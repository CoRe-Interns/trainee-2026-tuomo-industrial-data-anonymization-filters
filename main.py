import argparse
import json
import os
from src.anonymizer import AnonymizerTool
from src.logger import log_redaction

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

def load_config(policy_name):
    config_path = os.path.join(PROJECT_ROOT, "configs", f"{policy_name}.json")
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def run_anonymization(input_text=None, policy_name="light"):
    # 1. Settings
    config = load_config(policy_name)

    # 2. Anonymization tool
    tool = AnonymizerTool(entities=config['entities'], threshold=config['threshold'], policy_name=policy_name)

    # 3. Test text (default) or CLI-provided text
    test_input = (
        input_text
        if input_text is not None
        else "My name is John Doe and my email is john.doe@example.com"
    )
    
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
    parser.add_argument(
        "--policy",
        default="light",
        choices=["light", "strict"],
        help="Anonymization policy to use",
    )
    args = parser.parse_args()

    run_anonymization(input_text=args.text, policy_name=args.policy)