"""
Simple CLI to test Piper TTS synthesis using project policy settings.
Usage:
  python tools/piper_tts_test.py --text "Terve maailma" --out /tmp/test.wav

The script requires `audio.tts_cli_command` from configs/policy.json and expects
that command to include a valid Piper model and config.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.modalities.audio.wav_ops import WavData, write_wav
from src.modalities.audio.tts_overlay import synthesize_text_clip


def load_policy():
    root = Path(__file__).resolve().parents[1]
    cfg = root / "configs" / "policy.json"
    if not cfg.exists():
        return {}
    return json.loads(cfg.read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    policy = load_policy()
    audio_cfg = policy.get("audio", {})
    voice = audio_cfg.get("piper_voice", "taco_fi")
    cli = audio_cfg.get("tts_cli_command")
    if not cli:
        raise RuntimeError(
            "audio.tts_cli_command is required and must point to a working Piper command "
            "with model/config arguments"
        )

    # Create a silent target WAVData for format matching (mono,16-bit,16k default)
    target = WavData(channels=1, sample_width=2, frame_rate=audio_cfg.get("piper_sample_rate", 24000), frames=b"")

    try:
        clip = synthesize_text_clip(text=args.text, target=target, backend="piper", cli_command=cli, kokoro_voice=voice)
    except Exception as exc:
        print("Piper synthesis failed:", exc, file=sys.stderr)
        sys.exit(2)

    out_path = Path(args.out)
    write_wav(out_path, clip)
    print(f"Wrote: {out_path}")


if __name__ == "__main__":
    main()
