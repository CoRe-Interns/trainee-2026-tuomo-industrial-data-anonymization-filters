from __future__ import annotations

import array
import sys
import wave
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WavData:
    channels: int
    sample_width: int
    frame_rate: int
    frames: bytes

    @property
    def frame_count(self) -> int:
        if self.channels <= 0 or self.sample_width <= 0:
            return 0
        return len(self.frames) // (self.channels * self.sample_width)

    @property
    def duration_s(self) -> float:
        if self.frame_rate <= 0:
            return 0.0
        return self.frame_count / float(self.frame_rate)


@dataclass(frozen=True)
class WavInterval:
    start_time_s: float
    end_time_s: float


INT16_MIN = -32768
INT16_MAX = 32767


def clamp_pcm16(value: float | int) -> int:
    return max(INT16_MIN, min(INT16_MAX, int(round(value))))


def pcm16_samples_from_bytes(frames: bytes) -> array.array:
    samples = array.array("h")
    samples.frombytes(frames)
    if sys.byteorder != "little":
        samples.byteswap()
    return samples


def pcm16_samples_to_bytes(samples: array.array) -> bytes:
    encoded = array.array("h", samples)
    if sys.byteorder != "little":
        encoded.byteswap()
    return encoded.tobytes()


def read_wav(path: str | Path) -> WavData:
    with wave.open(str(path), "rb") as handle:
        channels = handle.getnchannels()
        sample_width = handle.getsampwidth()
        frame_rate = handle.getframerate()
        frame_count = handle.getnframes()
        frames = handle.readframes(frame_count)

    if sample_width != 2:
        raise ValueError("Only 16-bit PCM WAV files are currently supported")

    return WavData(
        channels=channels,
        sample_width=sample_width,
        frame_rate=frame_rate,
        frames=frames,
    )


def write_wav(path: str | Path, data: WavData) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output_path), "wb") as handle:
        handle.setnchannels(data.channels)
        handle.setsampwidth(data.sample_width)
        handle.setframerate(data.frame_rate)
        handle.writeframes(data.frames)


def time_to_frame_index(time_s: float, frame_rate: int) -> int:
    return max(0, int(round(time_s * frame_rate)))


def slice_frame_bytes(frames: bytes, start_frame: int, end_frame: int, channels: int, sample_width: int) -> tuple[int, int]:
    bytes_per_frame = channels * sample_width
    return start_frame * bytes_per_frame, end_frame * bytes_per_frame


def duck_intervals(data: WavData, intervals: list[WavInterval], duck_db: float) -> WavData:
    if not intervals:
        return data

    if duck_db < 0:
        raise ValueError("duck_db must be >= 0")

    gain = 10 ** (-duck_db / 20.0)
    samples = pcm16_samples_from_bytes(data.frames)
    channels = data.channels

    for interval in intervals:
        start_frame = time_to_frame_index(max(0.0, interval.start_time_s), data.frame_rate)
        end_frame = time_to_frame_index(min(data.duration_s, interval.end_time_s), data.frame_rate)
        if end_frame <= start_frame:
            continue

        for frame_index in range(start_frame, end_frame):
            base = frame_index * channels
            for channel in range(channels):
                sample_index = base + channel
                samples[sample_index] = clamp_pcm16(samples[sample_index] * gain)

    return WavData(
        channels=data.channels,
        sample_width=data.sample_width,
        frame_rate=data.frame_rate,
        frames=pcm16_samples_to_bytes(samples),
    )
