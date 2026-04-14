import argparse
import json
import os
from src.anonymizer import AnonymizerTool
from src.logger import log_redaction # New import

def run_anonymization(input_text=None):
    # 1. Settings
    config_path = os.path.join("configs", "light.json")
    with open(config_path, "r") as f:
        config = json.load(f)

    # 2. Anonymization tool
    tool = AnonymizerTool(entities=config['entities'], threshold=config['threshold'])

    # 3. Test text (default) or CLI-provided text
    test_input = input_text or "My name is John Doe and my email is john.doe@example.com"
    
    # 4. Processing
    result_text, raw_results = tool.process_text(test_input)

    # 5. Logging
    log_redaction(raw_results, config['policy_name'])

    print("\n--- RESULT ---")
    print(f"Anonymized: {result_text}")
    print("--------------\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run text anonymization")
    parser.add_argument("--text", help="Input text to anonymize")
    args = parser.parse_args()

    run_anonymization(input_text=args.text)