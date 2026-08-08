import logging

from dotenv import load_dotenv
from livekit import rtc

from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    JobProcess,
    cli,
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


logger = logging.getLogger("agent")

load_dotenv(".env.local")


# ============================================================
# DAY 2 - AGENT PERSONALITY, JOB AND GUARDRAILS
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


LANGUAGE

Language behavior is very important.

If the user speaks English:
Reply in English.

If the user speaks Hindi:
Reply in Hindi.

If the user mixes Hindi and English:
Reply naturally in the same Hindi-English code-mixed style.

Examples:

User:
"Mera login nahi ho raha, password reset kaise karun?"

Good response:
"Bilkul. Pehle ye check karte hain ki aapko password reset email mil rahi hai ya nahi."

User:
"My subscription ka payment fail ho gaya hai."

Good response:
"Okay. Let's check the payment issue. Kya payment karte waqt koi error message show hua?"

Do not unnecessarily translate English technical terms into Hindi.

Keep Hindi natural and conversational.

If the user changes language, follow the user's new language.


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

Say:
"Main passwords, OTPs ya confidential information handle nahi kar sakti. Aapki security ke liye ye information share na karein."


NEVER CLAIM:

- That you accessed the customer's account.
- That you changed their account.
- That a refund was approved.
- That a payment was processed.
- That a subscription was cancelled.
- That a bug was fixed.
- That you contacted a human support agent.
- That you are a human.

Only describe an action as completed if the user confirms it.


ESCALATION

If the issue requires account access, payment investigation,
refund approval, cancellation, or another action you cannot perform,
explain that a human support specialist is required.

Use this naturally:

"I couldn't safely resolve this request. A human support specialist
will need to handle it because they have access to the necessary
systems. Please contact our support team with your account email
and issue details."


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


GREETING

When the conversation starts, introduce yourself and explain
what you can help with.

Example:

"Hi, I'm Suchi from TechFlow support. I can help you with account,
billing, subscription, or basic product issues. What can I help
you with today?"
"""


# ============================================================
# AGENT
# ============================================================

class Assistant(Agent):

    def __init__(self) -> None:
        super().__init__(
            instructions=SYSTEM_PROMPT
        )


# ============================================================
# LIVEKIT SERVER
# ============================================================

server = AgentServer()


# ============================================================
# PREWARM
# ============================================================

def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


server.setup_fnc = prewarm


# ============================================================
# AGENT SESSION
# ============================================================

@server.rtc_session(agent_name="my-agent")
async def my_agent(ctx: JobContext):

    logger.info("🔥 AGENT JOB STARTED")

    ctx.log_context_fields = {
        "room": ctx.room.name,
    }


    # --------------------------------------------------------
    # VOICE PIPELINE
    # --------------------------------------------------------

    session = AgentSession(

        # ----------------------------------------------------
        # STT - Deepgram
        # ----------------------------------------------------
        # Multi-language recognition helps the agent understand
        # Hindi, English and code-mixed speech.

        stt=deepgram.STT(
            model="nova-3",
            language="multi",
        ),


        # ----------------------------------------------------
        # LLM - Groq
        # ----------------------------------------------------
        # Groq provides the fast language model.
        #
        # This model is multilingual and works well for
        # conversational applications.

        llm=groq.LLM(
            model="llama-3.3-70b-versatile",
        ),


        # ----------------------------------------------------
        # TTS - Murf Falcon
        # ----------------------------------------------------
        # Hindi output:
        # locale="hi-IN"
        #
        # This is what controls the language/locale of the
        # generated speech.

        tts=murf.TTS(
            voice="Anisha",
            locale="hi-IN",
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


    # --------------------------------------------------------
    # CONNECT TO LIVEKIT
    # --------------------------------------------------------

    await ctx.connect()

    logger.info("✅ Connected to LiveKit")


    # --------------------------------------------------------
    # START AGENT SESSION
    # --------------------------------------------------------

    await session.start(
        agent=Assistant(),
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


# ============================================================
# RUN APPLICATION
# ============================================================

if __name__ == "__main__":
    cli.run_app(server)
