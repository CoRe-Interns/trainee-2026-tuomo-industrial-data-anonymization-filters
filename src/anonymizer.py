import re

from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer, RecognizerResult

class AnonymizerTool:
    def __init__(self, entities, threshold, policy_name="light", language="en"):
        # Initialize Presidio with no NLP engine so the custom pattern recognizers
        # can run offline without downloading SpaCy language models.
        self.analyzer = AnalyzerEngine(nlp_engine=None, supported_languages=[language])
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
                ),
                Pattern(
                    name="worker_style_id_token",
                    regex=(
                        r"(?<![A-Z0-9-])(?:EMP-[A-Z]{2}-\d{3,6}|FI-\d{3,6}|TECH-\d{2,6}|INSP-\d{2,6})(?![A-Z0-9-])"
                    ),
                    score=0.9,
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
            if result.entity_type == "PERSON":
                if not self._is_plausible_person_span(span_text):
                    continue
                lowered = span_text.strip().lower()
                if lowered in {"email", "phone", "id", "badge", "employee"}:
                    continue

            # Drop location false positives which often overlap phone/id-style fields.
            if result.entity_type == "LOCATION":
                lowered = span_text.lower()
                tokens = re.findall(r"[A-Za-zÅÄÖåäö]+", span_text)
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
                has_capitalized_token = any(token[:1].isupper() for token in tokens)
                if "phone" in lowered:
                    continue
                if not has_location_keyword and not has_capitalized_token:
                    continue
            results.append(result)

        # Add fallback email detection for dotted patterns that Presidio may have missed
        if "EMAIL_ADDRESS" in self.entities:
            results.extend(self._find_fallback_emails(text, results))

        results = self._expand_person_to_neighboring_full_name(text, results)
        results = self._expand_person_name_references(text, results)
        results = self._dedupe_overlaps(results)

        # 2. Apply deterministic pseudonyms. Different persons get different tags.
        anonymized_text = self._apply_pseudonyms(text, results)

        return anonymized_text, results

    @staticmethod
    def _is_plausible_person_span(span_text: str) -> bool:
        tokens = [token for token in re.findall(r"[A-Za-zÅÄÖåäö]+(?:[-'][A-Za-zÅÄÖåäö]+)*", span_text)]
        if not tokens:
            return False

        if len(tokens) > 3:
            return False

        if any(token[0].isupper() for token in tokens):
            return True

        # Lowercase free text should not be treated as a person name unless it
        # is already attached to a labeled field handled by the recognizer above.
        return False

    def _find_fallback_emails(self, text: str, existing_results: list) -> list:
        """
        Detect dotted email patterns that Presidio may have missed.
        
        Only reconstructs emails when:
        1. Pattern ends with known email TLD, AND
        2. Either preceded by email context OR looks like a standard email local-part
        
        This catches patterns like "tero.raja@company.fi" or "john.doe.acme.com"
        that survived Whisper/normalization but weren't detected by standard email regex.
        """
        email_tlds = {
            "fi", "com", "net", "org", "eu", "se", "io", "co", "uk", "de", "fr",
            "it", "es", "nl", "be", "at", "ch", "ru", "ua", "pl", "cz", "hu",
            "ro", "bg", "hr", "si", "sk", "gr", "pt", "ie", "us", "ca", "au",
            "nz", "jp", "cn", "in", "br", "mx", "ar", "za"
        }
        email_context_keywords = {
            "sähköpostilla", "sähköposti", "email", "contact", "posti", "osoite"
        }
        
        new_detections = []
        text_lower = text.lower()
        
        # Check for email context
        has_email_context = any(kw in text_lower for kw in email_context_keywords)
        
        # Pattern: word[.word]+[@]word[.word]+.tld
        # Matches: john.doe@acme.com, john.doe.acme.com, etc.
        tld_pattern = "|".join(email_tlds)
        pattern = rf"(?:^|\s)([a-z0-9._-]+(?:@|\.)[a-z0-9._-]*\.(?:{tld_pattern}))\b"
        
        for match in re.finditer(pattern, text_lower):
            span_text = match.group(1)
            start = match.start(1)
            end = match.end(1)
            
            # Skip if this span overlaps with existing detections
            overlaps = any(
                not (end <= existing.start or start >= existing.end)
                for existing in existing_results
            )
            if overlaps:
                continue
            
            # Only include if:
            # 1. Has @ (standard email), OR
            # 2. Has email context AND looks like email local-part
            if "@" in span_text:
                new_detections.append(
                    RecognizerResult(
                        entity_type="EMAIL_ADDRESS",
                        start=start,
                        end=end,
                        score=0.85,  # Slightly lower than Presidio standard (0.95) since this is fallback
                    )
                )
            elif has_email_context:
                # Check local part plausibility
                parts = span_text.split(".")
                if len(parts) >= 3 and parts[0]:
                    local = ".".join(parts[:-2])
                    # Only if local part looks standard (lowercase, alphanumeric, _, -)
                    if re.match(r"^[a-z0-9._-]+$", local):
                        new_detections.append(
                            RecognizerResult(
                                entity_type="EMAIL_ADDRESS",
                                start=start,
                                end=end,
                                score=0.80,  # Lower confidence for context-only reconstruction
                            )
                        )
        
        return new_detections

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

    @staticmethod
    def _expand_person_name_references(text, results):
        stop_tokens = {
            "name",
            "full",
            "contact",
            "operator",
            "technician",
            "employee",
            "manager",
            "supervisor",
            "attn",
            "email",
            "phone",
            "badge",
            "id",
        }

        known_name_tokens = set()
        for result in results:
            if result.entity_type != "PERSON":
                continue

            span_text = text[result.start:result.end]

            # Avoid amplifying labeled field detections like "Name=John Doe".
            prefix = text[max(0, result.start - 20):result.start].lower()
            if any(marker in prefix for marker in ["name=", "name:", "contact name", "full name", "supervisor:", "operator:", "manager:", "technician:"]):
                continue

            tokens = re.findall(r"[^\W\d_]+", span_text)
            if len(tokens) < 2:
                continue

            for token in tokens:
                if len(token) < 3:
                    continue
                lowered = token.lower()
                if lowered in stop_tokens:
                    continue
                if not token[0].isupper():
                    continue
                known_name_tokens.add(token)

        if not known_name_tokens:
            return results

        selected = list(results)
        for token in sorted(known_name_tokens, key=len, reverse=True):
            pattern = re.compile(rf"(?<![\w]){re.escape(token)}(?![\w])")
            for match in pattern.finditer(text):
                start, end = match.span()
                overlaps = any(
                    not (end <= existing.start or start >= existing.end)
                    for existing in selected
                )
                if overlaps:
                    continue

                selected.append(
                    RecognizerResult(
                        entity_type="PERSON",
                        start=start,
                        end=end,
                        score=0.79,
                    )
                )

        return selected

    @staticmethod
    def _expand_person_to_neighboring_full_name(text, results):
        stop_tokens = {
            "name",
            "full",
            "contact",
            "operator",
            "technician",
            "employee",
            "manager",
            "supervisor",
            "attn",
            "email",
            "phone",
            "badge",
            "id",
        }

        def is_name_token(token):
            if len(token) < 2:
                return False
            if token.lower() in stop_tokens:
                return False
            return token[0].isupper() and all(ch.isalpha() or ch in "-'" for ch in token)

        expanded = []
        for result in results:
            if result.entity_type != "PERSON":
                expanded.append(result)
                continue

            span_text = text[result.start:result.end]
            token_match = re.fullmatch(r"[^\W\d_]+", span_text)
            if not token_match:
                expanded.append(result)
                continue

            start = result.start
            end = result.end

            prev_match = re.search(r"([^\W\d_]+)\s+$", text[:start])
            if prev_match and is_name_token(prev_match.group(1)):
                start = prev_match.start(1)

            next_match = re.match(r"^\s+([^\W\d_]+)", text[end:])
            if next_match and is_name_token(next_match.group(1)):
                end = end + next_match.end(1)

            if start != result.start or end != result.end:
                expanded.append(
                    RecognizerResult(
                        entity_type="PERSON",
                        start=start,
                        end=end,
                        score=max(result.score, 0.86),
                    )
                )
            else:
                expanded.append(result)

        return expanded

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