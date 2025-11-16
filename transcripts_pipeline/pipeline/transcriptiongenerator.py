# live_transcriber_from_conf.py
"""
Live transcriber that loads configuration from:
  <project_root>/transcripts_pipeline/conf/transcription.conf

It ensures the transcripts_pipeline package is importable by searching up
the filesystem for the project root and inserting it into sys.path.
"""
import json
import pyaudio
from vosk import Model, KaldiRecognizer
from datetime import datetime
from typing import Optional, Callable, Any, Dict
import os
import sys

# ----------------------
# Helper: locate project root containing `transcripts_pipeline` folder
# ----------------------
def find_project_root_with_transcripts_pipeline(start_path: Optional[str] = None) -> Optional[str]:
    """
    Search upward from start_path (or this file) to find a parent directory
    that contains a 'transcripts_pipeline' child folder. Returns the parent
    directory path, or None if not found.
    """
    if start_path is None:
        start_path = os.path.dirname(os.path.abspath(__file__))

    cur = os.path.abspath(start_path)
    root = os.path.abspath(os.sep)
    while True:
        candidate = os.path.join(cur, "transcripts_pipeline")
        if os.path.isdir(candidate):
            # cur is project root
            return cur
        if cur == root:
            return None
        cur = os.path.abspath(os.path.join(cur, ".."))

# Find project root and add to sys.path so package imports work
_project_root = find_project_root_with_transcripts_pipeline()
if _project_root:
    if _project_root not in sys.path:
        sys.path.insert(0, _project_root)

# ----------------------
# Import ConfigManager from transcripts_pipeline.confreader.conf_reader
# ----------------------
ConfigManager = None
try:
    from transcripts_pipeline.confreader.conf_reader import ConfigManager  # preferred
except Exception as e:
    # Try fallback where confreader might be a sibling module (rare)
    try:
        from confreader.conf_reader import ConfigManager  # type: ignore
    except Exception:
        # Give a clear error later if ConfigManager still None
        ConfigManager = None

# ----------------------
# LiveTranscriber class
# ----------------------
class LiveTranscriber:
    """Handles real-time transcription using Vosk and reads config via ConfigManager."""

    def __init__(self, config: Optional[Any] = None):
        """
        Args:
            config: either
                - an instance of ConfigManager, or
                - a path string to the config file (e.g. '/.../transcription.conf'), or
                - None (will error later)
        """
        # If the user passed a path, instantiate ConfigManager
        if isinstance(config, str):
            if ConfigManager is None:
                raise RuntimeError("ConfigManager import failed; cannot instantiate from path.")
            self.config = ConfigManager(config)
        elif config is None:
            raise ValueError("config must be a ConfigManager instance or path to config file.")
        else:
            # Assume config is already an instance of ConfigManager (duck-typed)
            self.config = config

        # Vosk / audio internals
        self.model = None
        self.recognizer = None
        self.stream = None
        self.p = None

    # ----------------------------------------
    # Model & audio setup
    # ----------------------------------------
    def load_model(self) -> None:
        """Load Vosk model from config (vosk -> MODEL_PATH)."""
        model_path = self.config.vosk_model_path
        if not model_path or not isinstance(model_path, str):
            raise FileNotFoundError("Vosk model path is missing in config")
        print(f"[{datetime.now().isoformat()}] Loading Vosk model from: {model_path}")
        self.model = Model(model_path)
        print(f"[{datetime.now().isoformat()}] Vosk model loaded successfully!")

    def setup_audio_stream(self) -> None:
        """Open PyAudio stream using values from config (audio section)."""
        self.p = pyaudio.PyAudio()
        wav_format = self.config.wav_format  # ConfigManager returns pyaudio constant if valid

        # device selection is optional in your ConfigManager; handle if present
        open_kwargs = dict(
            format=wav_format,
            channels=self.config.channels,
            rate=self.config.sample_rate,
            input=True,
            frames_per_buffer=self.config.frame_per_buffer
        )

        # if ConfigManager exposes device index property name 'device_index', try to use it
        if hasattr(self.config, "device_index"):
            device_index = getattr(self.config, "device_index")
            if device_index:
                open_kwargs["input_device_index"] = device_index

        self.stream = self.p.open(**open_kwargs)
        print(f"[LiveTranscriber] Audio stream opened (rate: {self.config.sample_rate} Hz, channels: {self.config.channels})")

    def start_recognition(self) -> None:
        """Create KaldiRecognizer and enable word timing if configured."""
        if self.model is None:
            raise RuntimeError("Model not loaded. Call load_model() first.")
        self.recognizer = KaldiRecognizer(self.model, self.config.sample_rate)

        # enable word timing if config requests it (and recognizer supports it)
        try:
            if getattr(self.config, "vosk_enable_word_timing", False):
                if hasattr(self.recognizer, "SetWords"):
                    try:
                        self.recognizer.SetWords(True)
                    except Exception:
                        # some vosk versions expose a function with different casing; ignore failures
                        pass
        except Exception:
            # attribute access error fallback (keep running)
            pass

        print("[LiveTranscriber] Vosk recognizer initialized")

    # ----------------------------------------
    # Streaming / generator
    # ----------------------------------------
    def transcribe_stream(self, audio_callback: Optional[Callable[[bytes], None]] = None):
        """
        Generator: yields transcription events as dicts:
            { "type": "partial"|"final",
              "text": "...",
              "timestamp": ISO8601 str,
              "raw_result": <optional vosk dict> }
        """
        if self.stream is None or self.recognizer is None:
            raise RuntimeError("Audio stream or recognizer not initialized. Call setup and start_recognition first.")

        print("[LiveTranscriber] Starting real-time transcription. Press Ctrl+C to stop.")
        try:
            while True:
                data = self.stream.read(self.config.frame_per_buffer, exception_on_overflow=False)

                # pass raw pcm to optional callback (recorder will attach here)
                if audio_callback:
                    try:
                        audio_callback(data)
                    except Exception as e:
                        # Do not break on callback errors; log and continue
                        print(f"[LiveTranscriber] audio_callback error: {e}")

                # Feed to Vosk
                try:
                    if self.recognizer.AcceptWaveform(data):
                        res = json.loads(self.recognizer.Result())
                        text = res.get("text", "").strip()
                        if text:
                            yield {
                                "type": "final",
                                "text": text,
                                "timestamp": datetime.now().isoformat(),
                                "raw_result": res
                            }
                    else:
                        partial = json.loads(self.recognizer.PartialResult())
                        ptxt = partial.get("partial", "").strip()
                        if ptxt:
                            yield {
                                "type": "partial",
                                "text": ptxt,
                                "timestamp": datetime.now().isoformat(),
                                "raw_result": partial
                            }
                except Exception as e:
                    # Vosk read error — log and continue the loop gracefully
                    print(f"[LiveTranscriber] Vosk processing error: {e}")
                    continue

        except KeyboardInterrupt:
            print("\n[LiveTranscriber] Transcription stopped by user")
        except Exception as e:
            print(f"[LiveTranscriber] Error during transcription: {e}")
            raise

    def cleanup(self) -> None:
        """Stop/close stream and terminate PyAudio safely."""
        try:
            if self.stream is not None:
                try:
                    self.stream.stop_stream()
                except Exception:
                    pass
                try:
                    self.stream.close()
                except Exception:
                    pass
                self.stream = None
            if self.p is not None:
                try:
                    self.p.terminate()
                except Exception:
                    pass
                self.p = None
            print("[LiveTranscriber] Audio resources cleaned up")
        except Exception as e:
            print(f"[LiveTranscriber] Error during cleanup: {e}")

    # ----------------------------------------
    # Convenience runner that yields events and always cleans up
    # ----------------------------------------
    def run(self, audio_callback: Optional[Callable[[bytes], None]] = None):
        """
        High-level wrapper: loads model, opens stream, initializes recognizer,
        and yields transcription events. Ensures cleanup on exit.
        """
        try:
            # If config manager is not fully initialized, these methods will raise early
            self.load_model()
            self.setup_audio_stream()
            self.start_recognition()

            for evt in self.transcribe_stream(audio_callback=audio_callback):
                yield evt

        finally:
            # ALWAYS clean up resources
            self.cleanup()


# -------------------------
# Example usage (CLI-like)
# -------------------------
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Live Vosk transcription (config-driven).")

    # Default config path: prefer config at <project_root>/transcripts_pipeline/conf/transcription.conf
    if _project_root:
        default_conf = os.path.join(_project_root, "transcripts_pipeline", "conf", "transcription.conf")
    else:
        # fallback to local conf/transcription.conf next to this file
        default_conf = os.path.join(os.path.dirname(os.path.abspath(__file__)), "conf", "transcription.conf")

    parser.add_argument("--config", "-c", default=default_conf, help="Path to config file")
    args = parser.parse_args()

    if ConfigManager is None:
        raise RuntimeError(
            "Could not import ConfigManager from transcripts_pipeline.confreader.conf_reader. "
            "Ensure 'transcripts_pipeline/confreader/conf_reader.py' exists and the project root is discoverable."
        )

    cfg = ConfigManager(args.config)

    # Example audio_callback that simply writes raw frames into a queue or file.
    # Replace with your Recorder/Queue wiring.
    def print_callback(_data: bytes):
        # No-op or small monitor (keep very cheap)
        pass

    transcriber = LiveTranscriber(cfg)

    try:
        for result in transcriber.run(audio_callback=print_callback):
            # process or print the result
            if result["type"] == "partial":
                # print inline partial
                print(f"\r[PARTIAL] {result['text']}", end="", flush=True)
            else:
                print(f"\n[FINAL] {result['text']}")
    except KeyboardInterrupt:
        print("Exiting.")
