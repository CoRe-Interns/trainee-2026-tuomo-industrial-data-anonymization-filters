from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def _candidate_ffmpeg_bins() -> list[Path]:
    local_app_data = os.environ.get("LOCALAPPDATA")
    candidates = [
        Path(r"C:\ffmpeg\bin"),
        Path(r"C:\Program Files\ffmpeg\bin"),
    ]

    if local_app_data:
        candidates.append(
            Path(local_app_data)
            / "Microsoft"
            / "WinGet"
            / "Packages"
            / "Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
            / "ffmpeg-8.1-full_build"
            / "bin"
        )

    return candidates


def _prepend_path(path_dir: Path) -> None:
    current_path = os.environ.get("PATH", "")
    os.environ["PATH"] = f"{path_dir};{current_path}" if current_path else str(path_dir)


def _bootstrap_ffmpeg_path() -> bool:
    if shutil.which("ffmpeg") is not None:
        return True

    for candidate in _candidate_ffmpeg_bins():
        if (candidate / "ffmpeg.exe").exists():
            _prepend_path(candidate)
            return shutil.which("ffmpeg") is not None

    return False


def ensure_ffmpeg_available() -> None:
    if not _bootstrap_ffmpeg_path():
        raise RuntimeError("ffmpeg is required for non-WAV audio conversion but was not found on PATH")


def convert_audio_to_wav(
    input_path: str | Path,
    sample_rate: int = 16000,
    channels: int = 1,
) -> Path:
    ensure_ffmpeg_available()

    source = Path(input_path)
    temp_dir = Path(tempfile.mkdtemp(prefix="audio_convert_in_"))
    output_wav = temp_dir / f"{source.stem}.converted.wav"

    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(source),
        "-ar",
        str(sample_rate),
        "-ac",
        str(channels),
        "-acodec",
        "pcm_s16le",
        str(output_wav),
    ]
    process = subprocess.run(command, capture_output=True, text=True, check=False)
    if process.returncode != 0:
        error_text = process.stderr.strip() or process.stdout.strip() or "unknown ffmpeg conversion error"
        raise RuntimeError(f"ffmpeg conversion to wav failed: {error_text}")

    return output_wav


def transcode_wav_to_audio(input_wav_path: str | Path, output_audio_path: str | Path) -> None:
    ensure_ffmpeg_available()

    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_wav_path),
        str(output_audio_path),
    ]
    process = subprocess.run(command, capture_output=True, text=True, check=False)
    if process.returncode != 0:
        error_text = process.stderr.strip() or process.stdout.strip() or "unknown ffmpeg transcode error"
        raise RuntimeError(f"ffmpeg transcode from wav failed: {error_text}")


def cleanup_temp_audio(path: str | Path | None) -> None:
    if path is None:
        return

    target = Path(path)
    target.unlink(missing_ok=True)
    try:
        target.parent.rmdir()
    except OSError:
        pass
