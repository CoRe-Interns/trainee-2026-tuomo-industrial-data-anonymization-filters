import csv
from datetime import datetime
import os

def log_redaction(results, policy_name):
    log_file = "data/audit_log.csv"
    
    # Create the data folder if it does not exist
    os.makedirs("data", exist_ok=True)
    
    # Check whether headers should be written (if the file is new)
    file_exists = os.path.isfile(log_file)
    
    with open(log_file, mode='a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["timestamp", "policy", "entity_type", "start_pos", "end_pos", "confidence"])
        
        for res in results:
            writer.writerow([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                policy_name,
                res.entity_type,
                res.start,
                res.end,
                round(res.score, 2)
            ])
    print(f"Audit log updated: {log_file}")