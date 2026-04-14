#!/usr/bin/env python3
import json
import os
import random
from datetime import datetime, timedelta

try:
    from faker import Faker
except ImportError:
    print("Faker not found. Please pip install faker.")
    exit(1)

fake = Faker()
Faker.seed(42)
random.seed(42)

def generate_dob(min_age, max_age=80):
    age = random.randint(min_age, max_age)
    dob = datetime.now() - timedelta(days=age*365.25)
    return dob.strftime('%Y-%m-%d')

def load_rules():
    path = os.path.join(os.path.dirname(__file__), "../config/insurer_rules.json")
    with open(path, "r") as f:
        return json.load(f)

def generate_patients():
    rules = load_rules()
    patients = []
    
    for r in rules:
        # Variant 1: Clear Approve
        p1 = {
            "id": f"PA-{len(patients)+1:03d}",
            "name": fake.name(),
            "dob": generate_dob(r["min_age"] + 1 if r["min_age"] > 0 else 30),
            "insurance_provider": r["insurer"],
            "plan_type": random.choice(["HMO", "PPO", "EPO"]),
            "requested_treatment": {"name": r["brand_name"], "generic": r["drug_name"], "dosage": "Standard dose"},
            "diagnoses": r["icd10_codes"],
            "current_medications": [],
            "prior_treatments": r["step_therapy"],
            "labs": {k: v + 1.0 if "min" in k else v for k, v in r["lab_thresholds"].items() if isinstance(v, (int, float))},
            "contraindications": [],
            "npi": fake.numerify(text="##########"),
            "provider_name": "Dr. " + fake.last_name(),
            "gender": random.choice(["Male", "Female"]),
            "expected_outcome": "APPROVED",
            "expected_reasoning": "Meets all criteria."
        }
        patients.append(p1)
        
        # Variant 2: Clear Deny (wrong diagnosis or missing step therapy)
        p2 = {
            "id": f"PA-{len(patients)+1:03d}",
            "name": fake.name(),
            "dob": generate_dob(r["min_age"] + 1 if r["min_age"] > 0 else 30),
            "insurance_provider": r["insurer"],
            "plan_type": random.choice(["HMO", "PPO", "EPO"]),
            "requested_treatment": {"name": r["brand_name"], "generic": r["drug_name"], "dosage": "Standard dose"},
            "diagnoses": [r["icd10_codes"][0]] if r["icd10_codes"] else ["Z00.00"],
            "current_medications": [],
            "prior_treatments": [], # Missing step therapy!
            "labs": {k: v + 1.0 if "min" in k else v for k, v in r["lab_thresholds"].items() if isinstance(v, (int, float))},
            "contraindications": [],
            "npi": fake.numerify(text="##########"),
            "provider_name": "Dr. " + fake.last_name(),
            "gender": random.choice(["Male", "Female"]),
            "expected_outcome": "DENIED",
            "expected_reasoning": "Missing required step therapy."
        }
        if not r["step_therapy"]:
            p2["diagnoses"] = ["Z00.00"] # Change diagnosis if no step therapy required
            p2["expected_reasoning"] = "Invalid diagnosis."
        patients.append(p2)

        # Variant 3: Borderline (ambiguous lab or slightly off age)
        p3 = {
            "id": f"PA-{len(patients)+1:03d}",
            "name": fake.name(),
            "dob": generate_dob(r["min_age"] + 5 if r["min_age"] > 0 else 30),
            "insurance_provider": r["insurer"],
            "plan_type": random.choice(["HMO", "PPO", "EPO"]),
            "requested_treatment": {"name": r["brand_name"], "generic": r["drug_name"], "dosage": "Standard dose"},
            "diagnoses": r["icd10_codes"],
            "current_medications": [],
            "prior_treatments": r["step_therapy"],
            "labs": {k: v - 0.1 if "min" in k else v for k, v in r["lab_thresholds"].items() if isinstance(v, (int, float))}, # Slightly below threshold
            "contraindications": [],
            "npi": fake.numerify(text="##########"),
            "provider_name": "Dr. " + fake.last_name(),
            "gender": random.choice(["Male", "Female"]),
            "expected_outcome": "DENIED",
            "expected_reasoning": "Lab value borderline but below threshold."
        }
        patients.append(p3)

        # Variant 4: Missing Info (no labs provided when required)
        p4 = {
            "id": f"PA-{len(patients)+1:03d}",
            "name": fake.name(),
            "dob": generate_dob(r["min_age"] + 5 if r["min_age"] > 0 else 30),
            "insurance_provider": r["insurer"],
            "plan_type": random.choice(["HMO", "PPO", "EPO"]),
            "requested_treatment": {"name": r["brand_name"], "generic": r["drug_name"], "dosage": "Standard dose"},
            "diagnoses": r["icd10_codes"],
            "current_medications": [],
            "prior_treatments": r["step_therapy"],
            "labs": {}, # Missing!
            "contraindications": [],
            "npi": fake.numerify(text="##########"),
            "provider_name": "Dr. " + fake.last_name(),
            "gender": random.choice(["Male", "Female"]),
            "expected_outcome": "VALID_ESCALATION" if r["lab_thresholds"] else "APPROVED",
            "expected_reasoning": "Missing lab results requires escalation." if r["lab_thresholds"] else "Meets criteria."
        }
        patients.append(p4)

        # Variant 5: Edge case (contraindication present)
        p5 = {
            "id": f"PA-{len(patients)+1:03d}",
            "name": fake.name(),
            "dob": generate_dob(r["min_age"] + 5 if r["min_age"] > 0 else 30),
            "insurance_provider": r["insurer"],
            "plan_type": random.choice(["HMO", "PPO", "EPO"]),
            "requested_treatment": {"name": r["brand_name"], "generic": r["drug_name"], "dosage": "Standard dose"},
            "diagnoses": r["icd10_codes"],
            "current_medications": [],
            "prior_treatments": r["step_therapy"],
            "labs": {k: v + 1.0 if "min" in k else v for k, v in r["lab_thresholds"].items() if isinstance(v, (int, float))},
            "contraindications": [r["contraindications"][0]] if r["contraindications"] else ["pregnancy"],
            "npi": fake.numerify(text="##########"),
            "provider_name": "Dr. " + fake.last_name(),
            "gender": random.choice(["Male", "Female"]),
            "expected_outcome": "DENIED",
            "expected_reasoning": "Contraindication is present."
        }
        patients.append(p5)

    os.makedirs(os.path.join(os.path.dirname(__file__), "../data"), exist_ok=True)
    out_path = os.path.join(os.path.dirname(__file__), "../data/patients.json")
    with open(out_path, "w") as f:
        json.dump(patients, f, indent=2)
    print(f"Generated {len(patients)} patients at {out_path}")

if __name__ == "__main__":
    generate_patients()
