import asyncio
import sounddevice as sd
import numpy as np
import websockets
import base64
import json
import signal

WS_URL = "ws://localhost:8080/ws/twilio"
SAMPLE_RATE = 16000
BLOCK_SIZE = 1024  # smaller block = lower latency

async def stream_audio():
    async with websockets.connect(WS_URL) as ws:
        await ws.send(json.dumps({"event": "start"}))
        print("🎤 Connected! Start speaking... (Press Ctrl+C to stop)")

        loop = asyncio.get_event_loop()
        stop_event = asyncio.Event()

        def callback(indata, frames, time, status):
            if status:
                print("⚠️", status)
            pcm_bytes = (indata * 32767).astype(np.int16).tobytes()
            payload = base64.b64encode(pcm_bytes).decode("utf-8")
            msg = json.dumps({"event": "media", "media": {"payload": payload}})
            asyncio.run_coroutine_threadsafe(ws.send(msg), loop)

        # Open microphone stream
        with sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="float32", blocksize=BLOCK_SIZE, callback=callback
        ):
            try:
                await stop_event.wait()  # Run until Ctrl+C
            except asyncio.CancelledError:
                pass
            except KeyboardInterrupt:
                pass

        await ws.send(json.dumps({"event": "stop"}))
        print("🛑 Stopped streaming")

if __name__ == "__main__":
    try:
        asyncio.run(stream_audio())
    except KeyboardInterrupt:
        print("Exiting gracefully...")
