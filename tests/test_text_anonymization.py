import unittest
import os
import tempfile
from io import StringIO
from contextlib import redirect_stdout

from src.anonymizer import AnonymizerTool
from main import load_config, run_anonymization


class TextAnonymizationTests(unittest.TestCase):
    def test_run_anonymization_respects_explicit_empty_input(self):
        output = StringIO()
        with redirect_stdout(output):
            run_anonymization(input_text="", policy_name="light")

        printed = output.getvalue()
        self.assertIn("Anonymized: ", printed)
        self.assertNotIn("My name is John Doe", printed)

    def test_strict_policy_masks_location_as_generic_location(self):
        tool = AnonymizerTool(
            entities=["LOCATION"],
            threshold=0.3,
            policy_name="strict",
        )

        anonymized, _ = tool.process_text("Location=Helsinki Plant")

        self.assertIn("[LOCATION]", anonymized)
        self.assertNotIn("Helsinki", anonymized)

    def test_light_policy_masks_location_with_specific_placeholder(self):
        tool = AnonymizerTool(
            entities=["LOCATION"],
            threshold=0.3,
            policy_name="light",
        )

        anonymized, _ = tool.process_text("Location=Helsinki Plant")

        self.assertIn("[SITE]", anonymized)
        self.assertNotIn("Helsinki", anonymized)

    def test_phone_and_email_are_masked(self):
        tool = AnonymizerTool(
            entities=["EMAIL_ADDRESS", "PHONE_NUMBER"],
            threshold=0.3,
            policy_name="strict",
        )

        text = "Email: jane.doe@example.com | Phone: +358401234567"
        anonymized, _ = tool.process_text(text)

        self.assertIn("[EMAIL1]", anonymized)
        self.assertIn("[PHONE1]", anonymized)
        self.assertNotIn("jane.doe@example.com", anonymized)
        self.assertNotIn("+358401234567", anonymized)

    def test_strict_policy_masks_custom_id(self):
        tool = AnonymizerTool(
            entities=["ID"],
            threshold=0.3,
            policy_name="strict",
        )

        text = "Badge ID: ABC-12345"
        anonymized, _ = tool.process_text(text)

        self.assertIn("[ID1]", anonymized)
        self.assertNotIn("ABC-12345", anonymized)

    def test_same_person_gets_same_placeholder(self):
        tool = AnonymizerTool(
            entities=["PERSON"],
            threshold=0.3,
            policy_name="strict",
        )

        text = "Name=John Doe and Contact Name=John Doe"
        anonymized, _ = tool.process_text(text)

        self.assertEqual(anonymized.count("[NAME1]"), 2)
        self.assertNotIn("John Doe", anonymized)

    def test_repeated_and_distinct_people_are_pseudonymized_consistently(self):
        tool = AnonymizerTool(
            entities=["PERSON", "LOCATION", "EMAIL_ADDRESS", "PHONE_NUMBER", "ID"],
            threshold=0.3,
            policy_name="strict",
        )

        text = (
            "Operator: John Carter approved maintenance at Helsinki Plant. "
            "Contact Name=Anna Virtanen reviewed the ticket with John Carter. "
            "Email: john.carter@acme.com | Backup email: anna.virtanen@acme.com | "
            "Phone: +358401234567 | Badge ID: ABC-12345"
        )
        anonymized, _ = tool.process_text(text)

        self.assertEqual(anonymized.count("[NAME1]"), 2)
        self.assertEqual(anonymized.count("[NAME2]"), 1)
        self.assertNotIn("John Carter", anonymized)
        self.assertNotIn("Anna Virtanen", anonymized)

    def test_strict_policy_masks_high_risk_structured_entities(self):
        tool = AnonymizerTool(
            entities=["CREDIT_CARD", "IBAN_CODE", "IP_ADDRESS"],
            threshold=0.3,
            policy_name="strict",
        )

        text = "Card 4111 1111 1111 1111 | IBAN FI21 1234 5600 0007 85 | IP 10.20.30.40"
        anonymized, _ = tool.process_text(text)

        self.assertIn("[CREDIT_CARD1]", anonymized)
        self.assertIn("[IBAN1]", anonymized)
        self.assertIn("[IP_ADDRESS1]", anonymized)
        self.assertNotIn("4111 1111 1111 1111", anonymized)
        self.assertNotIn("FI21 1234 5600 0007 85", anonymized)
        self.assertNotIn("10.20.30.40", anonymized)

    def test_repeated_email_reuses_same_placeholder(self):
        tool = AnonymizerTool(
            entities=["EMAIL_ADDRESS"],
            threshold=0.3,
            policy_name="strict",
        )

        text = "Email jane.doe@example.com and copy jane.doe@example.com"
        anonymized, _ = tool.process_text(text)

        self.assertEqual(anonymized.count("[EMAIL1]"), 2)

    def test_load_config_works_outside_repo_cwd(self):
        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                os.chdir(temp_dir)
                cfg = load_config("light")
            finally:
                os.chdir(original_cwd)

        self.assertEqual(cfg["policy_name"], "light")
        self.assertIn("entities", cfg)
        self.assertIn("threshold", cfg)


if __name__ == "__main__":
    unittest.main()
