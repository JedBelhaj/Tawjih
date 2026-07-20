import pandas as pd
import re
import math
from pathlib import Path

# =====================================================================
# 1. EASY CONFIGURATION
# =====================================================================
PROJECT_ROOT = Path.cwd().parent
PROGRAMS_FILE = PROJECT_ROOT / "data" / "final" / "tawjih_scraped.csv"
FORMULAS_FILE = PROJECT_ROOT / "data" / "final" / "formulas.csv"

# Filter settings to keep your results clean and accurate
YEAR_FILTER = 2025                  # Year of historical cutoffs to evaluate against
BAC_TRACK_ARABIC = "علوم الإعلامية"   # Target track in your main data file
BAC_TRACK_ENGLISH = "Informatique"  # Target track in your formulas file

# Input your main and control session marks: (Main, Control)
# If you only sat a subject in one session, put None for the other.
USER_MARKS = {
    "MG":   (9.16, 10.0),       # Moyenne Générale
    "M":    (7.25, 8.0),        # Mathématiques
    "Algo": (8.5, 9.16),        # Algorithmique
    "SP":   (3.75, None),       # Sciences Physiques
    "STI":  (10.4, 12.65),      # Sciences et Technologies de l'Informatique
    "F":    (8.0, 6.25),        # Français
    "Ang":  (15.0, 17.5),       # Anglais
    "A":    (9.75, 9.25),       # Arabe
    "PH":   (6.25, None),       # Philosophie
    "EP":   (18.67, None),      # Éducation Physique
    "ESP":  (13.0, None),       # Espagnol
}

# =====================================================================
# 2. DATA LOADING & PRE-FILTERING
# =====================================================================
# Load datasets
programs = pd.read_csv(PROGRAMS_FILE, encoding="utf-8-sig")
formulas = pd.read_csv(FORMULAS_FILE, encoding="utf-8-sig")

# Fix: Filter down to your specific track and year immediately to eradicate noisy duplicates
filtered_programs = programs[
    (programs["year"] == YEAR_FILTER) & 
    (programs["bac_type"] == BAC_TRACK_ARABIC) & 
    (programs["orientation_score"] > 0)
].copy()

# Filter and prepare formulas
bac_formulas = formulas[formulas["bac_type"] == BAC_TRACK_ENGLISH].copy()

# Normalize lookup keys
filtered_programs["program_code_3digit"] = filtered_programs["program_code"].astype(str).str[-3:].str.strip().str.zfill(3)
bac_formulas["program_code_3digit"] = bac_formulas["program_code_3digit"].astype(str).str.strip().str.zfill(3)

# Merge programs with their respective calculation formulas
results = filtered_programs.merge(
    bac_formulas[["program_code_3digit", "formula"]],
    on="program_code_3digit",
    how="left"
)

# =====================================================================
# 3. SCORE CALCULATION ENGINE
# =====================================================================
def calculate_final_mark(main, control=None):
    if control is None or pd.isna(control):
        return main
    return (2 * main + control) / 3

# Compute final calculated mark dictionaries
calculated_marks = {sub: calculate_final_mark(*marks) for sub, marks in USER_MARKS.items()}

# Calculate Base Formula Group Score (FG)
FG = (
    4 * calculated_marks["MG"]
    + 1.5 * calculated_marks["M"]
    + 1.5 * calculated_marks["Algo"]
    + 0.5 * calculated_marks["SP"]
    + 0.5 * calculated_marks["STI"]
    + calculated_marks["F"]
    + calculated_marks["Ang"]
)

# Build the evaluation context variable mapping
eval_variables = {"FG": FG, **calculated_marks, "max": max}

def parse_and_eval_formula(formula, variables):
    if pd.isna(formula):
        return None
    
    f_str = str(formula).strip()
    
    # Fix 1: Convert implicit math strings like "2A" or "1.5M" to valid Python "2*A" or "1.5*M"
    f_str = re.sub(r'(\d+(?:\.\d+)?)([a-zA-Z])', r'\1*\2', f_str)
    
    # Fix 2: Translate sheet style Max equations like Max((Ang-15)|0) -> max((Ang-15), 0)
    f_str = f_str.replace("Max", "max").replace("|", ",")
    
    try:
        # Evaluate formula securely safely overriding global builtins to protect execution
        return eval(f_str, {"__builtins__": {}}, variables)
    except Exception:
        # Gracefully handle formulas relying on optional subjects you skipped (e.g. Italian "IT")
        return None

# Map scores across your profile entries
results["T_score"] = results["formula"].apply(lambda f: parse_and_eval_formula(f, eval_variables))
print(f"Your calculated Formule Globale (FG) score is: {FG:.2f}")

# =====================================================================
# 4. EASY SEARCH ENGINE FUNCTION
# =====================================================================
def search_programs(above=5, below=15, keyword=None):
    """
    Filters options based on safety margins and text searches.
    above: max points the school's historical cutoff can be OVER your T_Score (Reach options)
    below: max points the school's historical cutoff can be UNDER your T_Score (Safety options)
    """
    df = results.dropna(subset=["T_score"]).copy()
    
    # Filter by a reliable range matching your competitive brackets
    df = df[
        (df["orientation_score"] <= df["T_score"] + above) & 
        (df["orientation_score"] >= df["T_score"] - below)
    ]
    
    # Apply keyword searches across names, locations, or institution types
    if keyword:
        df = df[
            df["program_name"].str.contains(keyword, case=False, na=False) |
            df["institution"].str.contains(keyword, case=False, na=False) |
            df["university"].str.contains(keyword, case=False, na=False)
        ]
        
    # Calculate admission index margin to see how safely you clear past requirements
    df["safety_margin"] = df["T_score"] - df["orientation_score"]
    
    output_cols = ["program_name", "institution", "university", "program_code", "orientation_score", "T_score", "safety_margin"]
    return df[output_cols].sort_values(by="safety_margin", ascending=False)

print(search_programs(above=3, below=15))