from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


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


@dataclass(frozen=True)
class WhisperTranscript:
    text: str
    tokens: list[TranscriptToken]


def _normalize_word_text(word_text: str) -> str:
    return " ".join(word_text.strip().split())


def _append_token(transcript_parts: list[str], current_text_length: int, token_text: str) -> int:
    if transcript_parts:
        transcript_parts.append(" ")
        current_text_length += 1

    transcript_parts.append(token_text)
    return current_text_length + len(token_text)


def _load_whisper_model(model_name: str):
    try:
        import whisper
    except ImportError as exc:
        raise RuntimeError("openai-whisper is required for audio transcription") from exc

    return whisper.load_model(model_name)


def transcribe_audio_with_whisper(
    audio_path: str | Path,
    model_name: str = "base",
    language: str | None = None,
    temperature: float = 0.0,
    beam_size: int | None = None,
    best_of: int | None = None,
    initial_prompt: str | None = None,
) -> WhisperTranscript:
    model = _load_whisper_model(model_name)

    transcription_kwargs: dict[str, object] = {
        "word_timestamps": True,
        "verbose": False,
        "temperature": temperature,
    }
    if language is not None:
        transcription_kwargs["language"] = language
    if beam_size is not None:
        transcription_kwargs["beam_size"] = beam_size
    if best_of is not None:
        transcription_kwargs["best_of"] = best_of
    if initial_prompt:
        transcription_kwargs["initial_prompt"] = initial_prompt

    result = model.transcribe(str(Path(audio_path)), **transcription_kwargs)
    segments = result.get("segments", [])

    transcript_parts: list[str] = []
    tokens: list[TranscriptToken] = []
    current_text_length = 0

    for segment in segments:
        if not isinstance(segment, dict):
            continue

        words = segment.get("words")
        if isinstance(words, list) and words:
            for word in words:
                if not isinstance(word, dict):
                    continue

                word_text = _normalize_word_text(str(word.get("word", "")))
                start_time = word.get("start")
                end_time = word.get("end")

                if not word_text:
                    continue
                if not isinstance(start_time, (int, float)) or not isinstance(end_time, (int, float)):
                    continue
                if float(end_time) <= float(start_time):
                    continue

                start_char = current_text_length + (1 if transcript_parts else 0)
                current_text_length = _append_token(transcript_parts, current_text_length, word_text)

                tokens.append(
                    TranscriptToken(
                        text=word_text,
                        start_char=start_char,
                        end_char=current_text_length,
                        start_time_s=float(start_time),
                        end_time_s=float(end_time),
                    )
                )
            continue

        segment_text = _normalize_word_text(str(segment.get("text", "")))
        start_time = segment.get("start")
        end_time = segment.get("end")

        if not segment_text:
            continue
        if not isinstance(start_time, (int, float)) or not isinstance(end_time, (int, float)):
            continue
        if float(end_time) <= float(start_time):
            continue

        start_char = current_text_length + (1 if transcript_parts else 0)
        current_text_length = _append_token(transcript_parts, current_text_length, segment_text)

        tokens.append(
            TranscriptToken(
                text=segment_text,
                start_char=start_char,
                end_char=current_text_length,
                start_time_s=float(start_time),
                end_time_s=float(end_time),
            )
        )

    return WhisperTranscript(text="".join(transcript_parts), tokens=tokens)


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