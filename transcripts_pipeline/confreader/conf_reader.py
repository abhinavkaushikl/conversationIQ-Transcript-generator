#!/usr/bin/env python3
"""
config_check.py

Run this script to validate and inspect the configuration used by the transcription
pipeline. It will:

 - Load the config file (searches multiple locations)
 - Print raw config file contents
 - Print a formatted summary of interpreted values
 - Optionally create the directories the config points to (use --create-dirs)

Usage:
    python3 conf_reader.py
    python3 conf_reader.py --config /path/to/transcription.conf
    python3 conf_reader.py --create-dirs
"""

import argparse
import configparser
import json
import os
import sys
import pyaudio
from datetime import datetime
from typing import Any, Dict, Optional


class ConfigManager:
    """Manages configuration from transcription.conf file"""

    def __init__(self, config_file: str = "transcription.conf"):
        self.config = configparser.ConfigParser()
        self.config_file = config_file

        actual_config_path = self._find_config_file(config_file)

        if not actual_config_path:
            raise FileNotFoundError(
                "Configuration file not found: %s\n"
                "Searched in multiple locations. Please specify the correct path:\n"
                "   python3 conf_reader.py --config /path/to/transcription.conf"
                % config_file
            )

        print("[%s] Loading configuration from: %s"
              % (datetime.now().isoformat(), actual_config_path))

        self._read_and_validate_file(actual_config_path)

        try:
            self.config.read(actual_config_path)
        except Exception as e:
            print("[PARSE ERROR] Failed to parse config file: %s" % e)
            raise

        self._validate_config()

        print("[%s] Configuration validation passed"
              % datetime.now().isoformat())

    def _read_and_validate_file(self, filepath: str) -> None:
        """Read the raw config file before parsing"""
        print("\n[DEBUG] Reading raw config file...")
        try:
            with open(filepath, "r") as f:
                content = f.read()

            if "//" in content:
                print("[WARNING] Config file contains '//' comments. Use '#' instead.")

            lines = content.split("\n")[:10]
            print("[DEBUG] First few lines of config file:")
            for i, line in enumerate(lines, 1):
                print("  Line %d: %s" % (i, repr(line)))
            print()

        except Exception as e:
            print("[ERROR] Failed to read config file: %s" % e)
            raise

    def _find_config_file(self, config_file: str) -> Optional[str]:
        """
        Try to find config file in multiple locations.
        """
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(script_dir))

        search_paths = [
            config_file,
            os.path.join(os.getcwd(), config_file),
            os.path.join(script_dir, config_file),
            os.path.join(script_dir, "conf", config_file),
            os.path.join(os.path.dirname(script_dir), "conf", config_file),
            os.path.join(project_root, "transcripts_pipeline", "conf", config_file),
            os.path.join(script_dir, "..", "..", "transcripts_pipeline", "conf", config_file),
        ]

        print("\n[CONFIG] Searching for config file in:")
        for i, path in enumerate(search_paths, 1):
            abs_path = os.path.abspath(path)
            exists = os.path.exists(abs_path)
            status = "FOUND" if exists else "NOT FOUND"
            print("  [%d] %s %s" % (i, status, abs_path))
            if exists:
                return abs_path

        print()
        return None

    def _validate_config(self):
        """Validate that all required sections exist"""
        required_sections = ["vosk", "audio", "recording", "whisper", "output"]

        print("\n[DEBUG] Sections found:", self.config.sections())
        print("[DEBUG] Required sections:", required_sections)

        missing_sections = [
            sec for sec in required_sections
            if not self.config.has_section(sec)
        ]

        if missing_sections:
            print("\nMissing sections:", missing_sections)
            raise ValueError(
                "Missing required sections: %s" % missing_sections
            )

    # ------------------ VOSK ------------------
    @property
    def vosk_model_path(self) -> str:
        return self.config.get("vosk", "MODEL_PATH")

    @property
    def vosk_enable_word_timing(self) -> bool:
        return self.config.getboolean("vosk", "ENABLE_WORD_TIMING")

    # ------------------ AUDIO ------------------
    @property
    def sample_rate(self) -> int:
        return self.config.getint("audio", "SAMPLE_RATE")

    @property
    def channels(self) -> int:
        return self.config.getint("audio", "CHANNELS")

    @property
    def frame_per_buffer(self) -> int:
        return self.config.getint("audio", "FRAME_PER_BUFFER")

    @property
    def wav_format(self):
        fmt = self.config.get("audio", "WAV_FORMAT")
        try:
            return getattr(pyaudio, fmt)
        except AttributeError:
            print("[WARNING] WAV_FORMAT '%s' not in pyaudio constants" % fmt)
            return fmt

    # ------------------ RECORDING ------------------
    @property
    def output_dir(self) -> str:
        return self.config.get("recording", "OUTPUT_DIR")

    @property
    def chunk_seconds(self) -> int:
        return self.config.getint("recording", "CHUNK_SECONDS")

    # ------------------ WHISPER ------------------
    @property
    def whisper_model_size(self) -> str:
        return self.config.get("whisper", "MODEL_SIZE")

    @property
    def whisper_language(self) -> str:
        return self.config.get("whisper", "LANGUAGE")

    @property
    def enable_whisper(self) -> bool:
        return self.config.getboolean("whisper", "ENABLE_WHISPER")

    # ------------------ OUTPUT ------------------
    @property
    def transcript_dir(self) -> str:
        return self.config.get("output", "TRANSCRIPT_DIR")

    def create_directories(self) -> None:
        for path in [self.output_dir, self.transcript_dir]:
            try:
                os.makedirs(path, exist_ok=True)
                print("[CONFIG] Created directory:", path)
            except Exception as e:
                print("[CONFIG] Failed to create %s: %s" % (path, e))

    def print_all_config(self) -> None:
        """Pretty print interpreted configuration"""
        print("\n" + "=" * 80)
        print("CONFIGURATION VALUES SUMMARY")
        print("=" * 80)

        print("\n[VOSK]")
        print("  Model Path:           ", self.vosk_model_path)
        print("  Word Timing:          ", self.vosk_enable_word_timing)

        print("\n[AUDIO]")
        print("  Sample Rate:          ", self.sample_rate)
        print("  Channels:             ", self.channels)
        print("  Frame Per Buffer:     ", self.frame_per_buffer)
        print("  WAV Format:           ", self.config.get("audio", "WAV_FORMAT"))

        print("\n[RECORDING]")
        print("  Output Directory:     ", self.output_dir)
        print("  Chunk Seconds:        ", self.chunk_seconds)

        print("\n[WHISPER]")
        print("  Model Size:           ", self.whisper_model_size)
        print("  Language:             ", self.whisper_language)
        print("  Enabled:              ", self.enable_whisper)

        print("\n[OUTPUT]")
        print("  Transcript Directory: ", self.transcript_dir)

        print("=" * 80 + "\n")

    def get_raw_config_dict(self) -> Dict[str, Dict[str, Any]]:
        return {sec: dict(self.config[sec]) for sec in self.config.sections()}

    def print_raw_config(self) -> None:
        print("\n" + "=" * 80)
        print("RAW CONFIGURATION FILE CONTENTS")
        print("=" * 80)
        for sec in self.config.sections():
            print("\n[%s]" % sec)
            for k, v in self.config[sec].items():
                print("  %s = %s" % (k, v))
        print("=" * 80 + "\n")


def main():
    ap = argparse.ArgumentParser(
        description="Check transcription pipeline config values",
    )
    ap.add_argument("--config", "-c", default="transcription.conf",
                    help="Path to .conf configuration file")
    ap.add_argument("--create-dirs", action="store_true",
                    help="Create directories")
    args = ap.parse_args()

    print("\n" + "=" * 80)
    print("CONFIGURATION CHECK - TRANSCRIPTION PIPELINE")
    print("=" * 80)

    try:
        cm = ConfigManager(args.config)
    except Exception as e:
        print("Error:", e)
        sys.exit(1)

    cm.print_raw_config()
    cm.print_all_config()

    print("[CONFIG AS JSON]")
    print(json.dumps(cm.get_raw_config_dict(), indent=2))

    if args.create_dirs:
        cm.create_directories()

    print("Done.\n")


if __name__ == "__main__":
    main()
