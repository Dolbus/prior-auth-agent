#!/usr/from env python3
import json
import os

RULES = [
    # 1. GLP-1 / Diabetes
    {
        "insurer": "Aetna",
        "category": "GLP-1",
        "drug_name": "semaglutide",
        "brand_name": "Ozempic",
        "icd10_codes": ["E11", "E11.65", "E11.9"],  # Type 2 Diabetes
        "step_therapy": ["metformin"],
        "min_age": 18,
        "lab_thresholds": {"A1C_min": 7.0},
        "contraindications": ["medullary thyroid carcinoma", "MEN 2"],
        "pa_required": True,
        "approval_duration_months": 12
    },
    {
        "insurer": "Cigna",
        "category": "GLP-1",
        "drug_name": "semaglutide",
        "brand_name": "Wegovy",
        "icd10_codes": ["E66.01", "E66.9"],  # Obesity
        "step_therapy": ["lifestyle modification program"],
        "min_age": 12,
        "lab_thresholds": {"BMI_min": 30.0, "BMI_with_comorbidity": 27.0},
        "contraindications": ["pregnancy", "medullary thyroid carcinoma"],
        "pa_required": True,
        "approval_duration_months": 8
    },
    {
        "insurer": "UnitedHealthcare",
        "category": "GLP-1",
        "drug_name": "tirzepatide",
        "brand_name": "Mounjaro",
        "icd10_codes": ["E11", "E11.9"],
        "step_therapy": ["metformin", "sulfonylurea"],
        "min_age": 18,
        "lab_thresholds": {"A1C_min": 7.5},
        "contraindications": ["pancreatitis"],
        "pa_required": True,
        "approval_duration_months": 12
    },
    {
        "insurer": "Humana",
        "category": "GLP-1",
        "drug_name": "liraglutide",
        "brand_name": "Victoza",
        "icd10_codes": ["E11.9"],
        "step_therapy": ["metformin"],
        "min_age": 10,
        "lab_thresholds": {"A1C_min": 7.0},
        "contraindications": ["MEN 2"],
        "pa_required": True,
        "approval_duration_months": 12
    },

    # 2. Biologics / Immunology
    {
        "insurer": "Aetna",
        "category": "Biologics",
        "drug_name": "adalimumab",
        "brand_name": "Humira",
        "icd10_codes": ["M05", "M06.9", "L40.0"], # RA or Psoriasis
        "step_therapy": ["methotrexate"],
        "min_age": 18,
        "lab_thresholds": {},
        "contraindications": ["active infection", "tuberculosis"],
        "pa_required": True,
        "approval_duration_months": 12
    },
    {
        "insurer": "Cigna",
        "category": "Biologics",
        "drug_name": "dupilumab",
        "brand_name": "Dupixent",
        "icd10_codes": ["L20.9", "J45.40"], # Eczema or Asthma
        "step_therapy": ["topical corticosteroids"],
        "min_age": 6,
        "lab_thresholds": {},
        "contraindications": ["helminth infection"],
        "pa_required": True,
        "approval_duration_months": 12
    },
    {
        "insurer": "UnitedHealthcare",
        "category": "Biologics",
        "drug_name": "risankizumab",
        "brand_name": "Skyrizi",
        "icd10_codes": ["L40.0"], # Plaque Psoriasis
        "step_therapy": ["methotrexate", "phototherapy"],
        "min_age": 18,
        "lab_thresholds": {"body_surface_area_min_percent": 10},
        "contraindications": ["active TB"],
        "pa_required": True,
        "approval_duration_months": 12
    },
    {
        "insurer": "Humana",
        "category": "Biologics",
        "drug_name": "secukinumab",
        "brand_name": "Cosentyx",
        "icd10_codes": ["M45.9"], # Ankylosing Spondylitis
        "step_therapy": ["NSAIDs"],
        "min_age": 18,
        "lab_thresholds": {},
        "contraindications": ["active infection"],
        "pa_required": True,
        "approval_duration_months": 12
    },

    # 3. PCSK9 Inhibitors
    {
        "insurer": "Aetna",
        "category": "PCSK9",
        "drug_name": "evolocumab",
        "brand_name": "Repatha",
        "icd10_codes": ["E78.01"], # Familial Hypercholesterolemia
        "step_therapy": ["high-intensity statin", "ezetimibe"],
        "min_age": 18,
        "lab_thresholds": {"LDL_min": 100},
        "contraindications": [],
        "pa_required": True,
        "approval_duration_months": 12
    },
    {
        "insurer": "Cigna",
        "category": "PCSK9",
        "drug_name": "alirocumab",
        "brand_name": "Praluent",
        "icd10_codes": ["I25.10"], # ASCVD
        "step_therapy": ["high-intensity statin"],
        "min_age": 18,
        "lab_thresholds": {"LDL_min": 70},
        "contraindications": [],
        "pa_required": True,
        "approval_duration_months": 12
    },
    {
        "insurer": "UnitedHealthcare",
        "category": "PCSK9",
        "drug_name": "evolocumab",
        "brand_name": "Repatha",
        "icd10_codes": ["E78.01", "I25.10"],
        "step_therapy": ["atorvastatin", "rosuvastatin"],
        "min_age": 18,
        "lab_thresholds": {"LDL_min": 70},
        "contraindications": [],
        "pa_required": True,
        "approval_duration_months": 12
    },
    {
        "insurer": "Humana",
        "category": "PCSK9",
        "drug_name": "alirocumab",
        "brand_name": "Praluent",
        "icd10_codes": ["E78.01"],
        "step_therapy": ["ezetimibe", "simvastatin"],
        "min_age": 18,
        "lab_thresholds": {"LDL_min": 100},
        "contraindications": [],
        "pa_required": True,
        "approval_duration_months": 12
    },

    # 4. Specialty Oncology
    {
        "insurer": "Aetna",
        "category": "Oncology",
        "drug_name": "pembrolizumab",
        "brand_name": "Keytruda",
        "icd10_codes": ["C34.90"], # NSCLC
        "step_therapy": [],
        "min_age": 18,
        "lab_thresholds": {"PD_L1_min_percent": 1},
        "contraindications": ["autoimmune disease"],
        "pa_required": True,
        "approval_duration_months": 6
    },
    {
        "insurer": "Cigna",
        "category": "Oncology",
        "drug_name": "palbociclib",
        "brand_name": "Ibrance",
        "icd10_codes": ["C50.919"], # Breast cancer
        "step_therapy": ["letrozole"],
        "min_age": 18,
        "lab_thresholds": {"ER_status": "positive", "HER2_status": "negative"},
        "contraindications": [],
        "pa_required": True,
        "approval_duration_months": 6
    },
    {
        "insurer": "UnitedHealthcare",
        "category": "Oncology",
        "drug_name": "nivolumab",
        "brand_name": "Opdivo",
        "icd10_codes": ["C43.9"], # Melanoma
        "step_therapy": [],
        "min_age": 18,
        "lab_thresholds": {"BRAF_status": "wild-type"},
        "contraindications": ["pneumonitis"],
        "pa_required": True,
        "approval_duration_months": 6
    },
    {
        "insurer": "Humana",
        "category": "Oncology",
        "drug_name": "pembrolizumab",
        "brand_name": "Keytruda",
        "icd10_codes": ["C43.9"], # Melanoma
        "step_therapy": ["ipilimumab"],
        "min_age": 18,
        "lab_thresholds": {},
        "contraindications": ["autoimmune disease"],
        "pa_required": True,
        "approval_duration_months": 6
    },

    # 5. High-Tech Imaging
    {
        "insurer": "Aetna",
        "category": "Imaging",
        "drug_name": "mri_lumbar",
        "brand_name": "MRI Lumbar Spine",
        "icd10_codes": ["M54.5"], # Low back pain
        "step_therapy": ["physical therapy 6 weeks", "x-ray", "NSAIDs"],
        "min_age": 0,
        "lab_thresholds": {},
        "contraindications": ["implanted pacemaker"],
        "pa_required": True,
        "approval_duration_months": 1
    },
    {
        "insurer": "Cigna",
        "category": "Imaging",
        "drug_name": "pet_scan",
        "brand_name": "PET Scan Whole Body",
        "icd10_codes": ["C34.90", "C50.919", "C81.90"], # Oncology staging
        "step_therapy": ["ct_scan"],
        "min_age": 0,
        "lab_thresholds": {},
        "contraindications": ["pregnancy"],
        "pa_required": True,
        "approval_duration_months": 1
    },
    {
        "insurer": "UnitedHealthcare",
        "category": "Imaging",
        "drug_name": "ct_abdomen",
        "brand_name": "CT Abdomen/Pelvis",
        "icd10_codes": ["R10.9"], # Abdominal pain
        "step_therapy": ["ultrasound"],
        "min_age": 0,
        "lab_thresholds": {},
        "contraindications": ["severe renal impairment"],
        "pa_required": True,
        "approval_duration_months": 1
    },
    {
        "insurer": "Humana",
        "category": "Imaging",
        "drug_name": "mri_brain",
        "brand_name": "MRI Brain",
        "icd10_codes": ["G43.909", "R51"], # Headache
        "step_therapy": ["neurology consultation", "ct_head"],
        "min_age": 0,
        "lab_thresholds": {},
        "contraindications": ["implanted pacemaker"],
        "pa_required": True,
        "approval_duration_months": 1
    },

    # 6. Mental Health
    {
        "insurer": "Aetna",
        "category": "Mental Health",
        "drug_name": "esketamine",
        "brand_name": "Spravato",
        "icd10_codes": ["F33.2"], # MDD
        "step_therapy": ["SSRI", "SNRI", "bupropion"],
        "min_age": 18,
        "lab_thresholds": {},
        "contraindications": ["aneurysmal vascular disease"],
        "pa_required": True,
        "approval_duration_months": 3
    },
    {
        "insurer": "Cigna",
        "category": "Mental Health",
        "drug_name": "lurasidone",
        "brand_name": "Latuda",
        "icd10_codes": ["F20.9", "F31.9"], # Schizophrenia, Bipolar
        "step_therapy": ["aripiprazole", "risperidone"],
        "min_age": 10,
        "lab_thresholds": {},
        "contraindications": ["strong CYP3A4 inhibitors"],
        "pa_required": True,
        "approval_duration_months": 12
    },
    {
        "insurer": "UnitedHealthcare",
        "category": "Mental Health",
        "drug_name": "cariprazine",
        "brand_name": "Vraylar",
        "icd10_codes": ["F31.9", "F33.2"],
        "step_therapy": ["quetiapine", "aripiprazole"],
        "min_age": 18,
        "lab_thresholds": {},
        "contraindications": [],
        "pa_required": True,
        "approval_duration_months": 12
    },
    {
        "insurer": "Humana",
        "category": "Mental Health",
        "drug_name": "brexanolone",
        "brand_name": "Zulresso",
        "icd10_codes": ["F53.0"], # Postpartum depression
        "step_therapy": ["oral antidepressants 4 weeks"],
        "min_age": 18,
        "lab_thresholds": {},
        "contraindications": ["ESRD"],
        "pa_required": True,
        "approval_duration_months": 1
    }
]

def main():
    os.makedirs(os.path.join(os.path.dirname(__file__), "../config"), exist_ok=True)
    out_path = os.path.join(os.path.dirname(__file__), "../config/insurer_rules.json")
    with open(out_path, "w") as f:
        json.dump(RULES, f, indent=2)
    print(f"Generated 24 rules at {out_path}")

if __name__ == "__main__":
    main()
