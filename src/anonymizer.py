import re

from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer

class AnonymizerTool:
    def __init__(self, entities, threshold, policy_name="light", language="en"):
        # Initialize Presidio engines
        self.analyzer = AnalyzerEngine()
        self.entities = entities
        self.threshold = threshold
        self.policy_name = policy_name
        self.language = language
        self._register_custom_recognizers()

    def _register_custom_recognizers(self):
        phone_recognizer = PatternRecognizer(
            supported_entity="PHONE_NUMBER",
            name="custom_phone_number",
            patterns=[
                Pattern(
                    name="finnish_phone_number",
                    regex=r"(?<!\d)(?:0|\+?358)\d(?:[\s-]?\d){7,10}(?!\d)",
                    score=0.95,
                )
            ],
        )
        self.analyzer.registry.add_recognizer(phone_recognizer)

        id_recognizer = PatternRecognizer(
            supported_entity="ID",
            name="industrial_id",
            patterns=[
                Pattern(
                    name="entity_with_id_marker",
                    regex=(
                        r"(?i)\b(?:badge|employee|worker|operator|ticket|incident|work\s*order|"
                        r"order|request|visitor)\s*(?:id|number|no|#)\s*[:=#-]?\s*"
                        r"[A-Z0-9][A-Z0-9-]{2,19}\b"
                    ),
                    score=0.9,
                ),
                Pattern(
                    name="generic_id_marker",
                    regex=r"(?i)\b(?:id|badge\s*id|employee\s*id)\s*[:=#-]\s*[A-Z0-9][A-Z0-9-]{2,19}\b",
                    score=0.88,
                )
            ],
        )
        self.analyzer.registry.add_recognizer(id_recognizer)

        # Field-oriented patterns are more stable than sentence-specific cues.
        person_patterns = [
            Pattern(
                name="person_in_labeled_field",
                regex=(
                    r"(?i)\b(?:name|full\s*name|contact\s*name|operator|technician|employee|"
                    r"manager|supervisor|attn)\s*[:=]\s*[^\W\d_]+(?:[\s'-][^\W\d_]+){1,2}\b"
                ),
                score=0.8,
            ),
            Pattern(
                name="likely_finnish_lowercase_full_name",
                regex=r"(?i)\b[^\W\d_]{2,20}\s+[^\W\d_]*[äöå][^\W\d_]*\b",
                score=0.78,
            ),
        ]
        self.analyzer.registry.add_recognizer(
            PatternRecognizer(
                supported_entity="PERSON",
                name="field_person_name",
                patterns=person_patterns,
            )
        )

        location_patterns = [
            Pattern(
                name="location_in_labeled_field",
                regex=(
                    r"(?i)\b(?:location|site|city|plant|facility|address)\s*[:=]\s*"
                    r"[^\W\d_]+(?:[\s'-][^\W\d_]+){0,3}\b"
                ),
                score=0.75,
            ),
            Pattern(
                name="industrial_location_phrase",
                regex=(
                    r"(?i)(?:(?<=\bat\s)|(?<=\bin\s)|(?<=\bon\s)|(?<=\bfrom\s)|(?<=\bnear\s))"
                    r"[^\W\d_]+(?:[\s'-][^\W\d_]+){0,2}\s+"
                    r"(?:plant|facility|factory|mill|site|refinery)\b"
                    r"(?:\s+(?:unit|building|block|line|zone)\s*[-#]?\s*\d+[A-Za-z]?)?\b"
                ),
                score=0.9,
            ),
        ]
        self.analyzer.registry.add_recognizer(
            PatternRecognizer(
                supported_entity="LOCATION",
                name="field_location",
                patterns=location_patterns,
            )
        )

    def process_text(self, text):
        # 1. Analyze text and find data to anonymize
        raw_results = self.analyzer.analyze(
            text=text, 
            entities=self.entities, 
            language=self.language, 
            score_threshold=self.threshold
        )

        results = []
        for result in raw_results:
            span_text = text[result.start:result.end]
            # Drop location false positives which often overlap phone/id-style fields.
            if result.entity_type == "LOCATION":
                lowered = span_text.lower()
                has_digits = any(char.isdigit() for char in span_text)
                has_location_keyword = any(
                    keyword in lowered
                    for keyword in [
                        "site",
                        "plant",
                        "facility",
                        "factory",
                        "mill",
                        "unit",
                        "building",
                        "address",
                        "street",
                        "road",
                        "avenue",
                        "lane",
                        "city",
                    ]
                )
                if "phone" in lowered:
                    continue
                if has_digits and not has_location_keyword:
                    continue
            results.append(result)

        results = self._dedupe_overlaps(results)

        # 2. Apply deterministic pseudonyms. Different persons get different tags.
        anonymized_text = self._apply_pseudonyms(text, results)

        return anonymized_text, results

    @staticmethod
    def _dedupe_overlaps(results):
        # Prefer high-confidence and tighter spans to avoid label+value duplicates.
        ranked = sorted(
            results,
            key=lambda r: (-r.score, (r.end - r.start), r.start)
        )
        selected = []

        for candidate in ranked:
            overlaps = any(
                not (candidate.end <= kept.start or candidate.start >= kept.end)
                for kept in selected
            )
            if not overlaps:
                selected.append(candidate)

        return sorted(selected, key=lambda r: (r.start, r.end))

    def _apply_pseudonyms(self, text, results):
        placeholder_maps = {}
        placeholder_counters = {}
        replacements = {}

        strict_labels = {
            "PERSON": "NAME",
            "EMAIL_ADDRESS": "EMAIL",
            "PHONE_NUMBER": "PHONE",
            "ID": "ID",
            "CREDIT_CARD": "CREDIT_CARD",
            "IBAN_CODE": "IBAN",
            "IP_ADDRESS": "IP_ADDRESS",
            "LOCATION": "LOCATION",
        }

        def placeholder_for(result, span_text):
            normalized = span_text.strip().lower()
            entity_type = result.entity_type

            if self.policy_name == "strict":
                strict_label = strict_labels.get(entity_type, entity_type)
                return f"[{strict_label}]"

            if entity_type == "LOCATION":
                return self._location_placeholder(span_text)

            entity_label = {
                "PERSON": "NAME",
                "EMAIL_ADDRESS": "EMAIL",
                "PHONE_NUMBER": "PHONE",
                "ID": "ID",
                "CREDIT_CARD": "CREDIT_CARD",
                "IBAN_CODE": "IBAN",
                "IP_ADDRESS": "IP_ADDRESS",
            }.get(entity_type, entity_type)

            entity_map = placeholder_maps.setdefault(entity_type, {})
            if normalized in entity_map:
                return entity_map[normalized]

            next_index = placeholder_counters.get(entity_type, 0) + 1
            placeholder_counters[entity_type] = next_index
            placeholder = f"[{entity_label}{next_index}]"
            entity_map[normalized] = placeholder
            return placeholder

        # Assign pseudonym labels in natural left-to-right order.
        for result in sorted(results, key=lambda r: (r.start, r.end)):
            span_value = text[result.start:result.end]
            replacements[(result.start, result.end)] = placeholder_for(result, span_value)

        anonymized_text = text
        for result in sorted(results, key=lambda r: r.start, reverse=True):
            replacement = replacements[(result.start, result.end)]

            anonymized_text = (
                anonymized_text[:result.start]
                + replacement
                + anonymized_text[result.end:]
            )

        return anonymized_text

    def _location_placeholder(self, span_text):
        if self.policy_name == "strict":
            return "[LOCATION]"

        lowered = span_text.lower()

        if any(keyword in lowered for keyword in ["country", "nation", "state"]):
            return "[COUNTRY]"
        if any(keyword in lowered for keyword in ["city", "town", "village", "municipality"]):
            return "[CITY]"
        if any(keyword in lowered for keyword in ["site", "plant", "facility", "factory", "mill", "unit"]):
            return "[SITE]"
        if any(keyword in lowered for keyword in ["address", "street", "road", "avenue", "lane", "postal", "zip"]):
            return "[ADDRESS]"

        if any(char.isdigit() for char in span_text):
            return "[ADDRESS]"

        tokens = [token for token in re.findall(r"[A-Za-zÅÄÖåäö]+", span_text)]
        if len(tokens) <= 2:
            return "[CITY]"

        return "[LOCATION]"