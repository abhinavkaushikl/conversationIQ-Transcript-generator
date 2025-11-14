from vosk import Model, KaldiRecognizer
import pyaudio
import json
import os

# Load the Vosk model
def load_model():
    model_path = "/Users/abhinavkaushik/conversiq_transcript_pipeline/vosk-model-small-en-us-0.15"  # Update with the correct path
    if not os.path.exists(model_path):
        print(f"❌ Model path does not exist: {model_path}")
        exit(1)
    try:
        print("Loading Vosk model...")
        model = Model(model_path)
        print("✅ Model loaded successfully!")
        return model
    except Exception as e:
        print(f"❌ Failed to load model: {e}")
        exit(1)

# Test audio capture and transcription
def test_audio():
    model = load_model()
    recognizer = KaldiRecognizer(model, 16000)
    p = pyaudio.PyAudio()
    try:
        stream = p.open(format=pyaudio.paInt16,
                        channels=1,
                        rate=16000,
                        input=True,
                        frames_per_buffer=1024)
        print("🎤 Listening... Speak into the microphone.")
        while True:
            data = stream.read(1024, exception_on_overflow=False)
            if recognizer.AcceptWaveform(data):
                result = json.loads(recognizer.Result())
                print(f"📝 Transcript: {result['text']}")
    except KeyboardInterrupt:
        print("\n🛑 Stopping audio capture...")
    except Exception as e:
        print(f"❌ Error during audio capture: {e}")
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()

if __name__ == "__main__":
    test_audio()