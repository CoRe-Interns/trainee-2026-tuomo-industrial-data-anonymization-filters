import argparse
import os
from pathlib import Path

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

from src.file_pipeline import (
    FileProcessingResult,
    detect_file_kind,
    process_input_directory,
    process_input_file,
    process_text_content,
)
from src.modalities.audio.conversion import ensure_ffmpeg_available
from src.logger import log_redaction

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_INPUT_DIR = os.path.join(PROJECT_ROOT, "data", "input")
DEFAULT_OUTPUT_DIR = os.path.join(PROJECT_ROOT, "data", "output")


def run_anonymization(input_text, policy_name="light"):
    result_text, raw_results, config = process_text_content(input_text, policy_name)

    log_redaction(raw_results, config["policy_name"])

    print("\n--- RESULT ---")
    print(f"Anonymized: {result_text}")
    print("--------------\n")


def _print_file_result(result: FileProcessingResult):
    print("\n--- FILE RESULT ---")
    print(f"Input: {result.input_path}")
    print(f"Kind: {result.detected_kind}")
    print(f"Status: {result.status}")
    if result.output_path:
        print(f"Output: {result.output_path}")
    if result.report_path:
        print(f"Report: {result.report_path}")
    if result.message:
        print(f"Message: {result.message}")
    print("-------------------\n")


def _run_ffmpeg_preflight_for_inputs(policy_name: str, input_paths: list[str]) -> None:
    needs_audio = any(detect_file_kind(path) == "audio" for path in input_paths)
    if not needs_audio:
        return

    try:
        ensure_ffmpeg_available()
    except RuntimeError as exc:
        raise ValueError(
            f"{exc}. Install ffmpeg before processing audio files"
        )


def _collect_input_files(input_dir: str, recursive: bool) -> list[str]:
    root = Path(input_dir)
    if not root.exists():
        return []

    iterator = root.rglob("*") if recursive else root.iterdir()
    return [str(path) for path in iterator if path.is_file()]

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run text anonymization")
    mode = parser.add_mutually_exclusive_group(required=False)
    mode.add_argument("--text", help="Input text to anonymize")
    mode.add_argument("--input-file", help="Input file to anonymize")
    mode.add_argument("--input-dir", help="Input directory to anonymize")
    mode.add_argument("--batch", action="store_true", help="Process default data/input to data/output")
    mode.add_argument("--ui", action="store_true", help="Open the desktop UI")
    parser.add_argument("--output-file", help="Output file for --input-file mode")
    parser.add_argument("--output-dir", help="Output directory for --input-file or --input-dir mode")
    parser.add_argument("--recursive", action="store_true", help="Recursively process files under --input-dir")
    parser.add_argument(
        "--policy",
        default="light",
        choices=["light", "strict"],
        help="Anonymization policy to use",
    )
    args = parser.parse_args()

    if args.output_file and (args.batch or args.input_dir):
        parser.error("--output-file can be used only with --input-file")

    if args.ui:
        from src.gui_app import launch_app

        launch_app()
        raise SystemExit(0)

    run_default_batch = (
        args.batch
        or (args.text is None and args.input_file is None and args.input_dir is None)
    )

    if run_default_batch:
        if not os.path.isdir(DEFAULT_INPUT_DIR):
            parser.error(f"Default input folder does not exist: {DEFAULT_INPUT_DIR}")

        try:
            _run_ffmpeg_preflight_for_inputs(
                policy_name=args.policy,
                input_paths=_collect_input_files(DEFAULT_INPUT_DIR, recursive=True),
            )
        except ValueError as exc:
            parser.error(str(exc))

        output_dir = args.output_dir or DEFAULT_OUTPUT_DIR
        os.makedirs(output_dir, exist_ok=True)

        results = process_input_directory(
            DEFAULT_INPUT_DIR,
            policy_name=args.policy,
            output_dir=output_dir,
            recursive=True,
        )
        if not results:
            print(f"No files found in input folder: {DEFAULT_INPUT_DIR}")
        for result in results:
            _print_file_result(result)
    elif args.text is not None:
        run_anonymization(input_text=args.text, policy_name=args.policy)
    elif args.input_file is not None:
        try:
            _run_ffmpeg_preflight_for_inputs(policy_name=args.policy, input_paths=[args.input_file])
        except ValueError as exc:
            parser.error(str(exc))

        result = process_input_file(
            args.input_file,
            policy_name=args.policy,
            output_path=args.output_file,
            output_dir=args.output_dir,
        )
        _print_file_result(result)
    else:
        try:
            _run_ffmpeg_preflight_for_inputs(
                policy_name=args.policy,
                input_paths=_collect_input_files(args.input_dir, recursive=args.recursive),
            )
        except ValueError as exc:
            parser.error(str(exc))

        results = process_input_directory(
            args.input_dir,
            policy_name=args.policy,
            output_dir=args.output_dir or DEFAULT_OUTPUT_DIR,
            recursive=args.recursive,
        )
        for result in results:
            _print_file_result(result)