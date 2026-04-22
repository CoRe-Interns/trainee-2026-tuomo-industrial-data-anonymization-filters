import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.file_pipeline import build_anonymizer


def run_cases(policy_name="strict"):
    tool, _ = build_anonymizer(policy_name)

    samples = [
        "Operator: John Carter | Site: Helsinki Plant | Email: john.carter@acme.com | Phone: +358401234567",
        "Maintenance note: Technician Laura Nieminen replaced valve at facility: Turku Refinery. Contact Name=Marko Virtanen",
        "Shift handover: supervisor Mike Adams approved lockout. Reach him at mike.adams@factory.io or 0401239876.",
        "Incident #772: Employee Sarah Connor reported near-miss in city: Oulu. Manager=David Lee",
        "Delivery gate log: Driver Peter Brown checked in at address=Port Road 12, Tampere. Phone=0507654321",
        "Calibration ticket: Contact Name: Emma Wilson, Plant: Vaasa Unit 3, Email=emma.wilson@plant.net",
        "Contractor visit: Name=Ahmed Al Farsi; Site=Kotka Mill; Badge ID 88321",
        "Field report: operator matti meikalainen inspected compressor in Turku, email matti.meikalainen@ops.fi",
        "Night shift summary: Full Name=Olivia Johnson, Location=Espoo Site, emergency phone 0459988776",
        "Quality note: technician Jari Makela escalated issue to manager Anne Kallio at location: Porvoo",
    ]

    for i, text in enumerate(samples, 1):
        anonymized, results = tool.process_text(text)
        entities = [
            {
                "type": r.entity_type,
                "score": round(r.score, 2),
                "span": text[r.start:r.end],
            }
            for r in results
        ]
        print(f"CASE {i}")
        print("INPUT:", text)
        print("ANON :", anonymized)
        print("ENTS :", entities)
        print("-")


if __name__ == "__main__":
    run_cases("strict")
