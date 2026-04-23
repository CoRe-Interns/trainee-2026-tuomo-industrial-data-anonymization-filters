from __future__ import annotations

from pathlib import Path

from src.modalities.audio.speech_to_text import (
    IntervalWithLabel,
    apply_padding,
    map_text_span_to_time_interval,
    merge_intervals,
    transcribe_audio_with_whisper,
)
from src.modalities.audio.tts_overlay import overlay_clip, synthesize_label_clip
from src.modalities.audio.wav_ops import WavInterval, duck_intervals, read_wav, write_wav


def resolve_audio_output_path(input_path: str | Path, output_path: str | Path) -> Path:
    source = Path(input_path)
    target = Path(output_path)

    # If caller gives a generic stem (from .anonymized original), retain source extension semantics.
    if target.suffix.lower() != source.suffix.lower():
        target = target.with_suffix(source.suffix)

    if ".anonymized" not in target.stem:
        target = target.with_name(f"{target.stem}.anonymized{target.suffix}")

    if target.suffix.lower() != ".wav":
        return target

    return target


def _entity_to_label(entity_type: str, labels: dict[str, str]) -> str:
    return labels.get(entity_type, labels.get("default", "redacted"))


def _serialise_audio_detection(entity_type: str, start_time_s: float, end_time_s: float, label: str, score: float) -> dict[str, object]:
    return {
        "entity_type": entity_type,
        "start_time_s": round(start_time_s, 3),
        "end_time_s": round(end_time_s, 3),
        "replacement_label": label,
        "confidence": round(score, 2),
    }


def process_audio_with_whisper(
    audio_path: str | Path,
    output_audio_path: str | Path,
    anonymizer_tool,
    whisper_model: str,
    whisper_language: str | None,
    padding_ms: int,
    duck_db: float,
    labels: dict[str, str],
) -> tuple[list[dict[str, object]], str | None]:
    audio = read_wav(audio_path)

    transcript = transcribe_audio_with_whisper(
        audio_path=audio_path,
        model_name=whisper_model,
        language=whisper_language,
    )
    full_text = transcript.text
    tokens = transcript.tokens

    _, raw_results = anonymizer_tool.process_text(full_text)

    intervals: list[IntervalWithLabel] = []
    detections: list[dict[str, object]] = []

    for result in raw_results:
        mapped = map_text_span_to_time_interval(result.start, result.end, tokens)
        if mapped is None:
            continue

        padded = apply_padding(mapped, padding_ms=padding_ms, audio_duration_s=audio.duration_s)
        label = _entity_to_label(result.entity_type, labels)

        intervals.append(
            IntervalWithLabel(
                start_time_s=padded.start_time_s,
                end_time_s=padded.end_time_s,
                label=label,
                entity_type=result.entity_type,
            )
        )

        detections.append(
            _serialise_audio_detection(
                entity_type=result.entity_type,
                start_time_s=padded.start_time_s,
                end_time_s=padded.end_time_s,
                label=label,
                score=result.score,
            )
        )

    merged = merge_intervals(intervals)

    ducked = duck_intervals(
        data=audio,
        intervals=[WavInterval(start_time_s=item.start_time_s, end_time_s=item.end_time_s) for item in merged],
        duck_db=duck_db,
    )

    modified = ducked
    for interval in merged:
        clip = synthesize_label_clip(interval.label, modified)
        modified = overlay_clip(
            base_data=modified,
            clip_data=clip,
            start_time_s=interval.start_time_s,
            end_time_s=interval.end_time_s,
        )

    write_wav(output_audio_path, modified)
    return detections, None
