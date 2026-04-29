from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from src.modalities.audio.speech_to_text import (
    TranscriptToken,
    map_text_span_to_time_interval,
    transcribe_audio_with_whisper,
)
from src.modalities.audio.tts_overlay import synthesize_text_clip
from src.modalities.audio.wav_ops import WavData, read_wav, write_wav


def resolve_audio_output_path(input_path: str | Path, output_path: str | Path) -> Path:
    source = Path(input_path)
    target = Path(output_path)

    if not target.suffix:
        target = target.with_suffix(source.suffix)

    if ".anonymized" not in target.stem:
        target = target.with_name(f"{target.stem}.anonymized{target.suffix}")

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


@dataclass(frozen=True)
class SpokenChunk:
    text: str
    start_time_s: float
    end_time_s: float


def _overlaps_span(token: TranscriptToken, start_char: int, end_char: int) -> bool:
    return not (token.end_char <= start_char or token.start_char >= end_char)


def _silence_frames(duration_s: float, target: WavData) -> bytes:
    if duration_s <= 0:
        return b""
    frame_count = int(round(duration_s * target.frame_rate))
    bytes_per_frame = target.channels * target.sample_width
    return b"\x00" * (frame_count * bytes_per_frame)


def _fit_clip_to_duration(clip: WavData, duration_s: float, target: WavData) -> bytes:
    if duration_s <= 0:
        return b""

    bytes_per_frame = target.channels * target.sample_width
    target_frame_count = int(round(duration_s * target.frame_rate))
    desired_bytes = target_frame_count * bytes_per_frame
    clip_bytes = clip.frames[:desired_bytes]

    if len(clip_bytes) < desired_bytes:
        clip_bytes += b"\x00" * (desired_bytes - len(clip_bytes))

    return clip_bytes


_PLACEHOLDER_PATTERN = re.compile(r"\[([A-Z_]+)(\d+)?\]")


def _prepare_anonymized_text_for_tts(text: str, labels: dict[str, str]) -> str:
    def replace_placeholder(match: re.Match[str]) -> str:
        entity = match.group(1)
        mapped = labels.get(entity)
        if mapped:
            return mapped
        return entity.replace("_", " ").lower()

    normalized = _PLACEHOLDER_PATTERN.sub(replace_placeholder, text or "")
    normalized = re.sub(r"\s+([,.;:!?])", r"\1", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized or labels.get("default", "redacted")


def _build_spoken_chunks(
    tokens: list[TranscriptToken],
    raw_results,
    labels: dict[str, str],
) -> tuple[list[SpokenChunk], list[dict[str, object]]]:
    if not tokens:
        return [], []

    detection_meta: list[dict[str, object]] = []
    for result in raw_results:
        mapped = map_text_span_to_time_interval(result.start, result.end, tokens)
        if mapped is None:
            continue
        label = _entity_to_label(result.entity_type, labels)
        detection_meta.append(
            {
                "start_char": result.start,
                "end_char": result.end,
                "start_time_s": mapped.start_time_s,
                "end_time_s": mapped.end_time_s,
                "entity_type": result.entity_type,
                "label": label,
                "score": result.score,
            }
        )

    detection_meta.sort(key=lambda item: (int(item["start_char"]), int(item["end_char"])))

    chunks: list[SpokenChunk] = []
    detections: list[dict[str, object]] = []
    emitted_spans: set[tuple[int, int, str]] = set()

    index = 0
    while index < len(tokens):
        token = tokens[index]
        matched = None
        for item in detection_meta:
            if _overlaps_span(token, int(item["start_char"]), int(item["end_char"])):
                matched = item
                break

        if matched is None:
            phrase_tokens = [token.text]
            start_time_s = token.start_time_s
            end_time_s = token.end_time_s
            index += 1

            while index < len(tokens):
                next_token = tokens[index]
                blocked = False
                for item in detection_meta:
                    if _overlaps_span(next_token, int(item["start_char"]), int(item["end_char"])):
                        blocked = True
                        break
                if blocked:
                    break
                phrase_tokens.append(next_token.text)
                end_time_s = next_token.end_time_s
                index += 1

            chunks.append(
                SpokenChunk(
                    text=" ".join(phrase_tokens),
                    start_time_s=start_time_s,
                    end_time_s=end_time_s,
                )
            )
            continue

        key = (int(matched["start_char"]), int(matched["end_char"]), str(matched["entity_type"]))
        if key not in emitted_spans:
            emitted_spans.add(key)
            chunks.append(
                SpokenChunk(
                    text=str(matched["label"]),
                    start_time_s=float(matched["start_time_s"]),
                    end_time_s=float(matched["end_time_s"]),
                )
            )
            detections.append(
                _serialise_audio_detection(
                    entity_type=str(matched["entity_type"]),
                    start_time_s=float(matched["start_time_s"]),
                    end_time_s=float(matched["end_time_s"]),
                    label=str(matched["label"]),
                    score=float(matched["score"]),
                )
            )

        while index < len(tokens) and _overlaps_span(tokens[index], int(matched["start_char"]), int(matched["end_char"])):
            index += 1

    return chunks, detections


def _synthesize_speech_timeline(
    chunks: list[SpokenChunk],
    target_audio: WavData,
    tts_backend: str,
    tts_cli_command: str | None,
    kokoro_voice: str,
    kokoro_lang_code: str,
    kokoro_speed: float,
    kokoro_repo_id: str,
) -> WavData:
    if not chunks:
        return WavData(
            channels=target_audio.channels,
            sample_width=target_audio.sample_width,
            frame_rate=target_audio.frame_rate,
            frames=_silence_frames(target_audio.duration_s, target_audio),
        )

    output_parts: list[bytes] = []
    cursor_time_s = 0.0

    for chunk in chunks:
        if chunk.start_time_s > cursor_time_s:
            output_parts.append(_silence_frames(chunk.start_time_s - cursor_time_s, target_audio))
            cursor_time_s = chunk.start_time_s

        clip = synthesize_text_clip(
            text=chunk.text,
            target=target_audio,
            backend=tts_backend,
            cli_command=tts_cli_command,
            kokoro_voice=kokoro_voice,
            kokoro_lang_code=kokoro_lang_code,
            kokoro_speed=kokoro_speed,
            kokoro_repo_id=kokoro_repo_id,
        )
        chunk_duration_s = max(0.0, chunk.end_time_s - chunk.start_time_s)
        output_parts.append(_fit_clip_to_duration(clip, chunk_duration_s, target_audio))
        cursor_time_s = chunk.end_time_s

    if cursor_time_s < target_audio.duration_s:
        output_parts.append(_silence_frames(target_audio.duration_s - cursor_time_s, target_audio))

    return WavData(
        channels=target_audio.channels,
        sample_width=target_audio.sample_width,
        frame_rate=target_audio.frame_rate,
        frames=b"".join(output_parts),
    )


def process_audio_with_whisper(
    audio_path: str | Path,
    output_audio_path: str | Path,
    anonymizer_tool,
    whisper_model: str,
    whisper_language: str | None,
    whisper_temperature: float,
    whisper_beam_size: int | None,
    whisper_best_of: int | None,
    whisper_initial_prompt: str | None,
    labels: dict[str, str],
    tts_backend: str,
    tts_cli_command: str | None,
    kokoro_voice: str,
    kokoro_lang_code: str,
    kokoro_speed: float,
    kokoro_repo_id: str,
) -> tuple[list[dict[str, object]], str | None, str]:
    audio = read_wav(audio_path)

    transcript = transcribe_audio_with_whisper(
        audio_path=audio_path,
        model_name=whisper_model,
        language=whisper_language,
        temperature=whisper_temperature,
        beam_size=whisper_beam_size,
        best_of=whisper_best_of,
        initial_prompt=whisper_initial_prompt,
    )
    full_text = transcript.text
    tokens = transcript.tokens

    anonymized_text, raw_results = anonymizer_tool.process_text(full_text)
    _, detections = _build_spoken_chunks(tokens=tokens, raw_results=raw_results, labels=labels)
    tts_text = _prepare_anonymized_text_for_tts(anonymized_text, labels)
    print(f"[AudioPipeline] TTS text preview: {tts_text[:200]!r}")
    synthesized_clip = synthesize_text_clip(
        text=tts_text,
        target=audio,
        backend=tts_backend,
        cli_command=tts_cli_command,
        kokoro_voice=kokoro_voice,
        kokoro_lang_code=kokoro_lang_code,
        kokoro_speed=kokoro_speed,
        kokoro_repo_id=kokoro_repo_id,
    )

    synthesized = WavData(
        channels=audio.channels,
        sample_width=audio.sample_width,
        frame_rate=audio.frame_rate,
        frames=_fit_clip_to_duration(synthesized_clip, audio.duration_s, audio),
    )

    write_wav(output_audio_path, synthesized)
    try:
        exists = Path(output_audio_path).exists()
    except Exception:
        exists = False
    print(f"[AudioPipeline] wrote synthesized WAV to: {output_audio_path} (exists={exists})")
    return detections, None, anonymized_text
