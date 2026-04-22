import unittest
import os
import tempfile
from io import StringIO
from contextlib import redirect_stdout

from src.anonymizer import AnonymizerTool
from src.file_pipeline import load_policy_config
from main import run_anonymization
from tests.run_text_anonymization_cases import run_cases


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

    def test_light_policy_masks_numeric_industrial_location(self):
        tool = AnonymizerTool(
            entities=["LOCATION"],
            threshold=0.3,
            policy_name="light",
        )

        anonymized, _ = tool.process_text("Site: Helsinki Plant Unit 3")

        self.assertIn("[SITE]", anonymized)
        self.assertNotIn("Helsinki Plant Unit 3", anonymized)

    def test_light_policy_masks_unlabeled_industrial_location_phrase(self):
        tool = AnonymizerTool(
            entities=["LOCATION"],
            threshold=0.3,
            policy_name="light",
        )

        text = "Shift handover at Helsinki Plant Unit 3 with maintenance team"
        anonymized, _ = tool.process_text(text)

        self.assertIn("at [SITE]", anonymized)
        self.assertNotIn("Helsinki Plant Unit 3", anonymized)

    def test_light_policy_does_not_swallow_person_before_industrial_location(self):
        tool = AnonymizerTool(
            entities=["PERSON", "LOCATION"],
            threshold=0.3,
            policy_name="light",
        )

        text = "Supervisor Mike Adams at Helsinki Plant Unit 3 reviewed alarms"
        anonymized, _ = tool.process_text(text)

        self.assertIn("Supervisor [NAME1] at [SITE]", anonymized)
        self.assertNotIn("Helsinki Plant Unit 3", anonymized)

    def test_light_policy_still_filters_phone_like_location_false_positive(self):
        tool = AnonymizerTool(
            entities=["LOCATION"],
            threshold=0.3,
            policy_name="light",
        )

        text = "Location: phone 0401239876"
        anonymized, _ = tool.process_text(text)

        self.assertEqual(anonymized, text)

    def test_phone_and_email_are_masked(self):
        tool = AnonymizerTool(
            entities=["EMAIL_ADDRESS", "PHONE_NUMBER"],
            threshold=0.3,
            policy_name="strict",
        )

        text = "Email: jane.doe@example.com | Phone: +358401234567"
        anonymized, _ = tool.process_text(text)

        self.assertIn("[EMAIL]", anonymized)
        self.assertIn("[PHONE]", anonymized)
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

        self.assertIn("[ID]", anonymized)
        self.assertNotIn("ABC-12345", anonymized)

    def test_strict_policy_masks_worker_style_ids_but_keeps_machine_code(self):
        tool = AnonymizerTool(
            entities=["ID"],
            threshold=0.3,
            policy_name="strict",
        )

        text = "Supervisor (EMP-FI-1102) worked with Jari (FI-8821). Maintenance (TECH-12) checked MX-4421."
        anonymized, _ = tool.process_text(text)

        self.assertNotIn("EMP-FI-1102", anonymized)
        self.assertNotIn("FI-8821", anonymized)
        self.assertNotIn("TECH-12", anonymized)
        self.assertIn("[ID]", anonymized)
        self.assertIn("MX-4421", anonymized)

    def test_strict_policy_masks_insp_worker_id_but_keeps_batch_code(self):
        tool = AnonymizerTool(
            entities=["PERSON", "ID"],
            threshold=0.3,
            policy_name="strict",
        )

        text = "14:25 - Olli Mäkinen (INSP-91) flagged batch B-77830"
        anonymized, _ = tool.process_text(text)

        self.assertNotIn("INSP-91", anonymized)
        self.assertIn("[ID]", anonymized)
        self.assertIn("B-77830", anonymized)

    def test_light_mode_same_person_gets_same_placeholder(self):
        tool = AnonymizerTool(
            entities=["PERSON"],
            threshold=0.3,
            policy_name="light",
        )

        text = "Name=John Doe and Contact Name=John Doe"
        anonymized, _ = tool.process_text(text)

        self.assertEqual(anonymized.count("[NAME1]"), 2)
        self.assertNotIn("John Doe", anonymized)

    def test_light_mode_repeated_and_distinct_people_are_pseudonymized_consistently(self):
        tool = AnonymizerTool(
            entities=["PERSON", "LOCATION", "EMAIL_ADDRESS", "PHONE_NUMBER", "ID"],
            threshold=0.3,
            policy_name="light",
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

    def test_strict_mode_anonymizes_without_unique_indices(self):
        tool = AnonymizerTool(
            entities=["PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER", "ID"],
            threshold=0.3,
            policy_name="strict",
        )

        text = (
            "Name=John Doe and Contact Name=John Doe. "
            "Email john.doe@example.com and copy john.doe@example.com. "
            "Phone +358401234567 and backup +358401234567. "
            "Badge ID: ABC-12345 and Employee ID: ABC-12345"
        )
        anonymized, _ = tool.process_text(text)

        self.assertEqual(anonymized.count("[NAME]"), 2)
        self.assertEqual(anonymized.count("[EMAIL]"), 2)
        self.assertEqual(anonymized.count("[PHONE]"), 2)
        self.assertIn("[ID]", anonymized)
        self.assertNotIn("John Doe", anonymized)
        self.assertNotIn("john.doe@example.com", anonymized)

    def test_strict_mode_masks_repeated_single_name_mentions_after_full_name_detection(self):
        tool = AnonymizerTool(
            entities=["PERSON"],
            threshold=0.3,
            policy_name="strict",
        )

        text = (
            "Supervisor: Jari Lehtonen reviewed alarms. "
            "Later Jari briefed Pekka Niemi, and Niemi confirmed the update."
        )
        anonymized, _ = tool.process_text(text)

        self.assertNotIn("Jari", anonymized)
        self.assertNotIn("Lehtonen", anonymized)
        self.assertNotIn("Niemi", anonymized)
        self.assertGreaterEqual(anonymized.count("[NAME]"), 4)

    def test_strict_policy_masks_high_risk_structured_entities(self):
        tool = AnonymizerTool(
            entities=["CREDIT_CARD", "IBAN_CODE", "IP_ADDRESS"],
            threshold=0.3,
            policy_name="strict",
        )

        text = "Card 4111 1111 1111 1111 | IBAN FI21 1234 5600 0007 85 | IP 10.20.30.40"
        anonymized, _ = tool.process_text(text)

        self.assertIn("[CREDIT_CARD]", anonymized)
        self.assertIn("[IBAN]", anonymized)
        self.assertIn("[IP_ADDRESS]", anonymized)
        self.assertNotIn("4111 1111 1111 1111", anonymized)
        self.assertNotIn("FI21 1234 5600 0007 85", anonymized)
        self.assertNotIn("10.20.30.40", anonymized)

    def test_light_mode_repeated_email_reuses_same_placeholder(self):
        tool = AnonymizerTool(
            entities=["EMAIL_ADDRESS"],
            threshold=0.3,
            policy_name="light",
        )

        text = "Email jane.doe@example.com and copy jane.doe@example.com"
        anonymized, _ = tool.process_text(text)

        self.assertEqual(anonymized.count("[EMAIL1]"), 2)

    def test_light_mode_assigns_names_in_left_to_right_order(self):
        tool = AnonymizerTool(
            entities=["PERSON"],
            threshold=0.3,
            policy_name="light",
        )

        text = "Operator: John Carter, Supervisor: Anna Virtanen, Engineer: Mike Adams"
        anonymized, _ = tool.process_text(text)

        self.assertIn("[NAME1]", anonymized)
        self.assertIn("[NAME2]", anonymized)
        self.assertIn("[NAME3]", anonymized)
        self.assertLess(anonymized.index("[NAME1]"), anonymized.index("[NAME2]"))
        self.assertLess(anonymized.index("[NAME2]"), anonymized.index("[NAME3]"))

    def test_light_mode_masks_full_name_span_without_leaking_first_name(self):
        tool = AnonymizerTool(
            entities=["PERSON"],
            threshold=0.3,
            policy_name="light",
        )

        text = "Coffee break. Mikko Saarinen left early."
        anonymized, _ = tool.process_text(text)

        self.assertNotIn("Mikko", anonymized)
        self.assertNotIn("Saarinen", anonymized)
        self.assertIn("[NAME1]", anonymized)

    def test_load_config_works_outside_repo_cwd(self):
        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                os.chdir(temp_dir)
                cfg = load_policy_config("light")
            finally:
                os.chdir(original_cwd)

        self.assertEqual(cfg["policy_name"], "light")
        self.assertIn("entities", cfg)
        self.assertEqual(cfg["threshold"], 0.4)

    def test_load_config_returns_strict_threshold(self):
        cfg = load_policy_config("strict")

        self.assertEqual(cfg["policy_name"], "strict")
        self.assertEqual(cfg["threshold"], 0.3)

    def test_sample_case_runner_uses_shared_policy_config(self):
        output = StringIO()
        with redirect_stdout(output):
            run_cases("strict")

        printed = output.getvalue()
        self.assertIn("CASE 1", printed)
        self.assertIn("ANON :", printed)


if __name__ == "__main__":
    unittest.main()
