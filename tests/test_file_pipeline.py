import json
import tempfile
import unittest
from pathlib import Path

from src.file_pipeline import detect_file_kind, process_input_directory, process_input_file


class FilePipelineTests(unittest.TestCase):
    def test_detect_file_kind_routes_text_and_media(self):
        self.assertEqual(detect_file_kind("example.txt"), "text")
        self.assertEqual(detect_file_kind("photo.png"), "image")
        self.assertEqual(detect_file_kind("audio.wav"), "audio")
        self.assertEqual(detect_file_kind("video.mp4"), "video")

    def test_process_input_file_writes_anonymized_output_and_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_file = root / "sample.txt"
            output_dir = root / "output"
            input_file.write_text("Email: jane.doe@example.com | Phone: +358401234567", encoding="utf-8")

            result = process_input_file(input_file, policy_name="strict", output_dir=output_dir)

            self.assertEqual(result.status, "processed")
            self.assertEqual(result.detected_kind, "text")
            self.assertIsNotNone(result.output_path)
            self.assertTrue(Path(result.output_path).exists())
            self.assertIn("[EMAIL]", Path(result.output_path).read_text(encoding="utf-8"))
            self.assertIsNotNone(result.report_path)
            report = json.loads(Path(result.report_path).read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "processed")
            self.assertEqual(report["detected_kind"], "text")
            self.assertGreaterEqual(len(report["detections"]), 2)

    def test_process_input_directory_preserves_structure_and_skips_non_text(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_dir = root / "input"
            nested_dir = input_dir / "nested"
            output_dir = root / "output"
            nested_dir.mkdir(parents=True)

            text_file = nested_dir / "note.txt"
            text_file.write_text("Name=John Doe", encoding="utf-8")
            media_file = input_dir / "photo.png"
            media_file.write_bytes(b"not a real image")

            results = process_input_directory(input_dir, policy_name="strict", output_dir=output_dir, recursive=True)

            self.assertEqual(len(results), 2)

            processed = next(item for item in results if item.detected_kind == "text")
            skipped = next(item for item in results if item.detected_kind == "image")

            self.assertEqual(processed.status, "processed")
            self.assertTrue(Path(processed.output_path).exists())
            self.assertIn("[NAME]", Path(processed.output_path).read_text(encoding="utf-8"))

            self.assertEqual(skipped.status, "skipped")
            self.assertIsNone(skipped.output_path)
            self.assertIsNotNone(skipped.report_path)
            skipped_report = json.loads(Path(skipped.report_path).read_text(encoding="utf-8"))
            self.assertEqual(skipped_report["status"], "skipped")
            self.assertIn("not implemented yet", skipped_report["message"])