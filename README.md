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
|   |      |-- transcript_mapping.py # Text-span to time-span mapping
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

Process audio (WAV + sidecar transcript):

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

Audio anonymization is implemented as audio-to-audio masking with spoken placeholders.

- Input audio remains audio and produces anonymized audio output.
- Sensitive spoken content is replaced by spoken placeholder labels (for example `name`, `location`, `email`).
- Original voice is ducked under detected redaction intervals.
- Processing currently requires a timestamped sidecar transcript file next to the audio.

Supported audio processing modes:

- Native `.wav` processing (default direct path).
- Optional non-WAV conversion path (`.mp3`, `.m4a`, `.flac`, `.ogg`, `.aac`, `.opus`) via local `ffmpeg`.

Required sidecar naming:

- `shift.wav` -> `shift.words.json`
- `shift.mp3` -> `shift.words.json`

Sidecar JSON format:

```json
{
  "text": "Email: john.doe@example.com",
  "words": [
    {
      "text": "Email:",
      "start_char": 0,
      "end_char": 6,
      "start_time_s": 0.0,
      "end_time_s": 0.25
    },
    {
      "text": "john.doe@example.com",
      "start_char": 7,
      "end_char": 27,
      "start_time_s": 0.25,
      "end_time_s": 0.9
    }
  ]
}
```

Phase 2 conversion notes:

- Non-WAV formats are converted to temporary WAV for anonymization and transcoded back to the original extension.
- Conversion requires local `ffmpeg` available on `PATH`.
- Conversion behavior is controlled by `configs/policy.json` under `audio.enable_format_conversion`.

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
- Prefer local-first processing and explicit auditability.

## Versions

Current implementation notes:

- Text anonymization is implemented.
- File-based input/output processing is implemented for text files.
- File type recognition is implemented for routing text, image, audio, and video files.
- Policies are implemented via a single JSON config file with mode-based thresholds.
- Audit logging is implemented to `data/audit_log.csv`.
- Audio anonymization is implemented for `.wav` files with timestamped sidecar transcripts and spoken placeholder masking.
- Phase 2 adds optional non-WAV conversion flow via `ffmpeg` while preserving original output extension.
- Image and video files are currently routed and reported as not implemented.

Planned next steps:

- Add UI on top of stable pipeline contracts.
- Add audio anonymization.
- Add image anonymization.
- Add video anonymization.
