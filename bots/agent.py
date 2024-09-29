import aiohttp
import os

from pipecat.frames.frames import EndFrame, Frame, LLMMessagesFrame, TextFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_response import LLMAssistantResponseAggregator, LLMFullResponseAggregator, LLMUserResponseAggregator
from pipecat.processors.aggregators.sentence import SentenceAggregator
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.services.deepgram import DeepgramSTTService, LiveOptions
from pipecat.vad.silero import SileroVADAnalyzer
from pipecat.services.elevenlabs import ElevenLabsTTSService
from pipecat.services.openai import OpenAILLMService
from pipecat.transports.services.daily import DailyParams, DailyTranscriptionSettings, DailyTransport, DailyTransportMessageFrame

async def agent(room_url: str, token, participant_id):
    async with aiohttp.ClientSession() as session:
        transport = DailyTransport(
            room_url,
            token,
            "Ai-GF",
            DailyParams(
                audio_in_enabled=True,
                audio_out_enabled=True,
                vad_enabled=True,
                vad_analyzer=SileroVADAnalyzer(),
                vad_audio_passthrough=True
            )
        )

        stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"), live_options=LiveOptions(
            language='en',
            model="nova-2",
            encoding="linear16",
            sample_rate=16000,
            channels=1,
            interim_results=False,
            smart_format=True,
        ))

        tts = ElevenLabsTTSService(
            aiohttp_session=session,
            api_key=os.getenv("ELEVENLABS_API_KEY"),
            voice_id="Xb7hH8MSUJpSbSDYk0k2",
            model="eleven_multilingual_v2",
        )

        llm = OpenAILLMService(
            api_key=os.getenv("OPENAI_API_KEY"),
            model="gpt-4o-mini"
        )

        messages = [
            {
                "role": "system",
                "content": f'''You are a sexy woman named Sikha. You love to talk to people. Give concise and playful responses. Don't include emojis and use words like "hmmm" and "ahhh" in your sentences.''' ,
            }
        ]
        user_in = LLMUserResponseAggregator(messages)
        assistant_out = LLMAssistantResponseAggregator(messages)
        lfra = LLMFullResponseAggregator()

        pipeline = Pipeline([
            transport.input(),
            stt,
            user_in,
            llm,
            lfra,
            tts,
            transport.output(),
            assistant_out,
        ])

        task = PipelineTask(pipeline, PipelineParams(allow_interruptions=True))

        @transport.event_handler("on_joined")
        async def on_joined(transport: DailyTransport, participant):
            participant = participant["participants"]["local"]
            # transport.update_subscription(participant_id=participant["id"])

        @transport.event_handler("on_participant_joined")
        async def on_participant_joined(transport: DailyTransport, participant):
            pass
            # if participant["id"] == participant_id:
                # transport.update_subscription(participant["id"])

        @transport.event_handler("on_participant_left")
        async def on_participant_left(transport, participant, reason):
            if participant["id"] == participant_id:
                await task.queue_frame(EndFrame())

        runner = PipelineRunner()

        await runner.run(task)