# Industrial Data Anonymization Filters

Prototype a local-first anonymization toolkit that makes industrial pilot data safer to share and process by removing or masking personal information from text, images, video, and audio while preserving as much operational utility as possible.

Real industrial data often includes sensitive personal information such as faces in video, name tags, spoken names, phone numbers, IDs, and email addresses. This work focuses on building practical anonymization filters that run locally or on-device, helping companies use data for internal pilots without unnecessary privacy risks.

Outputs: anonymization toolkit/CLI or service + policy-based filtering modes, text/image/video/audio anonymization pipelines, audit log format and redaction reports, before/after examples, utility-impact notes, and deployment guidance for on-prem vs cloud processing.

## Student will do

- Implement personal-data removal in text:
  - detect emails, phone numbers, IDs, and similar structured data with simple patterns
  - detect person names with NER models
  - replace findings with placeholders such as `[NAME1]`, `[EMAIL1]`, `[ID1]`
  - log what was changed in an audit trail
- Use common Python libraries for anonymization such as:
  - `presidio-analyzer`
  - `presidio-anonymizer`
  - `spaCy`
  - `re`
  - `hmac`
- Package the solution as a CLI and/or local service with:
  - policy modes such as `strict` and `light`
  - configuration files for redaction behavior
- Optimize processing for on-device / edge deployment in privacy-critical environments
- Implement voice anonymization for audio
- Build face and badge blurring for images and videos
- Log what was redacted, where applicable, together with confidence levels

## Expected outputs

- Anonymization toolkit with sample configs and audit log format
- Before/after samples for text, image, video, and audio cases
- Short impact report on downstream model/data usefulness after anonymization
- Guidelines for choosing on-prem vs cloud processing approaches

## Optional extensions

- Integrate with a transcription pipeline and anonymize private information in transcripts produced from audio
- Assess utility loss on downstream tasks such as pose estimation or quality control before vs after anonymization