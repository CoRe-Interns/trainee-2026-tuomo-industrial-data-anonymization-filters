import unittest
import os
import tempfile

from src.anonymizer import AnonymizerTool
from main import load_config


class TextAnonymizationTests(unittest.TestCase):
    def test_strict_policy_masks_location_as_generic_location(self):
        tool = AnonymizerTool(
            entities=["LOCATION"],
            threshold=0.3,
            policy_name="strict",
        )

        anonymized, _ = tool.process_text("Location=Helsinki Plant")

        self.assertIn("<LOCATION>", anonymized)
        self.assertNotIn("Helsinki", anonymized)

    def test_light_policy_masks_location_with_specific_placeholder(self):
        tool = AnonymizerTool(
            entities=["LOCATION"],
            threshold=0.3,
            policy_name="light",
        )

        anonymized, _ = tool.process_text("Location=Helsinki Plant")

        self.assertIn("<SITE>", anonymized)
        self.assertNotIn("Helsinki", anonymized)

    def test_phone_and_email_are_masked(self):
        tool = AnonymizerTool(
            entities=["EMAIL_ADDRESS", "PHONE_NUMBER"],
            threshold=0.3,
            policy_name="strict",
        )

        text = "Email: jane.doe@example.com | Phone: +358401234567"
        anonymized, _ = tool.process_text(text)

        self.assertIn("<EMAIL_ADDRESS>", anonymized)
        self.assertIn("<PHONE_NUMBER>", anonymized)
        self.assertNotIn("jane.doe@example.com", anonymized)
        self.assertNotIn("+358401234567", anonymized)

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
