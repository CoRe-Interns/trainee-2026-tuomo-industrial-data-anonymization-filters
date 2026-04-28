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


def diagnose_whisper_transcription(audio_path: str, language: str = "fi", model_name: str = "base"):
    """
    Diagnostic helper to check what Whisper actually transcribes from an audio file.
    Run this manually to debug audio-to-text issues before they reach anonymization.
    
    Usage:
        python -c "from tests.test_gui_app import diagnose_whisper_transcription; diagnose_whisper_transcription('data/input/TestiTallenne.m4a')"
    """
    from pathlib import Path
    from src.modalities.audio.speech_to_text import transcribe_audio_with_whisper
    from src.modalities.audio.conversion import convert_audio_to_wav
    from src.modalities.audio.wav_ops import read_wav
    
    print(f"\n{'='*60}")
    print(f"Whisper Transcription Diagnostic")
    print(f"{'='*60}\n")
    print(f"Input: {audio_path}")
    print(f"Model: {model_name}")
    print(f"Language: {language}\n")
    
    input_file = Path(audio_path)
    if not input_file.exists():
        print(f"ERROR: File not found: {audio_path}")
        return
    
    print(f"File size: {input_file.stat().st_size} bytes")
    print(f"Format: {input_file.suffix}\n")
    
    # Check conversion if non-WAV
    if input_file.suffix.lower() != ".wav":
        print("Converting to WAV for Whisper...")
        try:
            wav_path = convert_audio_to_wav(audio_path, sample_rate=16000, channels=1)
            wav_data = read_wav(wav_path)
            print(f"  Duration: {wav_data.duration_s:.2f}s")
            print(f"  Format: {wav_data.channels}ch, {wav_data.frame_rate}Hz, {wav_data.sample_width*8}-bit\n")
        except Exception as e:
            print(f"  ERROR during conversion: {e}\n")
            return
    
    print("Running Whisper transcription...")
    try:
        transcript = transcribe_audio_with_whisper(
            audio_path=audio_path,
            model_name=model_name,
            language=language,
        )
    except Exception as e:
        print(f"ERROR during transcription: {e}")
        return
    
    print(f"\n{'='*60}")
    print(f"Transcribed Text:")
    print(f"{'='*60}")
    print(transcript.text)
    print(f"\n{'='*60}")
    print(f"Word-level Tokens ({len(transcript.tokens)} total):")
    print(f"{'='*60}\n")
    
    for i, token in enumerate(transcript.tokens, 1):
        print(f"{i:3d}. [{token.start_time_s:6.2f}s–{token.end_time_s:6.2f}s] {token.text}")
    
    print(f"\n{'='*60}")
    if not transcript.tokens:
        print("WARNING: No tokens extracted. Whisper may have hallucinated or failed to parse audio.")
    elif len(transcript.tokens) < 3:
        print("WARNING: Very few tokens. Audio quality or format may be an issue.")
    print(f"{'='*60}\n")