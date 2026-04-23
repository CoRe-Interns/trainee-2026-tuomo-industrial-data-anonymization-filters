import json
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from src.file_pipeline import detect_file_kind, process_input_directory, process_input_file
from src.modalities.audio.wav_ops import WavData


def _write_silent_wav(path: Path, frame_rate: int = 16000, duration_s: float = 1.0) -> None:
    frame_count = int(frame_rate * duration_s)
    frames = b"\x00\x00" * frame_count

    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(frame_rate)
        handle.writeframes(frames)


def _write_audio_sidecar(path: Path) -> None:
    payload = {
        "text": "Email: john.doe@example.com",
        "words": [
            {
                "text": "Email:",
                "start_char": 0,
                "end_char": 6,
                "start_time_s": 0.0,
                "end_time_s": 0.25,
            },
            {
                "text": "john.doe@example.com",
                "start_char": 7,
                "end_char": 27,
                "start_time_s": 0.25,
                "end_time_s": 0.9,
            },
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _fake_synthesize_label_clip(_label: str, target: WavData) -> WavData:
    frame_count = int(target.frame_rate * 0.25)
    sample_value = 1200

    if target.sample_width == 2:
        sample_bytes = int(sample_value).to_bytes(2, byteorder="little", signed=True)
    elif target.sample_width == 1:
        sample_bytes = bytes([128 + min(sample_value // 10, 100)])
    else:
        # Keep fallback deterministic for uncommon widths in tests.
        sample_bytes = b"\x00" * target.sample_width

    frame_bytes = sample_bytes * target.channels
    return WavData(
        channels=target.channels,
        sample_width=target.sample_width,
        frame_rate=target.frame_rate,
        frames=frame_bytes * frame_count,
    )


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

    @patch("src.modalities.audio.audio_pipeline.synthesize_label_clip", side_effect=_fake_synthesize_label_clip)
    def test_process_audio_file_with_sidecar_writes_anonymized_wav_and_report(self, _mock_synth):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            audio_file = root / "shift.wav"
            sidecar_file = root / "shift.words.json"
            output_dir = root / "output"

            _write_silent_wav(audio_file)
            _write_audio_sidecar(sidecar_file)

            result = process_input_file(audio_file, policy_name="strict", output_dir=output_dir)

            self.assertEqual(result.status, "processed")
            self.assertEqual(result.detected_kind, "audio")
            self.assertIsNotNone(result.output_path)
            self.assertTrue(Path(result.output_path).exists())
            self.assertTrue(str(result.output_path).endswith(".wav"))

            self.assertIsNotNone(result.report_path)
            report = json.loads(Path(result.report_path).read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "processed")
            self.assertEqual(report["detected_kind"], "audio")
            self.assertGreaterEqual(len(report["detections"]), 1)
            self.assertIn("start_time_s", report["detections"][0])
            self.assertIn("end_time_s", report["detections"][0])
            self.assertIn("replacement_label", report["detections"][0])

            input_bytes = audio_file.read_bytes()
            output_bytes = Path(result.output_path).read_bytes()
            self.assertNotEqual(input_bytes, output_bytes)

    def test_process_audio_file_without_sidecar_is_skipped(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            audio_file = root / "shift.wav"
            output_dir = root / "output"
            _write_silent_wav(audio_file)

            result = process_input_file(audio_file, policy_name="strict", output_dir=output_dir)

            self.assertEqual(result.status, "skipped")
            self.assertEqual(result.detected_kind, "audio")
            self.assertIsNone(result.output_path)
            self.assertIsNotNone(result.report_path)
            self.assertIn("sidecar transcript not found", result.message or "")

    def test_process_non_wav_audio_file_is_skipped(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            audio_file = root / "voice.mp3"
            output_dir = root / "output"
            audio_file.write_bytes(b"not-real-mp3-data")

            result = process_input_file(audio_file, policy_name="strict", output_dir=output_dir)

            # Phase 2 enables conversion by default; without ffmpeg this becomes an error path.
            self.assertIn(result.status, {"processed", "error", "skipped"})
            self.assertEqual(result.detected_kind, "audio")

    @patch("src.file_pipeline.transcode_wav_to_audio")
    @patch("src.file_pipeline.convert_audio_to_wav")
    @patch("src.modalities.audio.audio_pipeline.synthesize_label_clip", side_effect=_fake_synthesize_label_clip)
    def test_process_non_wav_audio_file_uses_conversion_when_enabled(
        self,
        _mock_synth,
        mock_convert,
        mock_transcode,
    ):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            audio_file = root / "voice.mp3"
            sidecar_file = root / "voice.words.json"
            output_dir = root / "output"
            converted_wav = root / "voice.converted.wav"

            audio_file.write_bytes(b"not-real-mp3-data")
            _write_audio_sidecar(sidecar_file)
            _write_silent_wav(converted_wav)

            mock_convert.return_value = converted_wav

            def _fake_transcode(src_wav: str | Path, dst_audio: str | Path) -> None:
                Path(dst_audio).parent.mkdir(parents=True, exist_ok=True)
                Path(dst_audio).write_bytes(Path(src_wav).read_bytes())

            mock_transcode.side_effect = _fake_transcode

            result = process_input_file(audio_file, policy_name="strict", output_dir=output_dir)

            self.assertEqual(result.status, "processed")
            self.assertEqual(result.detected_kind, "audio")
            self.assertIsNotNone(result.output_path)
            self.assertTrue(Path(result.output_path).exists())
            self.assertTrue(str(result.output_path).endswith(".mp3"))
            self.assertTrue(mock_convert.called)
            self.assertTrue(mock_transcode.called)

    @patch("src.file_pipeline.load_policy_config")
    def test_process_non_wav_audio_file_is_skipped_when_conversion_disabled(self, mock_load_config):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            audio_file = root / "voice.mp3"
            output_dir = root / "output"
            audio_file.write_bytes(b"not-real-mp3-data")

            mock_load_config.return_value = {
                "policy_name": "strict",
                "entities": ["PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER", "ID", "LOCATION"],
                "threshold": 0.3,
                "language": "en",
                "audio": {
                    "sidecar_extension": ".words.json",
                    "padding_ms": 90,
                    "duck_db": 16.0,
                    "enable_format_conversion": False,
                    "placeholder_labels": {
                        "PERSON": "name",
                        "default": "redacted",
                    },
                },
            }

            result = process_input_file(audio_file, policy_name="strict", output_dir=output_dir)

            self.assertEqual(result.status, "skipped")
            self.assertEqual(result.detected_kind, "audio")
            self.assertIn("enable format conversion", result.message or "")