"""
Shared data-loading and formatting helpers for the Phase 2 Streamlit app.

Design constraint (important): this app is deployed on Streamlit Community
Cloud directly from the public GitHub repo. Per .gitignore, data/raw/ is
NOT committed (only data/processed/master_occupations.csv is). So every
page in this app must work from data/processed/master_occupations.csv
alone -- never call a data_acquisition/analysis function that reads from
data/raw/ (e.g. load_ilo_task_detail(), which needs the raw ILO Excel
file). The one exception is nearest_lower_exposure_alternatives(), which
only needs the already-merged master table, not any raw file.
"""
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

REPO_ROOT = Path(__file__).resolve().parent.parent
MASTER_CSV_PATH = REPO_ROOT / "data" / "processed" / "master_occupations.csv"
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# Imported lazily inside get_alternatives() rather than at module load time,
# so that a page which never needs the reskilling search (Home, Explore)
# doesn't pay the import cost of scikit-learn / the crosswalks module.

IMPACT_PATTERN_DEFINITIONS = {
    "Automation": "AI performs the task itself; human labor input for that task drops toward zero.",
    "Transformation": "The job's mix of tasks changes shape — some tasks automate, others emerge or "
                        "grow in importance — the occupation persists but looks different.",
    "Augmentation": "AI extends or enhances human output on a task rather than replacing the human "
                     "performing it.",
}

JOB_ZONE_DESCRIPTIONS = {
    1: "Little or no preparation needed",
    2: "Some preparation needed",
    3: "Medium preparation needed",
    4: "Considerable preparation needed",
    5: "Extensive preparation needed",
}

REQUIRED_COLUMNS = ["soc_code", "occupation_title", "composite_exposure_score"]


@st.cache_data(show_spinner="Loading occupation dataset...")
def load_master() -> pd.DataFrame:
    """
    Load the processed master occupation table. Cached for the life of the
    app session (Streamlit re-runs the whole script on every interaction,
    so without caching this CSV would be re-read from disk on every click).
    """
    if not MASTER_CSV_PATH.exists():
        raise FileNotFoundError(
            f"{MASTER_CSV_PATH} not found. Run `python src/analysis/build_master_dataset.py` "
            "from the repo root first (see README.md Setup) to generate it."
        )
    df = pd.read_csv(MASTER_CSV_PATH)
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"{MASTER_CSV_PATH} is missing expected column(s) {missing}. "
            "It may be stale -- try regenerating it with build_master_dataset.py."
        )
    return df


def get_skill_cols(df: pd.DataFrame) -> list:
    return [c for c in df.columns if c.startswith("skill__")]


@st.cache_data(show_spinner="Searching for skill-similar, lower-exposure occupations...")
def get_alternatives(source_soc: str, df: pd.DataFrame, skill_cols: list, n: int = 5, min_gap: float = 0.0):
    from analysis.build_master_dataset import nearest_lower_exposure_alternatives
    return nearest_lower_exposure_alternatives(source_soc, df, skill_cols, n=n, min_gap=min_gap)


def exposure_percentile(df: pd.DataFrame, score: float) -> float:
    """Share of occupations at or below `score` on composite_exposure_score, as a percent."""
    valid = df["composite_exposure_score"].dropna()
    if valid.empty or pd.isna(score):
        return float("nan")
    return float((valid <= score).mean() * 100)


def job_zone_label(job_zone) -> str:
    if pd.isna(job_zone):
        return "Not available"
    zone_int = round(float(job_zone))
    zone_int = min(max(zone_int, 1), 5)
    desc = JOB_ZONE_DESCRIPTIONS.get(zone_int, "")
    return f"Zone {job_zone:.1f} — {desc}"
