from __future__ import annotations

import json
import mimetypes
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

from src.anonymizer import AnonymizerTool
from src.logger import log_redaction
from src.modalities.audio.audio_pipeline import (
    process_audio_with_whisper,
    resolve_audio_output_path,
)
from src.modalities.audio.conversion import (
    cleanup_temp_audio,
    convert_audio_to_wav,
    ensure_ffmpeg_available,
    transcode_wav_to_audio,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = PROJECT_ROOT / "configs"
POLICY_CONFIG_NAME = "policy.json"

TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".log", ".json", ".xml", ".yaml", ".yml"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff"}
AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".m4a", ".aac", ".ogg", ".opus"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".wmv", ".webm"}


@dataclass
class FileProcessingResult:
    input_path: str
    detected_kind: str
    status: str
    policy_name: str
    output_path: str | None = None
    report_path: str | None = None
    detections: list[dict[str, object]] = field(default_factory=list)
    message: str | None = None


def load_policy_config(policy_name: str) -> dict:
    config_path = CONFIG_DIR / POLICY_CONFIG_NAME
    with config_path.open("r", encoding="utf-8") as file_handle:
        config = json.load(file_handle)

    if "entities" not in config:
        raise KeyError("Policy config missing required field: 'entities'")
    if "thresholds" not in config:
        raise KeyError("Policy config missing required field: 'thresholds'")

    thresholds = config["thresholds"]
    if policy_name not in thresholds:
        raise KeyError(f"Unknown policy mode: {policy_name}")

    return {
        "policy_name": policy_name,
        "entities": config["entities"],
        "threshold": thresholds[policy_name],
        "language": config.get("language", "en"),
        "audio": config.get("audio", {}),
    }


def build_anonymizer(policy_name: str) -> tuple[AnonymizerTool, dict]:
    config = load_policy_config(policy_name)
    tool = AnonymizerTool(
        entities=config["entities"],
        threshold=config["threshold"],
        policy_name=policy_name,
        language=config.get("language", "en"),
    )
    return tool, config


def process_text_content(text: str, policy_name: str = "light") -> tuple[str, list, dict]:
    tool, config = build_anonymizer(policy_name)
    anonymized_text, raw_results = tool.process_text(text)
    return anonymized_text, raw_results, config


def detect_file_kind(file_path: str | Path) -> str:
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix in TEXT_EXTENSIONS:
        return "text"
    if suffix in IMAGE_EXTENSIONS:
        return "image"
    if suffix in AUDIO_EXTENSIONS:
        return "audio"
    if suffix in VIDEO_EXTENSIONS:
        return "video"

    guessed_mime, _ = mimetypes.guess_type(str(path))
    if guessed_mime:
        if guessed_mime.startswith("text/") or guessed_mime in {"application/json", "application/xml", "application/yaml", "application/x-yaml"}:
            return "text"
        if guessed_mime.startswith("image/"):
            return "image"
        if guessed_mime.startswith("audio/"):
            return "audio"
        if guessed_mime.startswith("video/"):
            return "video"

    return "unsupported"


def _serialise_detections(results) -> list[dict[str, object]]:
    return [
        {
            "entity_type": result.entity_type,
            "start_pos": result.start,
            "end_pos": result.end,
            "confidence": round(result.score, 2),
        }
        for result in results
    ]


def _audio_config(policy: dict) -> tuple[dict[str, str], bool, int, int, str, str | None, float, int | None, int | None, str | None, str, str | None, str, str, float, str]:
    audio_cfg = policy.get("audio", {}) if isinstance(policy, dict) else {}
    enable_conversion = bool(audio_cfg.get("enable_format_conversion", False))
    conversion_sample_rate = int(audio_cfg.get("conversion_sample_rate", 16000))
    conversion_channels = int(audio_cfg.get("conversion_channels", 1))
    whisper_model = str(audio_cfg.get("whisper_model", "small"))
    whisper_language_raw = audio_cfg.get("whisper_language")
    whisper_temperature = float(audio_cfg.get("whisper_temperature", 0.0))
    whisper_beam_size_raw = audio_cfg.get("whisper_beam_size")
    whisper_best_of_raw = audio_cfg.get("whisper_best_of")
    whisper_initial_prompt_raw = audio_cfg.get("whisper_initial_prompt")
    tts_backend = str(audio_cfg.get("tts_backend", "piper")).strip().lower()
    tts_cli_command_raw = audio_cfg.get("tts_cli_command")
    kokoro_voice = str(audio_cfg.get("kokoro_voice", "af_heart")).strip()
    kokoro_lang_code = str(audio_cfg.get("kokoro_lang_code", "a")).strip()
    kokoro_speed = float(audio_cfg.get("kokoro_speed", 1.0))
    kokoro_repo_id = str(audio_cfg.get("kokoro_repo_id", "hexgrad/Kokoro-82M")).strip()
    labels = audio_cfg.get(
        "placeholder_labels",
        {
            "PERSON": "name",
            "LOCATION": "location",
            "ID": "id",
            "EMAIL_ADDRESS": "email",
            "PHONE_NUMBER": "phone number",
            "default": "redacted",
        },
    )

    if not isinstance(labels, dict):
        raise ValueError("Audio policy placeholder_labels must be an object")
    if not isinstance(whisper_model, str) or not whisper_model:
        raise ValueError("Audio policy whisper_model must be a non-empty string")
    if tts_backend != "piper":
        raise ValueError("Audio policy tts_backend must be 'piper'")
    if not kokoro_voice:
        raise ValueError("Audio policy kokoro_voice must be a non-empty string")
    if not kokoro_lang_code:
        raise ValueError("Audio policy kokoro_lang_code must be a non-empty string")
    if kokoro_speed <= 0:
        raise ValueError("Audio policy kokoro_speed must be > 0")
    if not kokoro_repo_id:
        raise ValueError("Audio policy kokoro_repo_id must be a non-empty string")

    labels_normalized: dict[str, str] = {
        str(key): str(value)
        for key, value in labels.items()
    }

    if whisper_language_raw in (None, "", "auto"):
        whisper_language = None
    else:
        whisper_language = str(whisper_language_raw)
    if whisper_beam_size_raw in (None, ""):
        whisper_beam_size = None
    else:
        whisper_beam_size = int(whisper_beam_size_raw)
    if whisper_best_of_raw in (None, ""):
        whisper_best_of = None
    else:
        whisper_best_of = int(whisper_best_of_raw)
    whisper_initial_prompt = None if whisper_initial_prompt_raw in (None, "") else str(whisper_initial_prompt_raw)
    tts_cli_command = None if tts_cli_command_raw is None else str(tts_cli_command_raw)

    if not tts_cli_command or not tts_cli_command.strip():
        raise ValueError("Audio policy tts_cli_command is required when tts_backend='piper'")

    return (
        labels_normalized,
        enable_conversion,
        conversion_sample_rate,
        conversion_channels,
        whisper_model,
        whisper_language,
        whisper_temperature,
        whisper_beam_size,
        whisper_best_of,
        whisper_initial_prompt,
        tts_backend,
        tts_cli_command,
        kokoro_voice,
        kokoro_lang_code,
        kokoro_speed,
        kokoro_repo_id,
    )


def _anonymized_filename(file_path: Path) -> str:
    return f"{file_path.stem}.anonymized{file_path.suffix}"


def _report_filename(file_path: Path) -> str:
    return f"{file_path.stem}.report.json"


def _derive_output_path(
    input_path: Path,
    output_path: str | Path | None = None,
    output_dir: str | Path | None = None,
    input_root: str | Path | None = None,
) -> Path:
    if output_path is not None:
        return Path(output_path)

    if input_root is not None and output_dir is not None:
        relative_path = input_path.relative_to(Path(input_root))
        return Path(output_dir) / relative_path.parent / _anonymized_filename(relative_path)

    if output_dir is not None:
        return Path(output_dir) / _anonymized_filename(input_path)

    return input_path.with_name(_anonymized_filename(input_path))


def _derive_report_path(
    input_path: Path,
    output_path: Path | None = None,
    output_dir: str | Path | None = None,
    input_root: str | Path | None = None,
) -> Path:
    if output_path is not None:
        return output_path.with_name(_report_filename(output_path))

    if input_root is not None and output_dir is not None:
        relative_path = input_path.relative_to(Path(input_root))
        return Path(output_dir) / relative_path.parent / _report_filename(relative_path)

    if output_dir is not None:
        return Path(output_dir) / _report_filename(input_path)

    return input_path.with_name(_report_filename(input_path))


def _write_report(report_path: Path, result: FileProcessingResult) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8") as file_handle:
        json.dump(asdict(result), file_handle, indent=2, ensure_ascii=False)


def process_input_file(
    input_path: str | Path,
    policy_name: str = "light",
    output_path: str | Path | None = None,
    output_dir: str | Path | None = None,
    input_root: str | Path | None = None,
) -> FileProcessingResult:
    path = Path(input_path)
    detected_kind = detect_file_kind(path)
    target_output_path = _derive_output_path(path, output_path=output_path, output_dir=output_dir, input_root=input_root)
    report_path = _derive_report_path(path, output_path=Path(target_output_path) if target_output_path else None, output_dir=output_dir, input_root=input_root)

    if detected_kind not in {"text", "audio"}:
        result = FileProcessingResult(
            input_path=str(path),
            detected_kind=detected_kind,
            status="skipped",
            policy_name=policy_name,
            output_path=None,
            report_path=str(report_path),
            detections=[],
            message=f"{detected_kind} processing is not implemented yet",
        )
        _write_report(report_path, result)
        return result

    try:
        if detected_kind == "audio":
            ensure_ffmpeg_available()

        if detected_kind == "text":
            source_text = path.read_text(encoding="utf-8", errors="replace")
            anonymized_text, raw_results, config = process_text_content(source_text, policy_name)

            target_output_path.parent.mkdir(parents=True, exist_ok=True)
            target_output_path.write_text(anonymized_text, encoding="utf-8")
            log_redaction(raw_results, config["policy_name"])

            result = FileProcessingResult(
                input_path=str(path),
                detected_kind=detected_kind,
                status="processed",
                policy_name=config["policy_name"],
                output_path=str(target_output_path),
                report_path=str(report_path),
                detections=_serialise_detections(raw_results),
            )
        else:
            tool, config = build_anonymizer(policy_name)
            (
                labels,
                enable_conversion,
                conversion_sample_rate,
                conversion_channels,
                whisper_model,
                whisper_language,
                whisper_temperature,
                whisper_beam_size,
                whisper_best_of,
                whisper_initial_prompt,
                tts_backend,
                tts_cli_command,
                kokoro_voice,
                kokoro_lang_code,
                kokoro_speed,
                kokoro_repo_id,
            ) = _audio_config(config)

            output_audio_path = resolve_audio_output_path(path, target_output_path)
            report_path = output_audio_path.with_name(_report_filename(output_audio_path))

            working_audio_input = path
            working_audio_output = output_audio_path
            converted_input: Path | None = None
            converted_output: Path | None = None
            message: str | None = None

            if path.suffix.lower() != ".wav":
                if not enable_conversion:
                    result = FileProcessingResult(
                        input_path=str(path),
                        detected_kind=detected_kind,
                        status="skipped",
                        policy_name=policy_name,
                        output_path=None,
                        report_path=str(report_path),
                        detections=[],
                        message="audio processing currently supports only .wav files unless format conversion is enabled in policy",
                    )
                    _write_report(report_path, result)
                    return result

                converted_input = convert_audio_to_wav(
                    input_path=path,
                    sample_rate=conversion_sample_rate,
                    channels=conversion_channels,
                )
                converted_output = output_audio_path.with_suffix(".tmp.anonymized.wav")
                working_audio_input = converted_input
                working_audio_output = converted_output

            try:
                detections, message, anonymized_text = process_audio_with_whisper(
                    audio_path=working_audio_input,
                    output_audio_path=working_audio_output,
                    anonymizer_tool=tool,
                    whisper_model=whisper_model,
                    whisper_language=whisper_language,
                    whisper_temperature=whisper_temperature,
                    whisper_beam_size=whisper_beam_size,
                    whisper_best_of=whisper_best_of,
                    whisper_initial_prompt=whisper_initial_prompt,
                    labels=labels,
                    tts_backend=tts_backend,
                    tts_cli_command=tts_cli_command,
                    kokoro_voice=kokoro_voice,
                    kokoro_lang_code=kokoro_lang_code,
                    kokoro_speed=kokoro_speed,
                    kokoro_repo_id=kokoro_repo_id,
                )
            finally:
                cleanup_temp_audio(converted_input)
                if converted_output is not None:
                    if message is None:
                        # Guard: ensure the synthesized wav exists before attempting transcode.
                        try:
                            converted_path = Path(converted_output)
                            exists = converted_path.exists()
                        except Exception:
                            exists = False

                        if not exists:
                            try:
                                parent = Path(converted_output).parent
                                listing = ", ".join([p.name for p in parent.iterdir()])
                            except Exception:
                                listing = "<unable to list directory>"
                            raise RuntimeError(
                                f"Expected synthesized WAV missing before transcode: {converted_output}. Parent listing: {listing}"
                            )

                        print(f"[FilePipeline] transcoding synthesized WAV: {converted_output} -> {output_audio_path}")
                        transcode_wav_to_audio(converted_output, output_audio_path)
                    cleanup_temp_audio(converted_output)

            if message is not None:
                result = FileProcessingResult(
                    input_path=str(path),
                    detected_kind=detected_kind,
                    status="skipped",
                    policy_name=config["policy_name"],
                    output_path=None,
                    report_path=str(report_path),
                    detections=[],
                    message=message,
                )
            else:
                transcript_output_path = output_audio_path.with_suffix(".txt")
                transcript_output_path.write_text(anonymized_text, encoding="utf-8")
                result = FileProcessingResult(
                    input_path=str(path),
                    detected_kind=detected_kind,
                    status="processed",
                    policy_name=config["policy_name"],
                    output_path=str(output_audio_path),
                    report_path=str(report_path),
                    detections=detections,
                )
    except Exception as exc:
        result = FileProcessingResult(
            input_path=str(path),
            detected_kind=detected_kind,
            status="error",
            policy_name=policy_name,
            output_path=None,
            report_path=str(report_path),
            detections=[],
            message=f"Error processing file: {exc}",
        )

    _write_report(report_path, result)
    return result


def process_input_directory(
    input_dir: str | Path,
    policy_name: str = "light",
    output_dir: str | Path | None = None,
    recursive: bool = False,
) -> list[FileProcessingResult]:
    source_dir = Path(input_dir)
    target_dir = Path(output_dir) if output_dir is not None else source_dir.parent / f"{source_dir.name}_anonymized"
    iterator: Iterable[Path] = source_dir.rglob("*") if recursive else source_dir.iterdir()

    results: list[FileProcessingResult] = []
    for path in sorted(item for item in iterator if item.is_file()):
        results.append(
            process_input_file(
                path,
                policy_name=policy_name,
                output_dir=target_dir,
                input_root=source_dir,
            )
        )

    return results