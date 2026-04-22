import unittest

from src.file_pipeline import FileProcessingResult
from src.gui_app import (
    build_result_detail,
    format_result_line,
    get_text_tab_expand_rows,
    summarize_results,
)


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

    def test_build_result_detail_includes_metadata_lines(self):
        result = FileProcessingResult(
            input_path="sample.txt",
            detected_kind="text",
            status="processed",
            policy_name="strict",
            output_path="sample.anonymized.txt",
            report_path="sample.report.json",
            message="ok",
        )

        detail = build_result_detail(result)

        self.assertIn("Input: sample.txt", detail)
        self.assertIn("Kind: text", detail)
        self.assertIn("Status: processed", detail)
        self.assertIn("Policy: strict", detail)
        self.assertIn("Output: sample.anonymized.txt", detail)
        self.assertIn("Report: sample.report.json", detail)
        self.assertIn("Message: ok", detail)

    def test_text_tab_expand_rows_include_input_and_output(self):
        input_row, output_row = get_text_tab_expand_rows()

        self.assertEqual(input_row, 1)
        self.assertEqual(output_row, 3)