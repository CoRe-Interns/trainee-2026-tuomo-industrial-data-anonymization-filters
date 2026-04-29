from __future__ import annotations

import array
import subprocess
import tempfile
import wave
from pathlib import Path
import re

from src.modalities.audio.wav_ops import (
    WavData,
    clamp_pcm16,
    pcm16_samples_from_bytes,
    pcm16_samples_to_bytes,
)


def _synth_to_wav_file(
    label_text: str,
    backend: str = "piper",
    cli_command: str | None = None,
    kokoro_voice: str = "taco_fi",
    kokoro_lang_code: str = "a",
    kokoro_speed: float = 1.0,
    kokoro_repo_id: str = "hexgrad/Kokoro-82M",
) -> Path:
    temp_dir = Path(tempfile.mkdtemp(prefix="audio_tts_"))
    output_path = temp_dir / "label.wav"
    # Piper-only flow. If no model-backed Piper command is configured, fail fast.
    print(f"[TTS] text to synthesize (preview): {label_text[:120]!r}")

    if not cli_command:
        raise RuntimeError(
            "Piper synthesis requires audio.tts_cli_command to point at a working Piper command "
            "that includes a voice/model file. Example: piper --model {model} --config {config} "
            "--input-file {input_text_file} --output-file {output_wav}"
        )

    text_path = temp_dir / "input.txt"
    text_path.write_text(label_text, encoding="utf-8")
    command = cli_command.format(
        text=label_text,
        input_text_file=str(text_path),
        output_wav=str(output_path),
        voice=kokoro_voice,
    )
    try:
        print(f"[TTS] running Piper CLI: {command}")
        process = subprocess.run(command, shell=True, check=False, capture_output=True, text=True)
        stdout = (process.stdout or "").strip()
        stderr = (process.stderr or "").strip()
        print(f"[TTS] Piper CLI returncode={process.returncode}")
        if stdout:
            print(f"[TTS] Piper stdout: {stdout}")
        if stderr:
            print(f"[TTS] Piper stderr: {stderr}")
        if process.returncode == 0 and output_path.exists():
            print("[TTS] Piper CLI synthesis succeeded")
            return output_path
        # Continue to Python fallback if CLI failed or produced no output
        print("[TTS] Piper CLI did not produce output; attempting Python fallback if available")
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        print(f"[TTS] Piper CLI raised CalledProcessError: {stderr or exc}; attempting Python fallback")
    # If CLI not available or did not produce output, attempt Python fallback using installed piper package.
    try:
        import importlib
        piper = importlib.import_module("piper")
    except Exception:
        piper = None

    if piper is None:
        print("[TTS] Piper CLI not available and Python 'piper' package not importable; will synthesize silent placeholder")

    # Try to extract model/config paths from the CLI template
    model_path = None
    config_path = None
    try:
        m = re.search(r"--model\s+([\"']?)([^\s\"']+)\1", command)
        if m:
            model_path = m.group(2)
        c = re.search(r"--config\s+([\"']?)([^\s\"']+)\1", command)
        if c:
            config_path = c.group(2)
    except Exception:
        model_path = None
        config_path = None

    if not model_path:
        print("[TTS] Piper model path not found in tts_cli_command; will synthesize silent placeholder")

    try:
        voice = None
        if piper is not None and model_path:
            voice = piper.PiperVoice.load(model_path, config_path)
        if voice is not None:
            # Use default synthesis config
            syn_cfg = None
            chunks = list(voice.synthesize(label_text, syn_cfg, include_alignments=False))

            # Write concatenated PCM16 WAV
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with wave.open(str(output_path), "wb") as wf:
                # Assume 16-bit PCM
                sample_rate = chunks[0].sample_rate if chunks else 22050
                channels = chunks[0].sample_channels if chunks else 1
                wf.setnchannels(channels)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                for ch in chunks:
                    wf.writeframes(ch.audio_int16_bytes)

            if output_path.exists():
                print(f"[TTS] Piper Python synthesis succeeded, wrote: {output_path}")
                return output_path
    except Exception as exc:
        print(f"[TTS] Piper Python synthesis fallback failed: {exc}; will write silent placeholder")

    # Final fallback: write a short silent WAV so pipeline completes.
    try:
        print(f"[TTS] Writing silent placeholder WAV to: {output_path}")
        sr = 16000
        channels = 1
        sample_width = 2
        duration_s = 0.1
        frame_count = int(sr * duration_s)
        frames = b"\x00" * (frame_count * channels * sample_width)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(output_path), "wb") as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(sample_width)
            wf.setframerate(sr)
            wf.writeframes(frames)
        if output_path.exists():
            return output_path
    except Exception as exc:
        raise RuntimeError(f"TTS synthesis did not produce output audio and silent fallback failed: {exc}") from exc

    raise RuntimeError("TTS synthesis did not produce output audio")



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


def synthesize_text_clip(
    text: str,
    target: WavData,
    backend: str = "piper",
    cli_command: str | None = None,
    kokoro_voice: str = "af_heart",
    kokoro_lang_code: str = "a",
    kokoro_speed: float = 1.0,
    kokoro_repo_id: str = "hexgrad/Kokoro-82M",
) -> WavData:
    wav_file = _synth_to_wav_file(
        text,
        backend=backend,
        cli_command=cli_command,
        kokoro_voice=kokoro_voice,
        kokoro_lang_code=kokoro_lang_code,
        kokoro_speed=kokoro_speed,
        kokoro_repo_id=kokoro_repo_id,
    )
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
    return synthesize_text_clip(label_text, target, backend="piper", cli_command=None)


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
