import argparse
import os

from src.file_pipeline import (
    FileProcessingResult,
    load_policy_config,
    process_input_directory,
    process_input_file,
    process_text_content,
)
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
        result = process_input_file(
            args.input_file,
            policy_name=args.policy,
            output_path=args.output_file,
            output_dir=args.output_dir,
        )
        _print_file_result(result)
    else:
        results = process_input_directory(
            args.input_dir,
            policy_name=args.policy,
            output_dir=args.output_dir or DEFAULT_OUTPUT_DIR,
            recursive=args.recursive,
        )
        for result in results:
            _print_file_result(result)