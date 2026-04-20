import unittest

from src.file_pipeline import FileProcessingResult
from src.gui_app import format_result_line, summarize_results


class GuiHelpersTests(unittest.TestCase):
    def test_summarize_results_counts_statuses(self):
        results = [
            FileProcessingResult(input_path="a.txt", detected_kind="text", status="processed", policy_name="light"),
            FileProcessingResult(input_path="b.png", detected_kind="image", status="skipped", policy_name="light"),
            FileProcessingResult(input_path="c.txt", detected_kind="text", status="error", policy_name="strict"),
        ]

        summary = summarize_results(results)

        self.assertEqual(summary.total, 3)
        self.assertEqual(summary.processed, 1)
        self.assertEqual(summary.skipped, 1)
        self.assertEqual(summary.errors, 1)

    def test_format_result_line_includes_core_fields(self):
        result = FileProcessingResult(
            input_path="sample.txt",
            detected_kind="text",
            status="processed",
            policy_name="strict",
            output_path="sample.anonymized.txt",
            report_path="sample.report.json",
            message="done",
        )

        line = format_result_line(result)

        self.assertIn("sample.txt", line)
        self.assertIn("text", line)
        self.assertIn("processed", line)
        self.assertIn("output=sample.anonymized.txt", line)
        self.assertIn("report=sample.report.json", line)
        self.assertIn("done", line)