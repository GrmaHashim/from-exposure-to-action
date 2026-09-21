"""
Build the master occupation-level analysis table by joining every source in
data/raw/ on occupation code (see src/crosswalks/).

Planned columns (see docs/From_Exposure_to_Action_Data_Dictionary.xlsx ->
"Framework & Definitions" tab for exact definitions):

    - occupation_code (SOC), occupation_title
    - aioe_score                          (AIOE)                              [x] this pass
    - oecd_exposure_score                 (OECD AI Exposure Measure)          [ ] later pass
    - ilo_task_automation_share           (ILO, aggregated from task-level)   [ ] later pass
    - gpts_are_gpts_score                 (Eloundou et al.)                   [ ] later pass
    - composite_exposure_score            (standardized average of the four above)
    - impact_pattern                      (Automation / Transformation / Augmentation) [ ] needs ILO
    - anthropic_usage_automation_share    (Anthropic Economic Index)          [ ] later pass
    - anthropic_usage_augmentation_share  (Anthropic Economic Index)          [ ] later pass
    - employment_growth_rate              (BLS OEWS, multi-year)              [ ] later pass
    - job_zone                            (O*NET — education/experience/training)  [x] this pass
    - skill_profile_vector                (O*NET Skills/Abilities, for similarity calc) [x] this pass

This first pass joins AIOE + O*NET (the two sources fetched so far). It is
written so that adding OECD / ILO / GPTs-are-GPTs / BLS / Anthropic later is
just: write that fetch_*.py, add one loader function below in the same
shape, and add its column to `merge_all()`. Nothing else needs to change.

Run:
    python build_master_dataset.py

Requires data/raw/aioe/AIOE_DataAppendix.xlsx and
data/raw/onet_db_31_0/{Occupation Data,Job Zones,Essential Skills}.xlsx to
already exist (run fetch_aioe.py and fetch_onet.py first).
"""
from pathlib import Path

import numpy as np
import pandas as pd

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from crosswalks.soc_onet_crosswalk import (  # noqa: E402
    _find_column,
    load_onet_occupation_data,
    onet_soc_to_soc,
)

ONET_VERSION = "31_0"
RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"
PROCESSED_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"
ONET_DIR = RAW_DIR / f"onet_db_{ONET_VERSION}"

AIOE_PATH = RAW_DIR / "AIOE_DataAppendix.xlsx"
JOB_ZONES_PATH = ONET_DIR / "Job Zones.xlsx"
SKILLS_PATH = ONET_DIR / "Essential Skills.xlsx"


# ---------------------------------------------------------------------------
# Step 1: load each source into a small, tidy DataFrame keyed by occupation.
# ---------------------------------------------------------------------------

def load_aioe(path: Path = AIOE_PATH) -> pd.DataFrame:
    """
    Load the AIOE score at the SOC-occupation level from "Appendix A".

    AIOE_DataAppendix.xlsx's exact header row/column names can shift slightly
    between the paper's public releases, so this auto-detects the SOC-code
    column (header containing "SOC") and the score column (header containing
    "AIOE") rather than hard-coding a column name.
    """
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run fetch_aioe.py first.")

    raw = pd.read_excel(path, sheet_name="Appendix A", header=None)
    # AIOE's appendix sheets typically have a title row or two before the
    # real header — find the first row that has one SHORT cell (a column
    # label, not a sentence) mentioning "SOC" and a DIFFERENT short cell
    # mentioning "AIOE". Checking short + distinct cells (rather than just
    # "does this row contain both substrings anywhere") avoids mistaking a
    # single title cell like "Appendix A: AIOE by SOC code" for the header.
    MAX_HEADER_CELL_LEN = 25
    header_row = None
    for i in range(min(10, len(raw))):
        cells = raw.iloc[i].fillna("").astype(str)
        soc_positions = {
            j for j, v in enumerate(cells)
            if "soc" in v.lower() and len(v) <= MAX_HEADER_CELL_LEN
        }
        aioe_positions = {
            j for j, v in enumerate(cells)
            if "aioe" in v.lower() and len(v) <= MAX_HEADER_CELL_LEN
        }
        if soc_positions and aioe_positions and soc_positions != aioe_positions:
            header_row = i
            break
    if header_row is None:
        raise ValueError(
            f"Could not find a header row with separate 'SOC' and 'AIOE' columns in "
            f"the first 10 rows of 'Appendix A'. Open {path} manually and check its layout."
        )

    df = pd.read_excel(path, sheet_name="Appendix A", header=header_row)
    df.columns = [str(c).strip() for c in df.columns]

    soc_col = _find_column(df, "SOC")
    aioe_col = _find_column(df, "AIOE")
    title_col = None
    for c in df.columns:
        if "title" in c.lower() or "occupation" in c.lower():
            title_col = c
            break

    out = df[[soc_col, aioe_col]].rename(columns={soc_col: "soc_code", aioe_col: "aioe_score"})
    if title_col:
        out["occupation_title"] = df[title_col]
    out["soc_code"] = out["soc_code"].astype(str).str.strip()
    out = out.dropna(subset=["soc_code"])
    return out


def load_onet_with_soc() -> pd.DataFrame:
    """O*NET-SOC occupations with the derived 6-digit SOC code attached."""
    occ = load_onet_occupation_data()
    code_col = _find_column(occ, "O*NET-SOC Code")
    title_col = _find_column(occ, "Title")
    occ = occ.rename(columns={code_col: "onet_soc_code", title_col: "onet_title"})
    occ["soc_code"] = occ["onet_soc_code"].apply(onet_soc_to_soc)
    return occ[["onet_soc_code", "soc_code", "onet_title"]]


def load_job_zones(path: Path = JOB_ZONES_PATH) -> pd.DataFrame:
    """One Job Zone (1-5: education/experience/training required) per O*NET-SOC code."""
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run fetch_onet.py first.")
    df = pd.read_excel(path)
    df.columns = [str(c).strip() for c in df.columns]
    code_col = _find_column(df, "O*NET-SOC Code")
    zone_col = _find_column(df, "Job Zone")
    return df[[code_col, zone_col]].rename(columns={code_col: "onet_soc_code", zone_col: "job_zone"})


def load_skill_profile(path: Path = SKILLS_PATH) -> pd.DataFrame:
    """
    Build a wide skill-profile table: one row per O*NET-SOC code, one column
    per skill element (its Importance ("IM") rating), for use later in
    RQ4 (exposure vs. skill profile) and the professional-layer reskilling
    similarity calc (nearest lower-exposure occupation by skill vector).
    """
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run fetch_onet.py first.")
    df = pd.read_excel(path)
    df.columns = [str(c).strip() for c in df.columns]

    code_col = _find_column(df, "O*NET-SOC Code")
    element_col = _find_column(df, "Element Name")
    scale_col = _find_column(df, "Scale ID")
    value_col = _find_column(df, "Data Value")

    importance = df[df[scale_col] == "IM"]
    wide = importance.pivot_table(
        index=code_col, columns=element_col, values=value_col, aggfunc="mean"
    )
    wide.columns = [f"skill__{c.strip().lower().replace(' ', '_')}" for c in wide.columns]
    wide = wide.reset_index().rename(columns={code_col: "onet_soc_code"})
    return wide


# ---------------------------------------------------------------------------
# Step 2: join everything into one occupation-level master table.
# ---------------------------------------------------------------------------

def merge_all() -> pd.DataFrame:
    print("Loading AIOE (SOC-level exposure score) ...")
    aioe = load_aioe()
    print(f"  {len(aioe)} SOC occupations with an AIOE score")

    print("Loading O*NET occupation list (O*NET-SOC -> SOC) ...")
    onet = load_onet_with_soc()
    print(f"  {len(onet)} O*NET-SOC occupations")

    print("Loading O*NET Job Zones ...")
    job_zones = load_job_zones()

    print("Loading O*NET skill profile (Essential Skills, Importance ratings) ...")
    skills = load_skill_profile()

    # O*NET-SOC is finer-grained than SOC (one SOC code can map to several
    # O*NET-SOC codes). Attach job zone + skills at the O*NET-SOC level
    # first, then average up to the SOC level so every source lines up on
    # the same key AIOE uses.
    onet_detail = onet.merge(job_zones, on="onet_soc_code", how="left")
    onet_detail = onet_detail.merge(skills, on="onet_soc_code", how="left")

    skill_cols = [c for c in onet_detail.columns if c.startswith("skill__")]
    agg = {"job_zone": "mean", **{c: "mean" for c in skill_cols}}
    onet_by_soc = onet_detail.groupby("soc_code").agg(agg).reset_index()

    # Keep one representative O*NET title per SOC code for readability.
    titles = (
        onet_detail.sort_values("onet_soc_code")
        .drop_duplicates("soc_code")[["soc_code", "onet_title"]]
    )
    onet_by_soc = onet_by_soc.merge(titles, on="soc_code", how="left")

    print("Merging AIOE with O*NET on soc_code ...")
    master = aioe.merge(onet_by_soc, on="soc_code", how="outer", suffixes=("_aioe", "_onet"))

    # Prefer AIOE's own title when both are present; fall back to O*NET's.
    if "occupation_title" in master.columns:
        master["occupation_title"] = master["occupation_title"].fillna(master.get("onet_title"))
    else:
        master["occupation_title"] = master.get("onet_title")
    master = master.drop(columns=[c for c in ["onet_title"] if c in master.columns])

    # Composite exposure score: for now this is just the standardized AIOE
    # score, since AIOE is the only index loaded so far. Once
    # fetch_oecd_exposure.py / fetch_ilo_genai.py / fetch_gpts_are_gpts.py
    # exist, add their z-scored columns to this mean.
    master["composite_exposure_score"] = (
        master["aioe_score"] - master["aioe_score"].mean()
    ) / master["aioe_score"].std()

    # impact_pattern needs ILO's per-task score variance (see RQ2 in the
    # notebook) — left as NaN until that source is joined.
    master["impact_pattern"] = np.nan

    cols_first = ["soc_code", "occupation_title", "aioe_score", "composite_exposure_score",
                  "impact_pattern", "job_zone"]
    other_cols = [c for c in master.columns if c not in cols_first]
    master = master[cols_first + other_cols]

    return master


def save(master: pd.DataFrame) -> Path:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / "master_occupations.csv"
    master.to_csv(out_path, index=False)
    return out_path


if __name__ == "__main__":
    master = merge_all()
    out_path = save(master)
    print(f"\nDone. {len(master)} occupations in the master table.")
    print(f"Saved: {out_path}")
    print(f"Columns: {list(master.columns)}")
