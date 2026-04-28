# Industrial Data Anonymization Filters

This repository contains a local-first anonymization prototype for industrial pilot data.
The current implementation focuses on text anonymization with policy-based behavior, deterministic placeholders, CSV audit logging, and file-based text processing with file-type routing.

## Repository structure

```text
.
|-- main.py                     # CLI entrypoint
|-- roadmap.md                  # Canonical project roadmap
|-- configs/
|   `-- policy.json            # Shared entity set and per-mode thresholds
|-- src/
|   |-- anonymizer.py          # Presidio + custom recognizers
|   |-- file_pipeline.py       # File routing and text file processing
|   |-- modalities/
|   |   `-- audio/
|   |      |-- audio_pipeline.py     # Audio processing orchestration
|   |      |-- conversion.py         # Optional ffmpeg-based format conversion
|   |      |-- speech_to_text.py     # Whisper transcription and timing helpers
|   |      |-- tts_overlay.py        # Spoken placeholder synthesis + overlay
|   |      `-- wav_ops.py            # WAV read/write and ducking operations
|   `-- logger.py              # Audit log writer
|-- tests/
|   |-- test_text_anonymization.py
|   |-- test_file_pipeline.py
|   `-- run_text_anonymization_cases.py
`-- data/
    `-- audit_log.csv          # Generated/appended at runtime
```

## Requirements

- Python 3.10+ recommended
- Local environment with ability to install dependencies from `requirements.txt`

Install dependencies:

```bash
pip install -r requirements.txt
```

## How to run

Run anonymization from CLI:

```bash
python main.py --text "Operator: John Carter | Email: john.carter@acme.com | Phone: +358401234567" --policy strict
```

Process a single file:

```bash
python main.py --input-file data/input/sample.txt --output-file data/output/sample.anonymized.txt --policy strict
```

Process audio with automatic Whisper transcription:

```bash
python main.py --input-file data/input/shift.wav --output-dir data/output --policy strict
```

Process a directory:

```bash
python main.py --input-dir data/input --output-dir data/output --recursive --policy light
```

Use default folders (recommended):

```bash
python main.py --batch --policy strict
```

Open the desktop UI:

```bash
python main.py --ui
```

This reads files from `data/input` and writes anonymized files and reports to `data/output`.

You can also run without mode flags and it will use the same default folders:

```bash
python main.py --policy strict
```

Arguments

- `--text` (required): anonymize input text.
- `--input-file`: anonymize a single file.
- `--input-dir`: anonymize files in a directory.
- `--batch`: process the default folders (`data/input` -> `data/output`).
- `--ui`: open the desktop UI.
- `--output-file`: target file for a single-file run.
- `--output-dir`: target directory for file or directory runs.
- `--recursive`: process nested files in directory mode.
- `--policy` (optional): `light` or `strict` (default: `light`).

## Desktop UI

The desktop app has two working areas:

- Text tab for pasting text and anonymizing it immediately.
- Folder Batch tab for processing the `data/input` folder into `data/output`.

The app opens on the Folder Batch tab by default.

Batch tab highlights:

- run summary with total/processed/skipped/error counts
- selectable results table for each processed or skipped file
- preview panel for selected result details and anonymized output snippets
- quick button to open the output folder

The UI uses the same pipeline and policies as the CLI, so output files and audit logging stay consistent.

## Audio anonymization

Audio anonymization is implemented as a speech-to-speech pipeline.

- Input audio is transcribed to text with Whisper.
- Sensitive content is detected and anonymized in text using the same policy engine as text files.
- The anonymized transcript is normalized for speech output and synthesized back to audio as one continuous utterance.
- The synthesized audio is trimmed or padded to match the source duration so output length stays aligned with the input file.

Supported audio processing modes:

- Native `.wav` processing.
- Optional non-WAV conversion path (`.mp3`, `.m4a`, `.flac`, `.ogg`, `.aac`, `.opus`) via local `ffmpeg`.

Whisper configuration:

- `audio.whisper_model` selects the Whisper model name, for example `small`.
- `audio.whisper_language` sets the transcription language hint. Omit it or set it to `auto` to let Whisper detect the language automatically.
- `audio.tts_backend` is fixed to `piper`.
- `audio.tts_cli_command` provides the Piper CLI command template.
  - The template can use `{text}`, `{input_text_file}`, and `{output_wav}` placeholders.
- `ffmpeg` is required for Whisper transcription and for optional audio format conversion.
- The app automatically tries common Windows ffmpeg install locations, including the WinGet package path, so UI sessions usually work without manually editing PATH.
- For audio files, an explicit `--output-file` suffix is kept and the anonymized marker is inserted before that extension.

Phase 2 conversion notes:

- Non-WAV formats are converted to temporary WAV for transcription and anonymization, then transcoded back to the original extension.
- Conversion requires local `ffmpeg` available on `PATH`.
- Conversion behavior is controlled by `configs/policy.json` under `audio.enable_format_conversion`.

Piper notes:

- Piper is the only supported TTS backend.
- Install dependencies from `requirements.txt` before running audio anonymization.
- `audio.tts_cli_command` must point to a working Piper command that includes a model/config pair.
- For mixed-language or Finnish/English recordings, the default auto-detection path is preferred over forcing a single language hint.

## Policy behavior

- `light` policy:
  - pseudonymizes detected values with stable placeholders per distinct value (for example `[NAME1]`, `[EMAIL1]`)
  - assigns pseudonym indices by first appearance in text (left to right)
  - uses the shared entity set from `configs/policy.json`
  - keeps industrial numeric location labels (for example `Helsinki Plant Unit 3`) as location candidates
  - detects both labeled and unlabeled industrial location phrases (for example `at Helsinki Plant Unit 3`)
  - preserves surrounding prepositions in text (for example `at [SITE]`)
  - higher threshold than strict policy
- `strict` policy:
  - anonymizes detected values with generic non-indexed placeholders (for example `[NAME]`, `[EMAIL]`, `[PHONE]`, `[ID]`)
  - detects worker-style IDs such as `EMP-FI-1102`, `FI-8821`, `TECH-12`, and `INSP-91`
  - lower threshold for broader detection

Policy files:

- `configs/policy.json`

The shared entity set currently includes `PERSON`, `EMAIL_ADDRESS`, `PHONE_NUMBER`, `ID`, `CREDIT_CARD`, `IBAN_CODE`, `IP_ADDRESS`, and `LOCATION`.

## Test and validation

Run unit tests:

```bash
python -m pytest -q
```

Run sample text cases:

```bash
python tests/run_text_anonymization_cases.py
```

The sample case runner uses the same shared policy loader as CLI and UI and reads mode thresholds from `configs/policy.json`.

## Output and audit log format

Audit log file: `data/audit_log.csv`

Per-file report file: `*.report.json` next to each generated anonymized file or routed input file.

Columns:

- `timestamp`
- `policy`
- `entity_type`
- `start_pos`
- `end_pos`
- `confidence`

## Notes for contributors

- Keep changes small and focused.

## Versions

Current implementation notes:

- Text anonymization is implemented.
- File-based input/output processing is implemented for text files.
- File type recognition is implemented for routing text, image, audio, and video files.
- Policies are implemented via a single JSON config file with mode-based thresholds.
- Audit logging is implemented to `data/audit_log.csv`.
- Audio anonymization is implemented for `.wav` files with automatic Whisper transcription, text anonymization, and speech re-synthesis.
- Phase 2 adds optional non-WAV conversion flow via `ffmpeg` while preserving original output extension.
- Image and video files are currently routed and reported as not implemented.

Planned next steps:

- Add UI on top of stable pipeline contracts.
- Add image anonymization.
- Add video anonymization.
