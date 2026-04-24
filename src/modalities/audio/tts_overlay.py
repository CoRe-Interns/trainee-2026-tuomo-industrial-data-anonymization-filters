from __future__ import annotations

import array
import subprocess
import tempfile
import wave
from pathlib import Path

from src.modalities.audio.wav_ops import (
    WavData,
    clamp_pcm16,
    pcm16_samples_from_bytes,
    pcm16_samples_to_bytes,
)


def _synth_to_wav_file(label_text: str, backend: str = "pyttsx3", cli_command: str | None = None) -> Path:
    temp_dir = Path(tempfile.mkdtemp(prefix="audio_tts_"))
    output_path = temp_dir / "label.wav"

    if backend == "cli":
        if not cli_command:
            raise RuntimeError("audio.tts_cli_command is required when audio.tts_backend is set to 'cli'")

        text_path = temp_dir / "input.txt"
        text_path.write_text(label_text, encoding="utf-8")

        command = cli_command.format(
            text=label_text,
            input_text_file=str(text_path),
            output_wav=str(output_path),
        )

        try:
            subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            raise RuntimeError(f"TTS CLI command failed: {stderr or exc}") from exc

        if not output_path.exists():
            raise RuntimeError("TTS CLI command did not produce output audio")
        return output_path

    if backend != "pyttsx3":
        raise RuntimeError(f"Unsupported TTS backend: {backend}")

    try:
        import pyttsx3
    except ImportError as exc:
        raise RuntimeError("pyttsx3 is required for spoken-label audio anonymization") from exc

    engine = pyttsx3.init()
    engine.setProperty("rate", 170)
    engine.save_to_file(label_text, str(output_path))
    engine.runAndWait()
    engine.stop()

    if not output_path.exists():
        raise RuntimeError("TTS synthesis did not produce output audio")

    return output_path


def _read_wav_as_data(path: str | Path) -> WavData:
    with wave.open(str(path), "rb") as handle:
        channels = handle.getnchannels()
        sample_width = handle.getsampwidth()
        frame_rate = handle.getframerate()
        frame_count = handle.getnframes()
        frames = handle.readframes(frame_count)

    return WavData(
        channels=channels,
        sample_width=sample_width,
        frame_rate=frame_rate,
        frames=frames,
    )


def _resample_pcm16(frames: bytes, channels: int, src_rate: int, dst_rate: int) -> bytes:
    if src_rate == dst_rate:
        return frames

    src_samples = pcm16_samples_from_bytes(frames)
    if channels <= 0:
        return frames

    src_frame_count = len(src_samples) // channels
    if src_frame_count == 0:
        return frames

    dst_frame_count = max(1, int(round(src_frame_count * (dst_rate / float(src_rate)))))
    dst_samples = array.array("h", [0] * (dst_frame_count * channels))

    for dst_frame in range(dst_frame_count):
        src_frame = min(src_frame_count - 1, int(round(dst_frame * src_rate / float(dst_rate))))
        for channel in range(channels):
            dst_samples[dst_frame * channels + channel] = src_samples[src_frame * channels + channel]

    return pcm16_samples_to_bytes(dst_samples)


def synthesize_text_clip(text: str, target: WavData, backend: str = "pyttsx3", cli_command: str | None = None) -> WavData:
    wav_file = _synth_to_wav_file(text, backend=backend, cli_command=cli_command)
    try:
        synthesized = _read_wav_as_data(wav_file)
    finally:
        wav_file.unlink(missing_ok=True)
        try:
            wav_file.parent.rmdir()
        except OSError:
            pass

    frames = synthesized.frames

    if synthesized.sample_width != 2 or target.sample_width != 2:
        raise ValueError("Only 16-bit PCM WAV files are supported for TTS overlay")

    if synthesized.frame_rate != target.frame_rate:
        frames = _resample_pcm16(
            frames=frames,
            channels=synthesized.channels,
            src_rate=synthesized.frame_rate,
            dst_rate=target.frame_rate,
        )

    if synthesized.channels != target.channels:
        source_samples = pcm16_samples_from_bytes(frames)
        if synthesized.channels == 1 and target.channels == 2:
            stereo_samples = []
            for sample in source_samples:
                stereo_samples.extend([sample, sample])
            frames = pcm16_samples_to_bytes(array.array("h", stereo_samples))
        elif synthesized.channels == 2 and target.channels == 1:
            mono_samples = []
            for idx in range(0, len(source_samples), 2):
                left = source_samples[idx]
                right = source_samples[idx + 1] if idx + 1 < len(source_samples) else left
                mono_samples.append(clamp_pcm16((left + right) / 2.0))
            frames = pcm16_samples_to_bytes(array.array("h", mono_samples))
        else:
            raise ValueError("Unsupported channel conversion for synthesized clip")

    return WavData(
        channels=target.channels,
        sample_width=target.sample_width,
        frame_rate=target.frame_rate,
        frames=frames,
    )


def synthesize_label_clip(label_text: str, target: WavData) -> WavData:
    return synthesize_text_clip(label_text, target, backend="pyttsx3", cli_command=None)


def overlay_clip(
    base_data: WavData,
    clip_data: WavData,
    start_time_s: float,
    end_time_s: float,
) -> WavData:
    if clip_data.channels != base_data.channels or clip_data.sample_width != base_data.sample_width:
        raise ValueError("Clip format must match base audio format")

    bytes_per_frame = base_data.channels * base_data.sample_width
    start_frame = max(0, int(round(start_time_s * base_data.frame_rate)))
    end_frame = min(base_data.frame_count, int(round(end_time_s * base_data.frame_rate)))
    if end_frame <= start_frame:
        return base_data

    region_frames = end_frame - start_frame
    max_region_bytes = region_frames * bytes_per_frame

    clip_bytes = clip_data.frames[:max_region_bytes]
    if not clip_bytes:
        return base_data

    start_byte = start_frame * bytes_per_frame
    end_byte = min(start_byte + len(clip_bytes), len(base_data.frames))

    output_samples = pcm16_samples_from_bytes(base_data.frames)
    clip_samples = pcm16_samples_from_bytes(clip_bytes[: end_byte - start_byte])

    start_sample = start_byte // base_data.sample_width
    for index, clip_sample in enumerate(clip_samples):
        sample_index = start_sample + index
        if sample_index >= len(output_samples):
            break
        mixed = output_samples[sample_index] + clip_sample
        output_samples[sample_index] = clamp_pcm16(mixed)

    return WavData(
        channels=base_data.channels,
        sample_width=base_data.sample_width,
        frame_rate=base_data.frame_rate,
        frames=pcm16_samples_to_bytes(output_samples),
    )
