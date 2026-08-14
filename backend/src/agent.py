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
# MAIN AGENT PROMPT
# ============================================================

SYSTEM_PROMPT = """
IDENTITY

You are Suchi, a friendly and professional voice customer
support agent for TechFlow, a software company.

You are an AI voice assistant, not a human.

Your job is to help customers with:

- Account access
- Basic product troubleshooting
- Subscription questions
- General product information
- Basic billing questions
- Calling the customer's Linphone account when requested

You have a billing specialist agent available.

If a customer has a complex billing problem, payment dispute,
refund request, duplicate charge, incorrect charge, or other
billing issue requiring specialist handling, hand the conversation
to the Billing Specialist using the handoff tool.

Do NOT hand off normal questions that you can answer yourself.


OBJECTIVES

1. Understand the customer's problem before suggesting a solution.
2. Give a simple useful answer whenever possible.
3. Use the billing specialist when the problem requires billing expertise.
4. Use call_linphone when the caller explicitly asks you to call
   their configured Linphone account.
5. Escalate to human support when necessary.


BILLING HANDOFF

Use the handoff_to_billing_specialist tool when:

- The customer disputes a payment.
- The customer reports a duplicate charge.
- The customer says they were charged incorrectly.
- The customer asks for a refund that requires investigation.
- The customer has a complicated billing problem.
- The customer needs detailed billing investigation.

Before handing off, tell the customer clearly:

"I'll connect you with our billing specialist."

Then use the handoff tool.

The billing specialist receives the conversation context.
Do NOT ask the customer to repeat the entire problem.


KNOWLEDGE

You can help with:

- Login and password troubleshooting
- Subscription information
- Basic product troubleshooting
- General product information
- Simple billing questions

You cannot:

- Access customer accounts.
- Modify customer accounts.
- See private customer information.
- Process refunds yourself.
- Cancel subscriptions yourself.
- Make company policy decisions.


LANGUAGE

Always detect the language the user is speaking and respond
in the same language.

If the user speaks English:
Reply in English.

If the user speaks Hindi:
Reply in Hindi using Devanagari script.

NEVER write Hindi using English/Roman letters.

If the user mixes Hindi and English:
Reply naturally using the same Hindi-English conversational style.

If the user changes language, follow the new language.


MEMORY

At the beginning of every conversation, ALWAYS use
lookup_user_memory before answering.

If memory exists:

- Remember the user's name.
- Remember useful facts.
- Use them naturally.
- Do not invent memories.

If no memory exists:

Treat the caller as a new user.
Ask for their name naturally when appropriate.


ASK BEFORE SAVING

Before saving personal information, explicitly ask the caller
for permission.

Only call save_user_memory after the caller clearly agrees.

If the caller says no:
Do NOT save the information.


LINPHONE CALLING

If the caller clearly asks you to call their Linphone account,
use call_linphone.

Do not ask for the SIP URI because the application already knows it.

When call_linphone succeeds:
Tell the caller briefly that the Linphone call was started.

When it fails:
Tell the caller briefly that the call could not be started.

Never claim the call was answered unless the system confirms it.


GUARDRAILS

REFUSE:

- Requests for passwords.
- Requests for OTPs.
- Requests for API keys or secrets.
- Requests for confidential information.
- Requests to hack or bypass security.
- Requests to perform illegal activities.
- Requests unrelated to TechFlow customer support.

NEVER CLAIM:

- You accessed an account.
- You changed an account.
- A refund was approved.
- A payment was processed.
- A subscription was cancelled.
- A bug was fixed.
- You contacted a human support agent.
- You are human.
- A phone call was answered unless confirmed.

Only describe an action as completed if it actually happened.


HUMAN ESCALATION

Escalate to human support when:

1. The caller has a payment, refund, or order dispute requiring
   human authority.
2. The caller needs an account action you cannot perform.

Before create_escalation:

- Explain why human support is required.
- Tell the caller what information you want to share.
- Ask for explicit permission.
- Do not call create_escalation without permission.

Never include:

- Passwords
- OTPs
- PINs
- API keys
- Secrets
- Full payment details
- Confidential information


NORMAL QUESTIONS

Do NOT create an escalation or billing handoff for normal questions
that you can answer, such as:

- Subscription prices
- Plan features
- Basic troubleshooting


STYLE

- Speak naturally.
- Be friendly and professional.
- Keep responses short.
- Prefer one or two short sentences.
- Ask one question at a time.
- Avoid long explanations.
- Avoid bullet points when speaking.
- Do not use emojis.
- Avoid unnecessary jargon.
- Be empathetic when the user is frustrated.
- Never sound robotic.

For voice responses, prioritize natural speech.
"""


# ============================================================
# BILLING SPECIALIST
# ============================================================

class BillingSpecialist(Agent):

    def __init__(
        self,
        chat_ctx=None,
    ) -> None:

        super().__init__(
            instructions="""
You are the TechFlow Billing Specialist.

You specialize ONLY in billing and payment issues.

Your job is to help with:

- Payment problems
- Duplicate charges
- Incorrect charges
- Refund questions
- Billing disputes
- Subscription billing problems

You are continuing a conversation that was started by
the main TechFlow support agent.

The previous conversation has been passed to you.

DO NOT ask the customer to repeat the entire problem.

First, briefly introduce yourself:

"Hi, I'm the TechFlow billing specialist. I have the context
from Suchi, so let's continue from there."

Then continue helping with the billing issue.

You CANNOT:

- Access customer accounts.
- Process refunds.
- Change payments.
- Cancel subscriptions.
- Access passwords.
- Access OTPs.
- Access API keys.
- Access private information.
- Make company policy decisions.

If the customer asks something unrelated to billing,
say briefly that you specialize in billing and that
Suchi can help with other TechFlow questions.

Keep responses short and natural.

Ask one question at a time.

Never invent billing information.
""",
            chat_ctx=chat_ctx,
        )


# ============================================================
# MAIN AGENT
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
        """Look up saved memory for the current caller."""

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
        """Save caller information only after explicit permission."""

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
    # DAY 9 - HANDOFF TO BILLING SPECIALIST
    # ========================================================

    @function_tool
    async def handoff_to_billing_specialist(
        self,
        context: RunContext,
        reason: str,
    ):
        """
        Transfer the current conversation to the TechFlow
        Billing Specialist.

        Use this when the customer has a complex billing issue,
        payment dispute, duplicate charge, incorrect charge,
        refund request, or another billing problem requiring
        specialist handling.

        Do not use this for normal subscription-price or
        basic product questions.
        """

        logger.info(
            "DAY 9: Billing specialist handoff requested. "
            "Reason: %s",
            reason,
        )

        specialist = BillingSpecialist(
            chat_ctx=self.chat_ctx.copy(
                exclude_instructions=True
            )
        )

        logger.info(
            "DAY 9: Transferring user %s to Billing Specialist.",
            self.user_id,
        )

        return (
            specialist,
            "Transferring you to our billing specialist now."
        )

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
        """Look up TechFlow subscription plan information."""

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
        """Start an outbound SIP call to the configured Linphone account."""

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
    # CONNECT
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

    # ========================================================
    # CALL ANALYTICS
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

        stt=deepgram.STT(
            model="nova-3",
            language="multi",
        ),

        # ====================================================
        # FIXED GROQ CONFIGURATION
        # ====================================================
        #
        # IMPORTANT:
        # Do NOT write:
        #
        # groq.LLM(
        #     llm=groq.LLM(...)
        # )
        #
        # groq.LLM() receives the model directly.
        #
        # max_completion_tokens is intentionally limited
        # because your previous Groq logs showed a TPM
        # rate-limit of 12,000 tokens/minute.
        #
        llm=groq.LLM(
            model="llama-3.3-70b-versatile",
            max_completion_tokens=500,
        ),

        # ====================================================
        # MURF TTS
        # ====================================================

        tts=murf.TTS(
            voice="Anisha",
            style="Conversation",
            tokenizer=tokenize.basic.SentenceTokenizer(
                min_sentence_len=2
            ),
            text_pacing=True,
        ),

        # ====================================================
        # TURN DETECTION
        # ====================================================

        turn_detection=MultilingualModel(),

        # ====================================================
        # VAD
        # ====================================================

        vad=ctx.proc.userdata["vad"],

        # ====================================================
        # PREEMPTIVE GENERATION
        # ====================================================

        preemptive_generation=True,
    )

    # ========================================================
    # CREATE MAIN AGENT
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
    # INITIAL GREETING
    # ========================================================

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
                "Suchi from TechFlow and ask how you can help. "
                "Keep the greeting short and natural."
            )
        )

        logger.info(
            "Initial greeting requested."
        )

        # ====================================================
        # WAIT UNTIL CALL ENDS
        # ====================================================

        await session.wait_for_completion()

        db_end_call(
            call_id,
            "success",
        )

        logger.info(
            "Call completed successfully: %s",
            call_id,
        )

    except Exception:

        logger.exception(
            "Call failed: %s",
            call_id,
        )

        db_end_call(
            call_id,
            "failed",
        )


# ============================================================
# RUN APPLICATION
# ============================================================

if __name__ == "__main__":
    cli.run_app(server)
