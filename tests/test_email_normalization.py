import unittest
from src.modalities.audio.audio_pipeline import _normalize_spoken_email_markers
from src.anonymizer import AnonymizerTool


class EmailNormalizationTests(unittest.TestCase):
    """Test email marker normalization for Whisper transcripts."""

    def test_normalizer_converts_spoken_piste_to_dot(self):
        """Finnish 'piste' (dot) should be converted to period with @ insertion."""
        text = "sähköpostilla tero piste raja piste company piste fi"
        normalized = _normalize_spoken_email_markers(text)
        self.assertIn("tero.raja@company.fi", normalized)

    def test_normalizer_converts_space_dot_space_to_dot(self):
        """Whisper-style ' . ' tokens should become periods."""
        text = "sähköpostilla tero . raja . company . fi"
        normalized = _normalize_spoken_email_markers(text)
        self.assertIn("tero.raja@company.fi", normalized)

    def test_normalizer_adds_at_symbol_with_email_context(self):
        """When email context is present, should insert @ before TLD domain."""
        text = "email john . smith . acme . com"
        normalized = _normalize_spoken_email_markers(text)
        self.assertIn("john.smith@acme.com", normalized)

    def test_normalizer_handles_english_dot_marker(self):
        """English 'dot' should be converted to period."""
        text = "contact jane dot doe dot example dot com"
        normalized = _normalize_spoken_email_markers(text)
        self.assertIn("jane.doe@example.com", normalized)

    def test_normalizer_doesnt_reconstruct_without_tld(self):
        """Should not reconstruct dotted sequences without recognized TLD."""
        text = "degree 4 . 2"
        normalized = _normalize_spoken_email_markers(text)
        self.assertEqual(normalized, "degree 4.2")
        self.assertNotIn("@", normalized)

    def test_normalizer_doesnt_reconstruct_degrees_without_context(self):
        """Academic references like 'chapter 3 . 5' should remain unchanged."""
        text = "chapter 3 . 5 . 1"
        normalized = _normalize_spoken_email_markers(text)
        # Should collapse dots but not add @
        self.assertNotIn("@", normalized)

    def test_normalizer_preserves_standard_emails(self):
        """Standard email format should pass through unchanged."""
        text = "Email: john.doe@acme.com is the contact"
        normalized = _normalize_spoken_email_markers(text)
        self.assertIn("john.doe@acme.com", normalized)

    def test_normalizer_handles_multiple_emails(self):
        """Multiple emails in one text should all be normalized."""
        text = "email alice piste bob piste com and contact charlie . dave . org"
        normalized = _normalize_spoken_email_markers(text)
        self.assertIn("alice@bob.com", normalized)
        self.assertIn("charlie@dave.org", normalized)

    def test_normalizer_replaces_spoken_at_marker(self):
        """Spoken '@' variants like 'at-merkki' should become @."""
        text = "john at-merkki example com"
        normalized = _normalize_spoken_email_markers(text)
        # May not fully reconstruct without dots, but @ marker should convert
        self.assertIn("@", normalized)

    def test_normalizer_handles_finnish_at_variant(self):
        """Finnish 'ät-merkki' should become @."""
        text = "john ät-merkki example fi"
        normalized = _normalize_spoken_email_markers(text)
        self.assertIn("@", normalized)


class EmailAnonymizationTests(unittest.TestCase):
    """Test that normalized emails are properly anonymized."""

    def test_anonymizer_detects_normalized_email_with_at_symbol(self):
        """Presidio should catch standard @ emails after normalization."""
        tool = AnonymizerTool(
            entities=["EMAIL_ADDRESS"],
            threshold=0.3,
            policy_name="light",
        )
        # Normalizer would have already converted this from spoken form
        text = "Contact: john.doe@acme.com for details"
        anonymized, results = tool.process_text(text)
        
        self.assertIn("[EMAIL1]", anonymized)
        self.assertNotIn("john.doe@acme.com", anonymized)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].entity_type, "EMAIL_ADDRESS")

    def test_anonymizer_fallback_detects_dotted_email_with_context(self):
        """Fallback should detect dotted emails when email context present."""
        tool = AnonymizerTool(
            entities=["EMAIL_ADDRESS"],
            threshold=0.3,
            policy_name="light",
        )
        text = "sähköpostilla john.doe@acme.fi for contact"
        anonymized, results = tool.process_text(text)
        
        self.assertIn("[EMAIL1]", anonymized)
        self.assertTrue(any(r.entity_type == "EMAIL_ADDRESS" for r in results))

    def test_anonymizer_reuses_same_email_placeholder(self):
        """Same email appearing twice should reuse the same placeholder."""
        tool = AnonymizerTool(
            entities=["EMAIL_ADDRESS"],
            threshold=0.3,
            policy_name="light",
        )
        text = "Email: jane.doe@example.com and copy jane.doe@example.com"
        anonymized, results = tool.process_text(text)
        
        self.assertEqual(anonymized.count("[EMAIL1]"), 2)

    def test_full_pipeline_whisper_style_email(self):
        """Full pipeline: normalize then anonymize Whisper-style email."""
        # Step 1: Normalize (simulating Whisper transcript)
        whisper_output = "sähköpostilla tero . raja . company . fi"
        normalized = _normalize_spoken_email_markers(whisper_output)
        
        self.assertIn("@", normalized)
        
        # Step 2: Anonymize
        tool = AnonymizerTool(
            entities=["EMAIL_ADDRESS"],
            threshold=0.3,
            policy_name="light",
        )
        anonymized, results = tool.process_text(normalized)
        
        self.assertIn("[EMAIL1]", anonymized)
        self.assertTrue(any(r.entity_type == "EMAIL_ADDRESS" for r in results))
        self.assertNotIn("tero.raja@company.fi", anonymized)


if __name__ == "__main__":
    unittest.main()
