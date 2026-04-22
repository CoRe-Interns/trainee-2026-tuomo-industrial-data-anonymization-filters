from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TranscriptToken:
    text: str
    start_char: int
    end_char: int
    start_time_s: float
    end_time_s: float


@dataclass(frozen=True)
class TimeInterval:
    start_time_s: float
    end_time_s: float


@dataclass(frozen=True)
class IntervalWithLabel:
    start_time_s: float
    end_time_s: float
    label: str
    entity_type: str


def extract_tokens_from_sidecar(payload: dict[str, Any]) -> tuple[str, list[TranscriptToken]]:
    full_text = payload.get("text")
    words = payload.get("words")

    if not isinstance(full_text, str):
        raise ValueError("Audio sidecar is missing required string field: text")
    if not isinstance(words, list):
        raise ValueError("Audio sidecar is missing required list field: words")

    tokens: list[TranscriptToken] = []
    for index, item in enumerate(words):
        if not isinstance(item, dict):
            raise ValueError(f"Invalid sidecar word entry at index {index}: expected object")

        word_text = item.get("text")
        start_char = item.get("start_char")
        end_char = item.get("end_char")
        start_time = item.get("start_time_s")
        end_time = item.get("end_time_s")

        if not isinstance(word_text, str):
            raise ValueError(f"Invalid sidecar word text at index {index}")
        if not isinstance(start_char, int) or not isinstance(end_char, int):
            raise ValueError(f"Invalid sidecar char offsets at index {index}")
        if not isinstance(start_time, (int, float)) or not isinstance(end_time, (int, float)):
            raise ValueError(f"Invalid sidecar timestamps at index {index}")

        if start_char < 0 or end_char <= start_char:
            raise ValueError(f"Invalid sidecar char range at index {index}")
        if start_time < 0 or end_time <= start_time:
            raise ValueError(f"Invalid sidecar time range at index {index}")

        tokens.append(
            TranscriptToken(
                text=word_text,
                start_char=start_char,
                end_char=end_char,
                start_time_s=float(start_time),
                end_time_s=float(end_time),
            )
        )

    return full_text, tokens


def map_text_span_to_time_interval(
    start_char: int,
    end_char: int,
    tokens: list[TranscriptToken],
) -> TimeInterval | None:
    overlapping = [
        token
        for token in tokens
        if not (token.end_char <= start_char or token.start_char >= end_char)
    ]
    if not overlapping:
        return None

    start_time = min(token.start_time_s for token in overlapping)
    end_time = max(token.end_time_s for token in overlapping)

    return TimeInterval(start_time_s=start_time, end_time_s=end_time)


def apply_padding(interval: TimeInterval, padding_ms: int, audio_duration_s: float) -> TimeInterval:
    padding_s = max(0, padding_ms) / 1000.0
    return TimeInterval(
        start_time_s=max(0.0, interval.start_time_s - padding_s),
        end_time_s=min(audio_duration_s, interval.end_time_s + padding_s),
    )


def merge_intervals(intervals: list[IntervalWithLabel], merge_gap_s: float = 0.02) -> list[IntervalWithLabel]:
    if not intervals:
        return []

    sorted_intervals = sorted(intervals, key=lambda item: (item.start_time_s, item.end_time_s))
    merged: list[IntervalWithLabel] = [sorted_intervals[0]]

    for candidate in sorted_intervals[1:]:
        last = merged[-1]
        if candidate.start_time_s <= last.end_time_s + merge_gap_s:
            merged[-1] = IntervalWithLabel(
                start_time_s=last.start_time_s,
                end_time_s=max(last.end_time_s, candidate.end_time_s),
                label=last.label,
                entity_type=last.entity_type,
            )
            continue
        merged.append(candidate)

    return merged
