import json
import logging

from dotenv import load_dotenv
from livekit import rtc
from livekit.agents import function_tool, RunContext
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

# IMPORTANT:
# Alias database functions so they don't conflict
# with our agent tool methods.

from memory import (
    init_db,
    lookup_user as db_lookup_user,
    save_user as db_save_user,
)


logger = logging.getLogger("agent")

load_dotenv(".env.local")


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

You are an AI voice assistant, not a human.


OBJECTIVES

A successful call should:

1. Understand the customer's problem before suggesting a solution.
2. Provide a simple and useful solution whenever possible.
3. Escalate problems that require human access or authority.


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

Example:

"बिल्कुल। पहले देखते हैं कि आपको पासवर्ड रीसेट ईमेल मिल रही है या नहीं।"

NEVER write Hindi using English/Roman letters.

Do NOT write:

"Mera login nahi ho raha."

Instead write:

"मेरा लॉगिन नहीं हो रहा।"

If the user mixes Hindi and English:
Reply naturally using the same Hindi-English conversational style.

Example:

User:
"Mera login nahi ho raha, password reset kaise karun?"

Good response:
"बिल्कुल। पहले देखते हैं कि आपको पासवर्ड रीसेट ईमेल मिल रही है या नहीं।"

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

For example:

"Welcome back, Ramesh. Last time we spoke about your subscription.
How did that go?"

If no memory exists:

Treat the caller as a new user.

Ask for their name naturally when appropriate.


ASK BEFORE SAVING

Before saving any personal information, explicitly ask
the caller for permission.

For example:

"I can remember your name and a few details for your next call.
Would you like me to save that?"

Only call save_user_memory after the user clearly agrees.

If the user says no:

Do NOT call save_user_memory.

Never save information without permission.


GUARDRAILS

REFUSE:

- Requests for passwords.
- Requests for OTPs.
- Requests for API keys or API secrets.
- Requests for confidential information.
- Requests to hack or bypass security.
- Requests to perform illegal activities.
- Requests unrelated to TechFlow customer support.

If a user asks for an OTP, password, API key, or secret:

"मैं passwords, OTPs या confidential information handle नहीं कर सकती।
आपकी security के लिए ये information share न करें।"


NEVER CLAIM:

- That you accessed the customer's account.
- That you changed their account.
- That a refund was approved.
- That a payment was processed.
- That a subscription was cancelled.
- That a bug was fixed.
- That you contacted a human support agent.
- That you are a human.

Only describe an action as completed if it actually happened.


ESCALATION

If the issue requires account access, payment investigation,
refund approval, cancellation, or another action you cannot perform,
explain that a human support specialist is required.


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

    def __init__(self, user_id: str) -> None:

        self.user_id = user_id

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
        Look up the current caller's saved memory.

        The application already knows the caller's real user ID.
        The request parameter only exists so the LLM tool schema
        contains a valid property for Groq.
        """

        logger.info(
            f"🧠 Looking up memory for user: {self.user_id}"
        )

        user = db_lookup_user(self.user_id)

        if user is None:

            logger.info(
                f"🆕 No memory found for {self.user_id}"
            )

            return "No saved memory exists for this caller."

        logger.info(
            f"✅ Memory found for {self.user_id}: {user}"
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
        Save caller information after the caller explicitly
        gives permission.

        Only use this tool AFTER the caller clearly agrees.

        Args:
            name:
                The caller's name.

            language_preference:
                The caller's preferred language.

            facts:
                Important facts in JSON format.
        """

        logger.info(
            f"💾 Saving memory for user: {self.user_id}"
        )

        try:

            facts_dict = json.loads(facts)

        except json.JSONDecodeError:

            logger.error(
                "❌ Invalid JSON received for facts"
            )

            return (
                "I couldn't save that information because "
                "the facts were not valid JSON."
            )

        # Save using the REAL application user ID.
        db_save_user(
            user_id=self.user_id,
            name=name,
            language_preference=language_preference,
            facts=facts_dict,
        )

        logger.info(
            f"✅ Memory saved for user: {self.user_id}"
        )

        return "The caller's memory was saved successfully."

    @function_tool
    async def lookup_plan(self, context: RunContext, plan_name: str):
        """Look up TechFlow subscription plan information.

        Use this tool whenever the user asks about the price, features,
        or availability of a TechFlow subscription plan.

        Supported plans are Basic, Pro, and Enterprise.

        Args:
            plan_name: The TechFlow subscription plan the user is asking about.
        """

        plans = {
            "basic": {
                "price": "₹499 per month",
                "features": "basic product features and email support",
            },
            "pro": {
                "price": "₹999 per month",
                "features": "all standard features and priority support",
            },
            "enterprise": {
                "price": "custom pricing",
                "features": "advanced features, dedicated support, and custom solutions",
            },
        }

        plan = plans.get(plan_name.lower().strip())

        if not plan:
            return (
                "I couldn't find that subscription plan in the current "
                "TechFlow plan database."
            )

        return (
            f"{plan_name.title()} plan costs {plan['price']} and includes "
            f"{plan['features']}."
        )
# ============================================================
# LIVEKIT SERVER
# ============================================================

server = AgentServer()


# Initialize SQLite database when backend starts.
init_db()


# ============================================================
# PREWARM
# ============================================================

def prewarm(proc: JobProcess):

    logger.info("🔥 Loading Silero VAD...")

    proc.userdata["vad"] = silero.VAD.load()

    logger.info("✅ Silero VAD loaded")


server.setup_fnc = prewarm


# ============================================================
# AGENT SESSION
# ============================================================

@server.rtc_session(agent_name="my-agent")
async def my_agent(ctx: JobContext):

    logger.info("=" * 60)
    logger.info("🔥 AGENT JOB STARTED")
    logger.info("=" * 60)

    ctx.log_context_fields = {
        "room": ctx.room.name,
    }


    # ========================================================
    # CONNECT TO LIVEKIT
    # ========================================================

    await ctx.connect()

    logger.info(
        f"✅ Connected to LiveKit: {ctx.room.name}"
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

        # Development fallback
        user_id = "demo_user_001"


    logger.info(
        f"👤 Caller detected: {user_id}"
    )

    logger.info(
        f"🧠 Agent using memory ID: {user_id}"
    )


    # ========================================================
    # VOICE PIPELINE
    # ========================================================

    session = AgentSession(

        # ----------------------------------------------------
        # STT - Deepgram
        # ----------------------------------------------------

        stt=deepgram.STT(
            model="nova-3",
            language="multi",
        ),


        # ----------------------------------------------------
        # LLM - Groq
        # ----------------------------------------------------

        llm=groq.LLM(
            model="llama-3.3-70b-versatile",
        ),


        # ----------------------------------------------------
        # TTS - MURF FALCON
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
        user_id=user_id
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

                    if params.participant.kind
                    == rtc.ParticipantKind.PARTICIPANT_KIND_SIP

                    else noise_cancellation.BVC()
                ),
            ),
        ),
    )


    logger.info(
        "🎤 Agent session started successfully"
    )


    # ========================================================
    # INITIAL GREETING + MEMORY LOOKUP
    # ========================================================

    await session.generate_reply(

        instructions=(
            "Start the conversation now. "

            "Before giving your greeting, "
            "use the lookup_user_memory tool. "

            "If memory exists, greet the caller naturally "
            "using their saved name and relevant saved facts. "

            "Do not invent any information. "

            "If no memory exists, introduce yourself as "
            "Suchi from TechFlow and ask how you can help."
        )
    )


    logger.info(
        "👋 Initial greeting requested"
    )


# ============================================================
# RUN APPLICATION
# ============================================================

if __name__ == "__main__":

    cli.run_app(server)
