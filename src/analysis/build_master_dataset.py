"""
Build the master occupation-level analysis table by joining every source in
data/raw/ on occupation code (see src/crosswalks/).

Planned columns (see docs/From_Exposure_to_Action_Data_Dictionary.xlsx ->
"Framework & Definitions" tab for exact definitions):

    - occupation_code (SOC), occupation_title
    - aioe_score                          (AIOE)                              [x] this pass
    - ilo_score                           (ILO occupation-level, ISCO-08)     [x] this pass
    - ilo_task_mean / ilo_task_std        (ILO task-level, ISCO-08)           [x] this pass
    - oecd_exposure_score                 (OECD AI Exposure Measure)          [ ] later pass
    - gpts_are_gpts_score                 (Eloundou et al.)                   [ ] later pass
    - composite_exposure_score            (standardized average of available indices)
    - impact_pattern                      (Automation / Transformation / Augmentation) [x] this pass, provisional
    - anthropic_usage_automation_share    (Anthropic Economic Index)          [ ] later pass
    - anthropic_usage_augmentation_share  (Anthropic Economic Index)          [ ] later pass
    - employment_growth_rate              (BLS OEWS, multi-year)              [ ] later pass
    - job_zone                            (O*NET — education/experience/training)  [x] this pass
    - skill_profile_vector                (O*NET Skills/Abilities, for similarity calc) [x] this pass

This pass joins AIOE + O*NET + ILO. It is written so that adding OECD /
GPTs-are-GPTs / BLS / Anthropic later is just: write that fetch_*.py, add
one loader function below in the same shape, and add its column to
`merge_all()`. Nothing else needs to change.

impact_pattern classification (provisional): ILO's task-level file gives
each occupation a distribution of exposure scores across its own tasks.
This pass classifies an occupation by comparing its task_mean and task_std
against the distribution of those same statistics across ALL occupations:

    - high internal variance (std above the cross-occupation median)
      -> "Transformation": some tasks are exposed and others aren't, so
         the job's task MIX changes shape rather than the whole job
         automating or staying human-only.
    - low variance + high mean (top third across occupations)
      -> "Automation": most of the job's tasks are similarly exposed.
    - low variance + low/mid mean
      -> "Augmentation": most of the job's tasks have low exposure, so AI
         likely extends output on a subset rather than replacing tasks.

This is a first-pass heuristic, not a validated model -- RQ2 in the
notebook cross-checks it against the Anthropic Economic Index's own
automation/augmentation usage split once that source is added (see
src/data_acquisition/README.md). Treat impact_pattern as provisional until
that cross-check happens.

Run:
    python build_master_dataset.py

Requires (run the matching fetch_*.py first for anything missing):
    data/raw/AIOE_DataAppendix.xlsx
    data/raw/onet_db_31_0/{Occupation Data,Job Zones,Essential Skills}.xlsx
    data/raw/ILO_Final_Scores_ISCO08_Gmyrek_et_al_2025.xlsx
    data/raw/ISCO_SOC_2010_Crosswalk.xls
    data/raw/SOC_2010_to_2018_Crosswalk.xlsx

(fetch_ilo_genai.py also downloads ILO_4digits_with_tasks.xlsx, but that
file turns out to hold only categorical exposure labels rather than a
numeric score -- see load_ilo_task_scores()'s docstring -- so it isn't
read by this script.)
"""
from pathlib import Path

import numpy as np
import pandas as pd

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from crosswalks.soc_onet_crosswalk import (  # noqa: E402
    _find_column,
    build_isco_to_soc2018,
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
ILO_OCCUPATION_PATH = RAW_DIR / "ILO_Final_Scores_ISCO08_Gmyrek_et_al_2025.xlsx"


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
    # real header -- find the first row that has one SHORT cell (a column
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


def load_ilo_occupation_scores(path: Path = ILO_OCCUPATION_PATH) -> pd.DataFrame:
    """
    Load ILO's occupation-level exposure score, keyed by ISCO-08 4-digit code.

    Final_Scores_ISCO08_Gmyrek_et_al_2025.xlsx is stored at TASK granularity
    (one row per task, ISCO_08 code repeated for every task under that
    occupation) but already carries each occupation's aggregate as
    mean_score_2025 -- so the occupation-level score here is just that
    column, deduplicated to one row per ISCO_08 code. Uses the 2025
    (GPT-4o/Gemini-updated) score rather than the original 2023 score, per
    fetch_ilo_genai.py's module docstring ("2025 update").
    """
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run fetch_ilo_genai.py first.")
    df = pd.read_excel(path)
    df.columns = [str(c).strip() for c in df.columns]

    out = df[["ISCO_08", "mean_score_2025"]].rename(
        columns={"ISCO_08": "isco_code", "mean_score_2025": "ilo_score"}
    )
    out["isco_code"] = _clean_isco(out["isco_code"])
    return out.dropna(subset=["isco_code", "ilo_score"]).drop_duplicates(subset=["isco_code"])


def load_ilo_task_scores(path: Path = ILO_OCCUPATION_PATH) -> pd.DataFrame:
    """
    Task-level score mean/std per occupation, for the provisional
    impact_pattern classification (see module docstring).

    Final_Scores_ISCO08_Gmyrek_et_al_2025.xlsx already carries each
    occupation's task-score mean_score_2025 / SD_2025 pre-computed (same
    file load_ilo_occupation_scores() reads -- one row per task, aggregate
    repeated across that occupation's rows), so this is a dedup rather than
    a fresh groupby.

    ILO_4digits_with_tasks.xlsx -- this project's OTHER ILO download,
    originally intended for this -- turns out to carry only categorical
    exposure labels ('Not Exposed' / 'Minimal Exposure' / 'Exposed:
    Gradient 1-4') rather than a numeric score, so it isn't usable for a
    mean/std calculation and isn't loaded here.
    """
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run fetch_ilo_genai.py first.")
    df = pd.read_excel(path)
    df.columns = [str(c).strip() for c in df.columns]

    out = df[["ISCO_08", "mean_score_2025", "SD_2025"]].rename(
        columns={"ISCO_08": "isco_code", "mean_score_2025": "ilo_task_mean", "SD_2025": "ilo_task_std"}
    )
    out["isco_code"] = _clean_isco(out["isco_code"])
    return out.dropna(subset=["isco_code", "ilo_task_mean"]).drop_duplicates(subset=["isco_code"])


def classify_impact_pattern(ilo_by_isco: pd.DataFrame) -> pd.DataFrame:
    """
    Add an `impact_pattern` column using the provisional rule described in
    the module docstring. Thresholds (tertiles of the mean, median of the
    std) are computed from this dataset's own distribution rather than
    fixed constants, so the rule adapts to whatever scale ILO's scores use.
    """
    out = ilo_by_isco.copy()
    mean_p33 = out["ilo_task_mean"].quantile(1 / 3)
    mean_p66 = out["ilo_task_mean"].quantile(2 / 3)
    std_median = out["ilo_task_std"].median()

    def _classify(row) -> str:
        if row["ilo_task_std"] > std_median:
            return "Transformation"
        if row["ilo_task_mean"] >= mean_p66:
            return "Automation"
        return "Augmentation"

    out["impact_pattern"] = out.apply(_classify, axis=1)
    return out


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

    print("Loading ILO occupation-level exposure scores (ISCO-08) ...")
    ilo_occ = load_ilo_occupation_scores()
    print(f"  {len(ilo_occ)} ISCO-08 occupations with an ILO score")

    print("Loading ILO task-level scores and classifying impact_pattern ...")
    ilo_tasks = load_ilo_task_scores()
    ilo_by_isco = ilo_occ.merge(ilo_tasks, on="isco_code", how="outer")
    ilo_by_isco = classify_impact_pattern(ilo_by_isco)
    print(f"  impact_pattern counts: {ilo_by_isco['impact_pattern'].value_counts().to_dict()}")

    print("Building ISCO-08 -> SOC 2018 crosswalk and mapping ILO onto it ...")
    isco_crosswalk = build_isco_to_soc2018()
    ilo_by_isco_soc = ilo_by_isco.merge(
        isco_crosswalk[["isco_code", "soc_2018"]], on="isco_code", how="left"
    )
    unmatched = ilo_by_isco_soc["soc_2018"].isna().sum()
    if unmatched:
        print(f"  Note: {unmatched} ISCO-08 occupations had no SOC 2018 match and were dropped.")
    ilo_by_isco_soc = ilo_by_isco_soc.dropna(subset=["soc_2018"]).rename(columns={"soc_2018": "soc_code"})

    # Several ISCO-08 codes can map to the same SOC 2018 code (and vice
    # versa) -- average the numeric fields and take the most common
    # impact_pattern label per SOC code, same aggregation approach used
    # for O*NET-SOC -> SOC below.
    ilo_by_soc = ilo_by_isco_soc.groupby("soc_code").agg(
        ilo_score=("ilo_score", "mean"),
        ilo_task_mean=("ilo_task_mean", "mean"),
        ilo_task_std=("ilo_task_std", "mean"),
        impact_pattern=("impact_pattern", lambda s: s.mode().iloc[0] if not s.mode().empty else np.nan),
    ).reset_index()
    print(f"  {len(ilo_by_soc)} SOC 2018 occupations with ILO data after aggregation")

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

    print("Merging AIOE + O*NET + ILO on soc_code ...")
    master = aioe.merge(onet_by_soc, on="soc_code", how="outer", suffixes=("_aioe", "_onet"))
    master = master.merge(ilo_by_soc, on="soc_code", how="outer")

    # Prefer AIOE's own title when both are present; fall back to O*NET's.
    if "occupation_title" in master.columns:
        master["occupation_title"] = master["occupation_title"].fillna(master.get("onet_title"))
    else:
        master["occupation_title"] = master.get("onet_title")
    master = master.drop(columns=[c for c in ["onet_title"] if c in master.columns])

    # Composite exposure score: mean of whichever standardized (z-scored)
    # index columns are available per row, so an occupation missing one
    # index (e.g. no ILO match) still gets a score from the other(s). Once
    # fetch_oecd_exposure.py / fetch_gpts_are_gpts.py exist, add their
    # z-scored columns to `index_cols` below -- nothing else needs to change.
    index_cols = ["aioe_score", "ilo_score"]
    z_cols = []
    for col in index_cols:
        z_col = f"_z_{col}"
        master[z_col] = (master[col] - master[col].mean()) / master[col].std()
        z_cols.append(z_col)
    master["composite_exposure_score"] = master[z_cols].mean(axis=1, skipna=True)
    master = master.drop(columns=z_cols)

    cols_first = ["soc_code", "occupation_title", "aioe_score", "ilo_score",
                  "composite_exposure_score", "impact_pattern", "job_zone"]
    other_cols = [c for c in master.columns if c not in cols_first]
    master = master[cols_first + other_cols]

    return master


def save(master: pd.DataFrame) -> Path:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / "master_occupations.csv"
    master.to_csv(out_path, index=False)
    return out_path


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _clean_isco(series: pd.Series) -> pd.Series:
    """Same float-artifact cleanup as soc_onet_crosswalk._clean_code_series (ISCO codes only)."""
    cleaned = series.astype(str).str.strip()
    return cleaned.str.replace(r"^(\d+)\.0$", r"\1", regex=True)


if __name__ == "__main__":
    master = merge_all()
    out_path = save(master)
    print(f"\nDone. {len(master)} occupations in the master table.")
    print(f"Saved: {out_path}")
    print(f"Columns: {list(master.columns)}")
