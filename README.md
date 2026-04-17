# Industrial Data Anonymization Filters

This repository contains a local-first anonymization prototype for industrial pilot data.
The current implementation focuses on text anonymization with policy-based behavior,
deterministic placeholders, and CSV audit logging.

## Current scope

- Text anonymization is implemented.
- Policies are implemented via JSON configs (`light` and `strict`).
- Audit logging is implemented to `data/audit_log.csv`.
- Image, video, and audio anonymization are planned but not implemented yet.

## Repository structure

```text
.
|-- main.py                     # CLI entrypoint
|-- configs/
|   |-- light.json             # Light policy
|   `-- strict.json            # Strict policy
|-- src/
|   |-- anonymizer.py          # Presidio + custom recognizers
|   `-- logger.py              # Audit log writer
|-- tests/
|   |-- test_text_anonymization.py
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

Arguments:

- `--text` (required): input text to anonymize.
- `--policy` (optional): `light` or `strict` (default: `light`).

Example output:

- anonymized text in terminal
- appended rows in `data/audit_log.csv`

## Policy behavior

- `light` policy:
  - focuses on common entities (`PERSON`, `EMAIL_ADDRESS`, `PHONE_NUMBER`, `LOCATION`)
  - higher threshold than strict policy
- `strict` policy:
  - includes additional high-risk entities (`ID`, `CREDIT_CARD`, `IBAN_CODE`, `IP_ADDRESS`)
  - lower threshold for broader detection

Policy files:

- `configs/light.json`
- `configs/strict.json`

## Test and validation

Run unit tests:

```bash
python -m pytest -q
```

Run sample text cases:

```bash
python tests/run_text_anonymization_cases.py
```

## Output and audit log format

Audit log file: `data/audit_log.csv`

Columns:

- `timestamp`
- `policy`
- `entity_type`
- `start_pos`
- `end_pos`
- `confidence`

## Roadmap

Planned next steps:

- Add file-based input/output pipeline with file type recognition.
- Preserve existing CLI text mode while adding file/folder processing mode.
- Add UI on top of stable pipeline contracts.
- Add audio anonymization.
- Add image anonymization.
- Add video anonymization.

## Notes for contributors

- Keep changes small and focused.
- Update this README whenever behavior, CLI arguments, configs, or outputs change.
- Prefer local-first processing and explicit auditability.
