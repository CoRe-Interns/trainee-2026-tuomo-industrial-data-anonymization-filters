import json
import os
from src.anonymizer import AnonymizerTool
from src.logger import log_redaction # Uusi tuonti

def run_anonymization():
    # 1. Asetukset
    config_path = os.path.join("configs", "light.json")
    with open(config_path, "r") as f:
        config = json.load(f)

    # 2. Työkalu
    tool = AnonymizerTool(entities=config['entities'], threshold=config['threshold'])

    # 3. Testiteksti
    test_input = "My name is John Doe and my email is john.doe@example.com"
    
    # 4. Prosessointi
    result_text, raw_results = tool.process_text(test_input)

    # 5. Lokitus
    log_redaction(raw_results, config['policy_name'])

    print("\n--- TULOS ---")
    print(f"Anonymisoitu: {result_text}")
    print("--------------\n")

if __name__ == "__main__":
    run_anonymization()