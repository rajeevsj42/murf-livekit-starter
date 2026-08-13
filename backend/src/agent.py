import json
import logging
import os
from urllib.parse import urlparse

from dotenv import load_dotenv
from livekit import api, rtc
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    JobProcess,
    RunContext,
    cli,
    function_tool,
    room_io,
    tokenize,
)
from livekit.plugins import (
    deepgram,
    groq,
    murf,
    noise_cancellation,
    silero,
)
from livekit.plugins.turn_detector.multilingual import MultilingualModel

from memory import (
    init_db,
    lookup_user as db_lookup_user,
    save_user as db_save_user,
    create_escalation as db_create_escalation,
    start_call as db_start_call,
    end_call as db_end_call,
)


# ============================================================
# CONFIG
# ============================================================

logger = logging.getLogger("agent")

load_dotenv(".env.local")

SIP_OUTBOUND_TRUNK_ID = os.getenv("SIP_OUTBOUND_TRUNK_ID")

LINPHONE_SIP_URL = os.getenv(
    "LINPHONE_SIP_URL",
    "sip:aarush22@sip.linphone.org",
)


def get_linphone_sip_user() -> str:
    """
    Extract only the SIP username from:

        sip:aarush22@sip.linphone.org
    """

    try:
        parsed = urlparse(LINPHONE_SIP_URL)

        if parsed.username:
            return parsed.username

    except Exception:
        pass

    return "aarush22"


LINPHONE_SIP_USER = get_linphone_sip_user()

logger.info(
    "Linphone SIP user configured: %s",
    LINPHONE_SIP_USER,
)

logger.info(
    "Linphone outbound trunk configured: %s",
    SIP_OUTBOUND_TRUNK_ID,
)


# ============================================================
# SYSTEM PROMPT
# ============================================================

SYSTEM_PROMPT = """
IDENTITY

You are Suchi, a friendly and professional voice customer
support agent for TechFlow, a software company.

Your job is to help customers with:

- Account access
- Billing questions
- Subscription questions
- Basic product troubleshooting
- General product information
- Calling the customer's Linphone account when requested

You are an AI voice assistant, not a human.


OBJECTIVES

A successful call should:

1. Understand the customer's problem before suggesting a solution.
2. Provide a simple and useful solution whenever possible.
3. Escalate problems that require human access or authority.
4. If the caller explicitly asks you to call their Linphone account,
   use the call_linphone tool.


KNOWLEDGE

You can help with:

- Login and password troubleshooting
- Subscription information
- Billing questions
- Basic product troubleshooting
- General product information

You cannot:

- Access customer accounts.
- Modify customer accounts.
- See private customer information.
- Process refunds.
- Cancel subscriptions yourself.
- Make company policy decisions.

If you do not know something, say that you do not know.
Never invent an answer.


LANGUAGE & SCRIPT

Always detect the language the user is speaking and respond
in the same language.

If the user speaks English:
Reply in English.

If the user speaks Hindi:
Reply in Hindi using Devanagari script.

NEVER write Hindi using English/Roman letters.

If the user mixes Hindi and English:
Reply naturally using the same Hindi-English conversational style.

Do not unnecessarily translate common English technical terms.

If the user changes language, follow the user's new language.


MEMORY

You have two memory tools:

1. lookup_user_memory
2. save_user_memory

At the beginning of every conversation, ALWAYS use
lookup_user_memory before answering the user.

If memory exists:

- Remember the user's name.
- Remember useful facts.
- Use them naturally.
- Do not invent memories.

If no memory exists:

Treat the caller as a new user.
Ask for their name naturally when appropriate.


ASK BEFORE SAVING

Before saving any personal information, explicitly ask
the caller for permission.

Only call save_user_memory after the user clearly agrees.

If the user says no:

Do NOT call save_user_memory.

Never save information without permission.


LINPHONE CALLING

If the user clearly asks you to call their Linphone account,
use the call_linphone tool.

Do not ask the user for the SIP URI if the application
already has the configured Linphone account.

The application already knows the Linphone SIP account.

When the call_linphone tool succeeds:

Tell the user briefly that the Linphone call was started.

When it fails:

Tell the user briefly that the call could not be started.

Never claim the call was answered unless the system actually confirms it.


GUARDRAILS

REFUSE:

- Requests for passwords.
- Requests for OTPs.
- Requests for API keys or API secrets.
- Requests for confidential information.
- Requests to hack or bypass security.
- Requests to perform illegal activities.
- Requests unrelated to TechFlow customer support.

NEVER CLAIM:

- That you accessed the customer's account.
- That you changed their account.
- That a refund was approved.
- That a payment was processed.
- That a subscription was cancelled.
- That a bug was fixed.
- That you contacted a human support agent.
- That you are a human.
- That a phone call was answered unless the system confirms it.

Only describe an action as completed if it actually happened.


HUMAN ESCALATION

Escalate to human support when:

1. The caller has a payment, refund, or order dispute.
2. The caller needs an account action that you cannot perform,
   such as cancelling a subscription or investigating an account issue.

When escalation is needed:

- Explain why human support is required.
- Tell the caller what information you want to share.
- Ask for explicit permission before calling create_escalation.
- Do NOT call create_escalation if permission is denied.
- Only share useful non-sensitive information.
- Never include passwords, OTPs, PINs, API keys, secrets,
  full payment details, or other confidential information.

After create_escalation succeeds:

- Give the caller the reference ID returned by the tool.
- Tell the caller the request is open.
- Explain that a human specialist will review it.
- Do not promise an immediate response unless the system guarantees one.


NORMAL QUESTIONS

Do NOT create an escalation for normal questions that you can answer,
such as subscription prices, plan features, or basic troubleshooting.


STYLE

- Speak naturally.
- Be friendly and professional.
- Keep responses short.
- Prefer one or two short sentences.
- Ask one question at a time.
- Avoid long explanations.
- Avoid bullet points when speaking.
- Do not use emojis.
- Do not use complicated formatting.
- Avoid unnecessary technical jargon.
- Be empathetic when the user is frustrated.
- Never sound robotic.

For voice responses, prioritize natural speech over long explanations.
"""


# ============================================================
# AGENT
# ============================================================

class Assistant(Agent):

    def __init__(
        self,
        user_id: str,
        job_context: JobContext,
    ) -> None:

        self.user_id = user_id
        self.job_context = job_context

        super().__init__(
            instructions=SYSTEM_PROMPT
        )

    # ========================================================
    # LOOKUP MEMORY
    # ========================================================

    @function_tool
    async def lookup_user_memory(
        self,
        context: RunContext,
        request: str = "",
    ):
        """
        Look up saved memory for the current caller.
        """

        logger.info(
            "Looking up memory for user: %s",
            self.user_id,
        )

        user = db_lookup_user(self.user_id)

        if user is None:

            logger.info(
                "No memory found for %s",
                self.user_id,
            )

            return "No saved memory exists for this caller."

        logger.info(
            "Memory found for %s: %s",
            self.user_id,
            user,
        )

        return str(user)

    # ========================================================
    # SAVE MEMORY
    # ========================================================

    @function_tool
    async def save_user_memory(
        self,
        context: RunContext,
        name: str,
        language_preference: str,
        facts: str,
    ):
        """
        Save caller information only after explicit permission.
        """

        logger.info(
            "Saving memory for user: %s",
            self.user_id,
        )

        try:
            facts_dict = json.loads(facts)

        except json.JSONDecodeError:

            logger.error(
                "Invalid JSON received for facts"
            )

            return (
                "I couldn't save that information because "
                "the facts were not valid JSON."
            )

        db_save_user(
            user_id=self.user_id,
            name=name,
            language_preference=language_preference,
            facts=facts_dict,
        )

        logger.info(
            "Memory saved for user: %s",
            self.user_id,
        )

        return "The caller's memory was saved successfully."

    # ========================================================
    # HUMAN ESCALATION
    # ========================================================

    @function_tool
    async def create_escalation(
        self,
        context: RunContext,
        issue: str,
        summary: str,
        urgency: str,
        language: str,
        follow_up_method: str,
    ):
        """
        Create a human-support request.

        Only call this after the caller explicitly gives
        permission to share the described information.
        """

        logger.info(
            "Creating human escalation for user: %s",
            self.user_id,
        )

        urgency = urgency.lower().strip()

        if urgency not in {
            "low",
            "medium",
            "high",
            "emergency",
        }:
            urgency = "medium"

        escalation_id = db_create_escalation(
            user_id=self.user_id,
            issue=issue,
            summary=summary,
            urgency=urgency,
            language=language,
            follow_up_method=follow_up_method,
        )

        logger.info(
            "Escalation created: %s",
            escalation_id,
        )

        return (
            f"Human support request created successfully. "
            f"Reference ID: {escalation_id}. "
            f"Status: open."
        )

    # ========================================================
    # LOOKUP PLAN
    # ========================================================

    @function_tool
    async def lookup_plan(
        self,
        context: RunContext,
        plan_name: str,
    ):
        """
        Look up TechFlow subscription plan information.
        """

        plans = {
            "basic": {
                "price": "₹499 per month",
                "features": (
                    "basic product features and email support"
                ),
            },
            "pro": {
                "price": "₹999 per month",
                "features": (
                    "all standard features and priority support"
                ),
            },
            "enterprise": {
                "price": "custom pricing",
                "features": (
                    "advanced features, dedicated support, "
                    "and custom solutions"
                ),
            },
        }

        plan = plans.get(
            plan_name.lower().strip()
        )

        if not plan:

            return (
                "I couldn't find that subscription plan "
                "in the current TechFlow plan database."
            )

        return (
            f"{plan_name.title()} plan costs {plan['price']} "
            f"and includes {plan['features']}."
        )

    # ========================================================
    # CALL LINPHONE
    # ========================================================

    @function_tool
    async def call_linphone(
        self,
        context: RunContext,
        request: str = "",
    ):
        """
        Start an outbound SIP call to the configured Linphone account.
        """

        logger.info(
            "Outbound Linphone call requested."
        )

        if not SIP_OUTBOUND_TRUNK_ID:

            logger.error(
                "SIP_OUTBOUND_TRUNK_ID is not configured."
            )

            return (
                "The Linphone calling service is not configured."
            )

        room_name = self.job_context.room.name

        logger.info(
            "Dialing Linphone SIP user: %s",
            LINPHONE_SIP_USER,
        )

        logger.info(
            "Using outbound trunk: %s",
            SIP_OUTBOUND_TRUNK_ID,
        )

        logger.info(
            "Into room: %s",
            room_name,
        )

        try:

            participant_identity = (
                f"linphone_{self.user_id}"
            )

            request = api.CreateSIPParticipantRequest(
                room_name=room_name,
                sip_trunk_id=SIP_OUTBOUND_TRUNK_ID,
                sip_call_to=LINPHONE_SIP_USER,
                participant_identity=participant_identity,
            )

            result = (
                await self.job_context.api.sip.create_sip_participant(
                    request
                )
            )

            logger.info(
                "Linphone SIP participant created: %s",
                result,
            )

            return (
                "The Linphone call has been started successfully."
            )

        except Exception:

            logger.exception(
                "Failed to create outbound Linphone call."
            )

            return (
                "I couldn't start the Linphone call because "
                "the calling service returned an error."
            )


# ============================================================
# LIVEKIT SERVER
# ============================================================

server = AgentServer()

init_db()


# ============================================================
# PREWARM
# ============================================================

def prewarm(proc: JobProcess):

    logger.info(
        "Loading Silero VAD..."
    )

    proc.userdata["vad"] = silero.VAD.load()

    logger.info(
        "Silero VAD loaded"
    )


server.setup_fnc = prewarm


# ============================================================
# AGENT SESSION
# ============================================================

@server.rtc_session(
    agent_name="my-agent"
)
async def my_agent(ctx: JobContext):

    logger.info("=" * 60)
    logger.info("AGENT JOB STARTED")
    logger.info("=" * 60)

    ctx.log_context_fields = {
        "room": ctx.room.name,
    }

    # ========================================================
    # CONNECT TO LIVEKIT
    # ========================================================

    await ctx.connect()

    logger.info(
        "Connected to LiveKit: %s",
        ctx.room.name,
    )

    # ========================================================
    # GET CALLER
    # ========================================================

    participants = list(
        ctx.room.remote_participants.values()
    )

    if participants:

        caller = participants[0]
        user_id = caller.identity

    else:

        user_id = "demo_user_001"

    logger.info(
        "Caller detected: %s",
        user_id,
    )

    logger.info(
        "Agent using memory ID: %s",
        user_id,
    )

    # ========================================================
    # DAY 8 - START CALL ANALYTICS
    # ========================================================

    call_id = db_start_call(user_id)

    logger.info(
        "Call analytics started: %s for user: %s",
        call_id,
        user_id,
    )

    # ========================================================
    # VOICE PIPELINE
    # ========================================================

    session = AgentSession(

        # ----------------------------------------------------
        # STT
        # ----------------------------------------------------

        stt=deepgram.STT(
            model="nova-3",
            language="multi",
        ),

        # ----------------------------------------------------
        # LLM
        # ----------------------------------------------------

        llm=groq.LLM(
            model="llama-3.3-70b-versatile",
        ),

        # ----------------------------------------------------
        # MURF TTS
        # ----------------------------------------------------

        tts=murf.TTS(
            voice="Anisha",
            style="Conversation",
            tokenizer=tokenize.basic.SentenceTokenizer(
                min_sentence_len=2
            ),
            text_pacing=True,
        ),

        # ----------------------------------------------------
        # TURN DETECTION
        # ----------------------------------------------------

        turn_detection=MultilingualModel(),

        vad=ctx.proc.userdata["vad"],

        preemptive_generation=True,
    )

    # ========================================================
    # CREATE AGENT
    # ========================================================

    agent = Assistant(
        user_id=user_id,
        job_context=ctx,
    )

    # ========================================================
    # START SESSION
    # ========================================================

    await session.start(
        agent=agent,
        room=ctx.room,
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(
                noise_cancellation=lambda params: (
                    noise_cancellation.BVCTelephony()
                    if (
                        params.participant.kind
                        == rtc.ParticipantKind.PARTICIPANT_KIND_SIP
                    )
                    else noise_cancellation.BVC()
                ),
            ),
        ),
    )

    logger.info(
        "Agent session started successfully"
    )

    # ========================================================
    # INITIAL GREETING + MEMORY
    # ========================================================

    await session.generate_reply(
        instructions=(
            "Start the conversation now. "
            "Before giving your greeting, "
            "use the lookup_user_memory tool. "
            "If memory exists, greet the caller naturally "
            "using their saved name and relevant saved facts. "
            "Do not invent information. "
            "If no memory exists, introduce yourself as "
            "Suchi from TechFlow and ask how you can help."
        )
    )

    logger.info(
        "Initial greeting requested."
    )

    # ========================================================
    # DAY 8 - CALL ANALYTICS
    # ========================================================
    #
    # When this LiveKit job shuts down, mark the call
    # as successful if the session completed normally.
    #
    # This is registered only once.
    # ========================================================

    async def record_call_outcome():

        try:

            db_end_call(
                call_id,
                "success",
            )

            logger.info(
                "Call analytics completed: %s -> success",
                call_id,
            )

        except Exception:

            logger.exception(
                "Failed to record call analytics: %s",
                call_id,
            )

    ctx.add_shutdown_callback(
        record_call_outcome
    )

    await session.start(
        agent=agent,
        room=ctx.room,
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(
                noise_cancellation=lambda params: (
                    noise_cancellation.BVCTelephony()
                    if (
                        params.participant.kind
                        == rtc.ParticipantKind.PARTICIPANT_KIND_SIP
                    )
                    else noise_cancellation.BVC()
                ),
            ),
        ),
    )

    logger.info("Agent session started successfully")

    try:
        await session.generate_reply(
            instructions=(
                "Start the conversation now. "
                "Before giving your greeting, "
                "use the lookup_user_memory tool. "
                "If memory exists, greet the caller naturally "
                "using their saved name and relevant saved facts. "
                "Do not invent information. "
                "If no memory exists, introduce yourself as "
                "Suchi from TechFlow and ask how you can help."
            )
        )

        logger.info("Initial greeting requested.")

        # Keep the session alive until the call ends.
        await session.wait_for_completion()

        logger.info(
            "Call completed successfully: %s",
            call_id,
        )

    except Exception:
        logger.exception(
            "Call failed: %s",
            call_id,
        )
        db_end_call(call_id, "failed")

    else:
        db_end_call(call_id, "success")
# ============================================================
# RUN APPLICATION
# ============================================================

if __name__ == "__main__":
    cli.run_app(server)
