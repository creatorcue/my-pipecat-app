import os
import json
import asyncio
import uvicorn
from fastapi import FastAPI, Response, WebSocket, Request
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketTransport,
    FastAPIWebsocketParams,
)
from pipecat.serializers.twilio import TwilioFrameSerializer
from pipecat.frames.frames import TextFrame
from pipecat.services.openai import OpenAISTTService, OpenAILLMService, OpenAITTSService
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.task import PipelineTask
from pipecat.pipeline.runner import PipelineRunner
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from dotenv import load_dotenv

load_dotenv()
app = FastAPI()

TUNNEL_URL = os.getenv("TUNNEL_URL", "https://z2894cw49yzy.share.zrok.io")
TUNNEL_WS = TUNNEL_URL.replace("https://", "wss://").replace("http://", "ws://") + "/ws"

import base64
import audioop
from pipecat.serializers.twilio import TwilioFrameSerializer
from pipecat.frames.frames import AudioRawFrame, Frame, EndFrame, CancelFrame, InterruptionFrame

class VobizFrameSerializer(TwilioFrameSerializer):
    """
    Subclasses TwilioFrameSerializer but overrides serialize() to use
    Vobiz's playAudio format instead of Twilio's media format.
    Deserialize() is inherited unchanged — same mulaw base64 format.
    """

    async def serialize(self, frame: Frame) -> str | bytes | None:
        if isinstance(frame, InterruptionFrame):
            # Vobiz clear audio event
            return json.dumps({"event": "clearAudio", "streamId": self._stream_sid})

        if isinstance(frame, AudioRawFrame):
            # Resample to 8000Hz mulaw — same as Twilio serializer does internally
            data = frame.audio
            if frame.sample_rate != 8000:
                data, _ = audioop.ratecv(data, 2, 1, frame.sample_rate, 8000, None)
            mulaw = audioop.lin2ulaw(data, 2)
            payload = base64.b64encode(mulaw).decode("utf-8")

            # ✅ Vobiz playAudio format — NOT Twilio's "media" event
            return json.dumps({
                "event": "playAudio",
                "media": {
                    "contentType": "audio/x-mulaw",
                    "sampleRate": 8000,
                    "payload": payload,
                }
            })

        if isinstance(frame, (EndFrame, CancelFrame)):
            return None

        return None

@app.post("/answer")
async def handle_answer(request: Request):
    try:
        body = await request.form()
        print("\n===== /answer HIT =====")
        print(dict(body))
    except Exception as e:
        print(f"[FORM PARSE ERROR] {e}")

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Stream
        bidirectional="true"
        keepCallAlive="true"
        contentType="audio/x-mulaw;rate=8000">
        {TUNNEL_WS}
    </Stream>
</Response>"""

    print(f"WS URL: {TUNNEL_WS}")
    return Response(content=xml, media_type="application/xml")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("\n===== ✅ WebSocket CONNECTED =====")

    stream_id = None

    try:
        # ── Wait for start frame to get streamId ──
        async for raw in websocket.iter_text():
            msg = json.loads(raw)
            event = msg.get("event")
            print(f"[HANDSHAKE] event={event}")

            if event == "start":
                start = msg.get("start", {})
                stream_id = start.get("streamId") or start.get("streamSid")
                print(f"✅ streamId={stream_id}")
                break
            elif event == "connected":
                continue
            elif event == "media":
                stream_id = msg.get("streamId", "fallback")
                print(f"⚠️ media before start, using fallback streamId")
                break

        if not stream_id:
            print("❌ No stream ID — aborting")
            await websocket.close()
            return

        # ── Build serializer ──
        # auto_hang_up=False → no Twilio credentials needed
        # twilio_sample_rate=8000 → matches Vobiz contentType
        serializer = VobizFrameSerializer(
        stream_sid=stream_id,
        params=TwilioFrameSerializer.InputParams(
        auto_hang_up=False,
        twilio_sample_rate=8000,
    )
)

        # ── Build transport ──
        # audio_in_enabled=True  → receive audio from Vobiz
        # audio_out_enabled=True → send TTS audio back to Vobiz
        # audio_out_sample_rate=8000 → match Vobiz mulaw 8000Hz
        # audio_in_sample_rate=8000  → Vobiz sends 8000Hz
        transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
        serializer=serializer,
        audio_in_enabled=True,
        audio_in_sample_rate=8000,
        audio_in_channels=1,
        audio_out_enabled=True,
        audio_out_sample_rate=8000,
        audio_out_channels=1,
        add_wav_header=False,
        vad_enabled=True,
        vad_analyzer=SileroVADAnalyzer(
            params=VADParams(
                stop_secs=0.5,      # detect end of speech after 0.5s silence (was ~1s default)
                min_volume=0.6,     # ignore very quiet background noise
            )
        ),
        vad_audio_passthrough=True,
    )
)

        # ── Build pipeline ──
        stt = OpenAISTTService(
            api_key=os.getenv("OPENAI_API_KEY"),
            model="whisper-1",          # whisper-1 is more robust than gpt-4o-transcribe for phone audio
            language="en",              # force English — prevents language switching
            prompt="Phone conversation. The user may ask for jokes, stories, or general questions.",  # context helps accuracy
        )

        llm = OpenAILLMService(
            api_key=os.getenv("OPENAI_API_KEY"),
            model="gpt-4o",
        )

        tts = OpenAITTSService(
            api_key=os.getenv("OPENAI_API_KEY"),
            voice="alloy",
        )

        context = OpenAILLMContext(messages=[{
        "role": "system",
        "content": (
            "You are a helpful voice assistant on a phone call. "
            "ALWAYS respond in English only, regardless of what language you hear. "
            "Keep all responses under 2 sentences. "
            "Be natural and conversational. No markdown or bullet points. "
            "If you mishear something unclear, ask the user to repeat it."
        )
}])
        context_aggregator = llm.create_context_aggregator(context)

        pipeline = Pipeline([
            transport.input(),
            stt,
            context_aggregator.user(),
            llm,
            tts,
            transport.output(),
            context_aggregator.assistant(),
        ])

        task = PipelineTask(pipeline)

        @transport.event_handler("on_client_connected")
        async def on_connected(transport, client):
            print("🎙️ Client connected — sending greeting")
            await task.queue_frames([
                TextFrame("Hello! I'm your AI assistant. How can I help you today?")
            ])

        @transport.event_handler("on_client_disconnected")
        async def on_disconnected(transport, client):
            print("📵 Client disconnected")
            await task.cancel()

        runner = PipelineRunner()
        print("🚀 Starting Pipecat pipeline...")
        await runner.run(task)

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        try:
            await websocket.close()
        except Exception:
            pass
    finally:
        print("===== WebSocket CLOSED =====")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7860)