"""
Build the master occupation-level analysis table by joining every source in
data/raw/ on occupation code (see src/crosswalks/).

Planned columns (see docs/From_Exposure_to_Action_Data_Dictionary.xlsx ->
"Framework & Definitions" tab for exact definitions):

    - occupation_code (SOC), occupation_title
    - aioe_score                          (AIOE)                              [x] this pass
    - ilo_score                           (ILO occupation-level, ISCO-08)     [x] this pass
    - ilo_task_mean / ilo_task_std        (ILO task-level, ISCO-08)           [x] this pass
    - oecd_exposure_score                 (OECD AI Exposure Measure)          [ ] DROPPED -- see note below
    - gpts_are_gpts_score                 (Eloundou et al., dv_rating_beta)   [x] this pass
    - gpts_are_gpts_human_score           (Eloundou et al., human_rating_beta) [x] this pass, reference only
    - composite_exposure_score            (standardized average of available indices)
    - impact_pattern                      (Automation / Transformation / Augmentation) [x] this pass, provisional
    - anthropic_1p_automation_share       (Anthropic Economic Index, 1P API)  [x] this pass
    - anthropic_1p_augmentation_share     (Anthropic Economic Index, 1P API)  [x] this pass
    - anthropic_claude_ai_*_share         (Anthropic Economic Index, claude.ai) [ ] blocked -- see note below
    - employment_growth_rate              (BLS OEWS, multi-year, CAGR 2023->2025) [x] this pass
    - job_zone                            (O*NET — education/experience/training)  [x] this pass
    - skill_profile_vector                (O*NET Skills/Abilities, for similarity calc) [x] this pass

OECD AI Exposure Measure: DROPPED from this project. Verified (not assumed)
that no downloadable dataset file exists anywhere yet -- OECD AI Papers
No. 59 describes the results in its PDF text only. Not a bug to fix;
documented as a known limitation in src/data_acquisition/README.md.

Anthropic Economic Index: the 1P API release (global-only, unambiguous) is
integrated this pass. The claude.ai release also exists and is richer (it
would let RQ2's cross-check use the larger, more representative Claude.ai
usage base instead of just the API), but it carries per-COUNTRY breakdowns
and multiple classification hierarchy_level values, and which exact
geo_id/geo_level value is the global aggregate hasn't been confirmed yet --
integrating it without that confirmation risks silently joining one
country's numbers instead of the worldwide total. Left for a later pass
once confirmed; 1P API alone is enough to unblock RQ2's cross-check.

This pass joins AIOE + O*NET + ILO + GPTs-are-GPTs + Anthropic (1P API) +
BLS OEWS (employment_growth_rate). It is written so that adding OECD (if it
ever ships) / the claude.ai AEI release later is just: write/finish that
fetch_*.py, add one loader function below in the same shape, and add its
column to `merge_all()`. Nothing else needs to change.

BLS OEWS: bls.gov blocks scripted downloads at the WAF level (same as the
ISCO/SOC crosswalks), so `data/raw/oesm23nat.zip`, `oesm24nat.zip`, and
`oesm25nat.zip` must be downloaded manually (see
src/data_acquisition/README.md). `load_bls_oews_growth()` reduces each
year's national "All Data" table to one economy-wide, detailed-occupation
row per SOC code, then computes employment_growth_rate as the annualized
(CAGR) change in total employment between the earliest and latest year
present. This is OPTIONAL at merge_all() time -- if fewer than 2 of the 3
zip files are present, merge_all() skips it and employment_growth_rate is
simply absent from the master table, rather than the whole run failing.

Statistics Canada is intentionally NOT loaded here -- see
load_statcan_noc_exposure() below, which is appendix-only (NOC-keyed, no
SOC crosswalk, feeds one standalone comparison chart in the notebook, not
the master table) per this project's guardrails.

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
    data/raw/GPTs_are_GPTs_occ_level.csv
    data/raw/AEI_aei_1p_api_<release-date>.csv
    data/raw/oesm23nat.zip, oesm24nat.zip, oesm25nat.zip (optional -- see
        the BLS OEWS note above; needs >=2 of the 3 for employment_growth_rate)

(fetch_ilo_genai.py also downloads ILO_4digits_with_tasks.xlsx, but that
file turns out to hold only categorical exposure labels rather than a
numeric score -- see load_ilo_task_scores()'s docstring -- so it isn't
read by this script.)
"""
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from crosswalks.soc_onet_crosswalk import (  # noqa: E402
    _clean_isco_code_series,
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
TRANSFERABLE_SKILLS_PATH = ONET_DIR / "Transferable Skills.xlsx"
KNOWLEDGE_PATH = ONET_DIR / "Knowledge.xlsx"
CIP_SOC_CROSSWALK_PATH = RAW_DIR / "CIP2020_SOC2018_Crosswalk.xlsx"
ILO_OCCUPATION_PATH = RAW_DIR / "ILO_Final_Scores_ISCO08_Gmyrek_et_al_2025.xlsx"
GPTS_ARE_GPTS_PATH = RAW_DIR / "GPTs_are_GPTs_occ_level.csv"
STATCAN_HTML_PATH = RAW_DIR / "StatCan_11F0019M2024005_AI_Occupational_Exposure.html"
BLS_OEWS_ZIPS = {
    2023: RAW_DIR / "oesm23nat.zip",
    2024: RAW_DIR / "oesm24nat.zip",
    2025: RAW_DIR / "oesm25nat.zip",
}

# fetch_anthropic_economic_index.py's output filenames carry the release
# date (e.g. AEI_aei_1p_api_2026-06-26.csv) so re-running it after a new
# Anthropic release doesn't silently overwrite the previous snapshot -- good
# for data provenance, but it means we can't hard-code today's date here.
# Glob for the pattern and take the lexicographically-latest match (works
# because the date is in YYYY-MM-DD order) instead.
AEI_1P_API_GLOB = "AEI_aei_1p_api_*.csv"


def _latest_matching_file(directory: Path, pattern: str) -> Path:
    matches = sorted(directory.glob(pattern))
    if not matches:
        raise FileNotFoundError(
            f"No file matching '{pattern}' found in {directory}. "
            "Run fetch_anthropic_economic_index.py first."
        )
    return matches[-1]


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


def _load_onet_wide_importance(path: Path, prefix: str) -> pd.DataFrame:
    """
    Shared pivot logic for any O*NET table shaped like Essential Skills.xlsx
    (one row per O*NET-SOC code x Element Name x Scale ID, with an
    Importance ("IM") and a Level ("LV") rating per row) -- Essential
    Skills.xlsx, Transferable Skills.xlsx, and Knowledge.xlsx all share this
    exact schema. Pivots to one row per O*NET-SOC code, one column per
    element's Importance rating, with `prefix` so the three resulting
    tables' columns never collide once merged onto the same master table
    (skill__* / xfskill__* / knowledge__*).
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
    wide.columns = [f"{prefix}{c.strip().lower().replace(' ', '_')}" for c in wide.columns]
    wide = wide.reset_index().rename(columns={code_col: "onet_soc_code"})
    return wide


def load_skill_profile(path: Path = SKILLS_PATH) -> pd.DataFrame:
    """
    Build a wide skill-profile table (skill__* columns) from O*NET's Basic
    Skills (Essential Skills.xlsx): one row per O*NET-SOC code, one column
    per skill element's Importance rating. These 10 skills are broad,
    cognitive/developmental skills shared by almost every occupation
    (Reading Comprehension, Mathematics, Critical Thinking, ...) -- used by
    RQ4 in the notebook.

    See also load_transferable_skills() and load_knowledge_profile(), added
    after a real-data test showed that skill__* alone is too generic to
    meaningfully distinguish occupations for the professional-layer
    reskilling similarity calc (nearest_lower_exposure_alternatives()):
    raw cosine similarity on just these 10 columns ranked e.g. Stonemasons
    99.7% "similar" to Data Scientists, because nearly every occupation
    rates baseline literacy/communication skills moderately-to-highly
    important. The reskilling calc now uses skill__* + xfskill__* +
    knowledge__* together (see app/pages/2_Reskilling_Alternatives.py);
    RQ4 still uses skill__* alone for now (revisit separately -- H4's own
    hypothesis is actually about social/physical/supervisory skills, which
    skill__* doesn't cover either; xfskill__* has the social ones).
    """
    return _load_onet_wide_importance(path, "skill__")


def load_transferable_skills(path: Path = TRANSFERABLE_SKILLS_PATH) -> pd.DataFrame:
    """
    Build a wide table (xfskill__* columns) from O*NET's Cross-Functional /
    "Transferable" Skills (Transferable Skills.xlsx): 24 more specific
    skills including Programming, Troubleshooting, Repairing, Systems
    Analysis, Equipment Maintenance, Negotiation, Social Perceptiveness,
    Management of Personnel Resources, etc. -- these are the skills that
    actually differ sharply between, say, a data scientist and an
    electrician, unlike the generic skill__* Basic Skills. Split out of
    O*NET's old combined Skills.xlsx as of O*NET v31.0 (see this project's
    first commit / src/data_acquisition/README.md); fetch_onet.py already
    downloads this file, it just wasn't loaded until now.
    """
    return _load_onet_wide_importance(path, "xfskill__")


def load_knowledge_profile(path: Path = KNOWLEDGE_PATH) -> pd.DataFrame:
    """
    Build a wide table (knowledge__* columns) from O*NET's Knowledge domain
    (Knowledge.xlsx): 33 subject-matter areas (Computers and Electronics,
    Engineering and Technology, Medicine and Dentistry, Mechanical,
    Building and Construction, Law and Government, ...). This is the most
    occupation-SPECIFIC of the three O*NET importance-rating tables used in
    this project -- most occupations score near-zero on most of these 33
    domains and high on just one or two, which is exactly the kind of
    signal that distinguishes, e.g., "needs a Computer Science-adjacent
    background" from "needs a Medicine-adjacent background." Combined with
    skill__* and xfskill__* for the professional-layer reskilling
    similarity calc.
    """
    return _load_onet_wide_importance(path, "knowledge__")


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
    out["isco_code"] = _clean_isco_code_series(out["isco_code"])
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
    out["isco_code"] = _clean_isco_code_series(out["isco_code"])
    return out.dropna(subset=["isco_code", "ilo_task_mean"]).drop_duplicates(subset=["isco_code"])


def load_ilo_task_detail(path: Path = ILO_OCCUPATION_PATH) -> pd.DataFrame:
    """
    Load ILO's TASK-level detail -- NOT deduplicated to one row per
    occupation like load_ilo_task_scores() -- for RQ3's "which tasks within
    an occupation carry the highest ILO exposure scores" question.

    Confirmed via real file inspection (not assumed): score_2025 is a
    genuine per-TASK score that varies across taskID within the same
    ISCO_08 occupation (e.g. two tasks under ISCO 1112 "Senior Government
    Officials" scored 0.350 and 0.435), unlike mean_score_2025/SD_2025
    which are occupation-level aggregates repeated identically across every
    task row under that occupation -- those are what
    load_ilo_occupation_scores()/load_ilo_task_scores() already use.
    Task_ISCO carries the actual task description text.

    Standalone / illustrative use only, same pattern as
    load_statcan_noc_exposure() -- NOT called from merge_all(), since
    task-level granularity doesn't fit the one-row-per-occupation master
    table. Call this directly from the notebook's RQ3 section instead.
    """
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run fetch_ilo_genai.py first.")
    df = pd.read_excel(path)
    df.columns = [str(c).strip() for c in df.columns]

    required = ["ISCO_08", "Title", "taskID", "Task_ISCO", "score_2025", "mean_score_2025"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise KeyError(
            f"Expected column(s) {missing} not found in {path}. "
            f"Available columns: {list(df.columns)}"
        )

    out = df[required].rename(columns={
        "ISCO_08": "isco_code",
        "Title": "occupation_title",
        "taskID": "task_id",
        "Task_ISCO": "task_description",
        "score_2025": "task_score_2025",
        "mean_score_2025": "occupation_mean_score_2025",
    })
    out["isco_code"] = _clean_isco_code_series(out["isco_code"])
    return out.dropna(subset=["isco_code", "task_score_2025"])


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


def load_gpts_are_gpts_scores(path: Path = GPTS_ARE_GPTS_PATH) -> pd.DataFrame:
    """
    Load "GPTs are GPTs" exposure scores, keyed by O*NET-SOC code.

    Uses dv_rating_beta (GPT-4-generated label, beta = E1 + 0.5*E2) as this
    project's gpts_are_gpts_score, for consistency with AIOE/ILO -- all
    three are automated/model-based measures, rather than a one-off human
    annotation exercise. IMPORTANT: the paper's own well-known headline
    figures ("80% of workers have >=10% of tasks exposed, 19% have >=50%")
    are based on human_rating_beta, NOT dv_rating_beta -- confirmed against
    the paper's own text, not inferred (see fetch_gpts_are_gpts.py's module
    docstring). human_rating_beta is kept alongside as
    gpts_are_gpts_human_score so that headline figure can still be cited
    correctly, and so the two can be cross-checked against each other (the
    paper reports they're highly correlated -- worth re-verifying here, same
    pattern as RQ1's AIOE-vs-ILO Spearman check).
    """
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run fetch_gpts_are_gpts.py first.")
    df = pd.read_csv(path)
    df.columns = [str(c).strip() for c in df.columns]
    code_col = _find_column(df, "O*NET-SOC Code")
    out = df[[code_col, "dv_rating_beta", "human_rating_beta"]].rename(
        columns={
            code_col: "onet_soc_code",
            "dv_rating_beta": "gpts_are_gpts_score",
            "human_rating_beta": "gpts_are_gpts_human_score",
        }
    )
    out["onet_soc_code"] = out["onet_soc_code"].astype(str).str.strip()
    out["soc_code"] = out["onet_soc_code"].apply(onet_soc_to_soc)
    return out.dropna(subset=["onet_soc_code"])


def load_anthropic_1p_api_usage(path: Path | None = None) -> pd.DataFrame:
    """
    Load Anthropic Economic Index usage shares from the 1P API release,
    keyed by O*NET-SOC code.

    This is real-world *usage evidence* (share of real Claude conversations
    per occupation falling in each collaboration bucket), not a theoretical
    exposure score like AIOE/ILO/GPTs-are-GPTs -- it feeds RQ2's cross-check
    of the provisional impact_pattern classification, and is kept OUT of
    composite_exposure_score.

    Only the 1P API release is used this pass (global-only, unambiguous).
    The richer claude.ai release also exists but has per-country breakdowns
    and multiple occupation hierarchy_level values whose "global total" row
    isn't confirmed yet -- see this module's docstring.

    category_name == "soc_occupation" and hierarchy_level == 0 selects the
    detailed-occupation-level rows (matching a full O*NET-SOC code like
    "49-9021.00") rather than SOC major-group rollups (hierarchy_level == 1,
    node_external_id like "49").
    """
    if path is None:
        path = _latest_matching_file(RAW_DIR, AEI_1P_API_GLOB)
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run fetch_anthropic_economic_index.py first.")

    df = pd.read_csv(path)
    df.columns = [str(c).strip() for c in df.columns]

    detailed = df[(df["category_name"] == "soc_occupation") & (df["hierarchy_level"] == 0)]
    wide = detailed.pivot_table(
        index="node_external_id", columns="metric_id", values="value", aggfunc="mean"
    )
    keep = {
        "collaboration_bucket_automation_pct": "anthropic_1p_automation_share",
        "collaboration_bucket_augmentation_pct": "anthropic_1p_augmentation_share",
    }
    missing = [c for c in keep if c not in wide.columns]
    if missing:
        raise KeyError(
            f"Expected metric_id value(s) {missing} not found in {path}. "
            f"Available metric_id values: {sorted(detailed['metric_id'].unique())}"
        )
    wide = wide[list(keep)].rename(columns=keep).reset_index().rename(
        columns={"node_external_id": "onet_soc_code"}
    )
    wide["soc_code"] = wide["onet_soc_code"].apply(onet_soc_to_soc)
    return wide


def load_statcan_noc_exposure(path: Path = STATCAN_HTML_PATH) -> pd.DataFrame:
    """
    Parse Statistics Canada's Table A.2 (May 2021) from the saved article
    page: NOC occupation groups with Employment, AIOE, Potential
    complementarity, Complementarity-adjusted AIOE, and 3 exposure-percentage
    columns.

    APPENDIX-ONLY (see README/Data-Dictionary guardrails: one Canada
    comparison chart, not a parallel pipeline) -- deliberately NOT called
    from merge_all() or joined onto the SOC-keyed master table. NOC is used
    as-is; no crosswalk to SOC is built or needed for a single standalone
    comparison chart. Call this directly from the notebook's Canada-appendix
    section instead.

    Table A.2 bundles many demographic breakdowns (Occupation, Industry,
    Education, ...) into ONE HTML <table> with sub-header rows between
    sections (see fetch_statcan_canada.py's docstring) -- this isolates only
    the rows between the "Occupation" and "Industry" sub-headers.
    """
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run fetch_statcan_canada.py first.")

    tables = pd.read_html(path)
    target = None
    for t in tables:
        first_col = t.iloc[:, 0].astype(str)
        if (first_col == "Occupation").any() and (first_col == "Industry").any():
            target = t
            break
    if target is None:
        raise ValueError(
            f"Could not find the multi-section demographic table (Table A.2) in "
            f"{path}. Open it manually and check its layout -- the page structure "
            "may have changed."
        )

    target = target.reset_index(drop=True)
    # pd.read_html gives this table a 2-row MultiIndex header (category name
    # e.g. "Employment" over a unit label e.g. "number"/"average index"/
    # "percent") -- flatten to the category name alone (the unit is
    # redundant once the column is named "Employment"/"AIOE"/etc.), and name
    # the unlabelled first column "label". Without this, assigning a plain
    # string column name like "noc_code" onto a MultiIndex-columned frame
    # silently creates a ("noc_code", "") key instead, breaking the final
    # occ[out_cols] selection below.
    if isinstance(target.columns, pd.MultiIndex):
        target.columns = [
            "label" if str(top).startswith("Unnamed") else str(top)
            for top, _ in target.columns
        ]
    else:
        target = target.rename(columns={target.columns[0]: "label"})
    label_col = "label"
    start = target.index[target[label_col].astype(str) == "Occupation"][0] + 1
    end = target.index[target[label_col].astype(str) == "Industry"][0]
    occ = target.iloc[start:end].copy()

    # NOC labels can carry several comma-separated codes (e.g. "Support
    # occupations in sales and service (66, 67)") when StatCan groups
    # multiple detailed NOC codes under one aggregated label -- \d+ alone
    # only matches single-code labels and silently drops the rest via the
    # dropna() below (12 of these 28 groups are multi-code), so capture the
    # full parenthetical content instead.
    occ["noc_code"] = occ[label_col].astype(str).str.extract(r"\(([\d,\s]+)\)")
    occ["occupation_group"] = (
        occ[label_col].astype(str).str.replace(r"\s*\([\d,\s]+\)\s*$", "", regex=True).str.strip()
    )

    numeric_cols = [c for c in occ.columns if c not in (label_col, "noc_code", "occupation_group")]
    for c in numeric_cols:
        occ[c] = pd.to_numeric(
            occ[c].astype(str).str.replace(",", "", regex=False).str.replace("%", "", regex=False),
            errors="coerce",
        )

    out_cols = ["noc_code", "occupation_group"] + numeric_cols
    return occ[out_cols].dropna(subset=["noc_code"]).reset_index(drop=True)


def _read_oews_zip(zip_path: Path, year: int) -> pd.DataFrame:
    """
    Read the one national "All Data" .xlsx inside a single oesmYYnat.zip and
    reduce it to one row per detailed (6-digit) SOC code: total employment
    for that occupation, economy-wide (all industries, all ownership types).

    The "All Data" National file bundles several things this project does
    NOT want mixed into one occupation's employment figure:
      - per-industry breakdowns (NAICS != the economy-wide total code)
      - SOC rollups above the detailed level (O_GROUP == "major"/"minor"/
        "broad"/"total" as well as "detailed") -- keeping those in would
        double count (e.g. a major-group row AND its detailed occupations
        both present under the same soc_code-shaped OCC_CODE column)

    NAICS "000000" is the standard BLS code for the cross-industry total
    row; O_GROUP is matched case-insensitively against "detailed" rather
    than assumed to be a fixed string, since this project has already found
    one BLS file (the ISCO/SOC crosswalk) with inconsistent header/label
    formatting across releases.
    """
    with zipfile.ZipFile(zip_path) as zf:
        xlsx_names = [n for n in zf.namelist() if n.lower().endswith(".xlsx")]
        if not xlsx_names:
            raise FileNotFoundError(f"No .xlsx file found inside {zip_path}.")
        with zf.open(xlsx_names[0]) as f:
            df = pd.read_excel(f)
    df.columns = [str(c).strip() for c in df.columns]

    naics_col = _find_column(df, "NAICS")
    ogroup_col = _find_column(df, "O_GROUP")
    occ_col = _find_column(df, "OCC_CODE")
    emp_col = _find_column(df, "TOT_EMP")

    naics_str = df[naics_col].astype(str).str.strip()
    cross_industry = df[naics_str.isin(["000000", "0"])]
    if cross_industry.empty:
        title_col = _find_column(df, "NAICS_TITLE")
        cross_industry = df[
            df[title_col].astype(str).str.contains("cross-industry", case=False, na=False)
        ]
    if cross_industry.empty:
        raise ValueError(
            f"Could not find the cross-industry (economy-wide) total rows in {zip_path}. "
            f"Distinct {naics_col} values seen: {sorted(naics_str.unique())[:10]}..."
        )

    detailed = cross_industry[
        cross_industry[ogroup_col].astype(str).str.strip().str.lower() == "detailed"
    ]
    if detailed.empty:
        raise ValueError(
            f"Could not find O_GROUP == 'detailed' rows in {zip_path}. Available "
            f"{ogroup_col} values: {sorted(cross_industry[ogroup_col].dropna().unique())}"
        )

    out = detailed[[occ_col, emp_col]].rename(
        columns={occ_col: "soc_code", emp_col: f"tot_emp_{year}"}
    )
    out["soc_code"] = out["soc_code"].astype(str).str.strip()
    out[f"tot_emp_{year}"] = pd.to_numeric(
        out[f"tot_emp_{year}"].astype(str).str.replace(",", "", regex=False), errors="coerce"
    )
    return out.dropna(subset=["soc_code"]).drop_duplicates(subset=["soc_code"])


def load_bls_oews_growth(zips: dict = BLS_OEWS_ZIPS) -> pd.DataFrame:
    """
    Compute employment_growth_rate (annualized, i.e. CAGR) per SOC code from
    BLS OEWS "All Data" National tables across however many years are present
    in `zips`.

    Uses whichever years are actually available rather than hard-coding
    "2023 to 2025", so this keeps working if a future year's file is added
    or one is temporarily missing -- though at least 2 years are required to
    compute any growth rate at all.

    bls.gov blocks scripted downloads (WAF-level 403, same as
    fetch_bls_crosswalks.py) -- these 3 zip files must be downloaded
    manually; see src/data_acquisition/README.md.
    """
    present = {y: p for y, p in zips.items() if p.exists()}
    if len(present) < 2:
        missing = [str(p) for y, p in zips.items() if y not in present]
        raise FileNotFoundError(
            "Need at least 2 years of BLS OEWS data to compute a growth rate; "
            f"only found {len(present)}. Missing: {missing}. Download 'All Data' "
            "National tables manually from bls.gov/oes/tables.htm (see "
            "src/data_acquisition/README.md)."
        )

    years = sorted(present)
    per_year = [_read_oews_zip(present[y], y) for y in years]
    merged = per_year[0]
    for df in per_year[1:]:
        merged = merged.merge(df, on="soc_code", how="outer")

    first_year, last_year = years[0], years[-1]
    span = last_year - first_year
    first_col, last_col = f"tot_emp_{first_year}", f"tot_emp_{last_year}"
    valid = (merged[first_col] > 0) & merged[last_col].notna()
    merged["employment_growth_rate"] = np.nan
    merged.loc[valid, "employment_growth_rate"] = (
        (merged.loc[valid, last_col] / merged.loc[valid, first_col]) ** (1 / span) - 1
    )

    emp_cols = [f"tot_emp_{y}" for y in years]
    return merged[["soc_code"] + emp_cols + ["employment_growth_rate"]]


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

    print("Loading O*NET Transferable Skills (Cross-Functional, Importance ratings) ...")
    transferable_skills = load_transferable_skills()

    print("Loading O*NET Knowledge domains (Importance ratings) ...")
    knowledge = load_knowledge_profile()

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

    print("Loading GPTs-are-GPTs exposure scores (O*NET-SOC) ...")
    gpts = load_gpts_are_gpts_scores()
    gpts_by_soc = gpts.groupby("soc_code").agg(
        gpts_are_gpts_score=("gpts_are_gpts_score", "mean"),
        gpts_are_gpts_human_score=("gpts_are_gpts_human_score", "mean"),
    ).reset_index()
    print(f"  {len(gpts_by_soc)} SOC occupations with a GPTs-are-GPTs score")

    print("Loading Anthropic Economic Index usage shares (1P API, O*NET-SOC) ...")
    anthropic = load_anthropic_1p_api_usage()
    anthropic_by_soc = anthropic.groupby("soc_code").agg(
        anthropic_1p_automation_share=("anthropic_1p_automation_share", "mean"),
        anthropic_1p_augmentation_share=("anthropic_1p_augmentation_share", "mean"),
    ).reset_index()
    print(f"  {len(anthropic_by_soc)} SOC occupations with Anthropic usage data")

    bls_oews_by_soc = None
    if sum(p.exists() for p in BLS_OEWS_ZIPS.values()) >= 2:
        print("Loading BLS OEWS employment (multi-year) and computing employment_growth_rate ...")
        bls_oews = load_bls_oews_growth()
        bls_oews_by_soc = bls_oews.groupby("soc_code").agg(
            {c: "mean" for c in bls_oews.columns if c != "soc_code"}
        ).reset_index()
        print(f"  {len(bls_oews_by_soc)} SOC occupations with a computed employment_growth_rate")
    else:
        print("Skipping BLS OEWS (fewer than 2 years of data/raw/oesm*nat.zip present) ...")

    # O*NET-SOC is finer-grained than SOC (one SOC code can map to several
    # O*NET-SOC codes). Attach job zone + skills at the O*NET-SOC level
    # first, then average up to the SOC level so every source lines up on
    # the same key AIOE uses.
    onet_detail = onet.merge(job_zones, on="onet_soc_code", how="left")
    onet_detail = onet_detail.merge(skills, on="onet_soc_code", how="left")
    onet_detail = onet_detail.merge(transferable_skills, on="onet_soc_code", how="left")
    onet_detail = onet_detail.merge(knowledge, on="onet_soc_code", how="left")

    skill_cols = [c for c in onet_detail.columns
                  if c.startswith(("skill__", "xfskill__", "knowledge__"))]
    agg = {"job_zone": "mean", **{c: "mean" for c in skill_cols}}
    onet_by_soc = onet_detail.groupby("soc_code").agg(agg).reset_index()

    # Keep one representative O*NET title per SOC code for readability.
    titles = (
        onet_detail.sort_values("onet_soc_code")
        .drop_duplicates("soc_code")[["soc_code", "onet_title"]]
    )
    onet_by_soc = onet_by_soc.merge(titles, on="soc_code", how="left")

    print("Merging AIOE + O*NET + ILO + GPTs-are-GPTs + Anthropic on soc_code ...")
    master = aioe.merge(onet_by_soc, on="soc_code", how="outer", suffixes=("_aioe", "_onet"))
    master = master.merge(ilo_by_soc, on="soc_code", how="outer")
    master = master.merge(gpts_by_soc, on="soc_code", how="outer")
    master = master.merge(anthropic_by_soc, on="soc_code", how="outer")
    if bls_oews_by_soc is not None:
        master = master.merge(bls_oews_by_soc, on="soc_code", how="outer")

    # Prefer AIOE's own title when both are present; fall back to O*NET's.
    if "occupation_title" in master.columns:
        master["occupation_title"] = master["occupation_title"].fillna(master.get("onet_title"))
    else:
        master["occupation_title"] = master.get("onet_title")
    master = master.drop(columns=[c for c in ["onet_title"] if c in master.columns])

    # Composite exposure score: mean of whichever standardized (z-scored)
    # index columns are available per row, so an occupation missing one or
    # more indices still gets a score from the other(s). gpts_are_gpts_score
    # uses dv_rating_beta (see load_gpts_are_gpts_scores()'s docstring for
    # why, not human_rating_beta) to stay consistent with AIOE/ILO as
    # automated/model-based measures. anthropic_1p_automation_share/
    # augmentation_share are deliberately excluded -- they're real usage
    # evidence, not a theoretical exposure score, and belong in RQ2's
    # cross-check instead (see this module's docstring).
    index_cols = ["aioe_score", "ilo_score", "gpts_are_gpts_score"]
    z_cols = []
    for col in index_cols:
        z_col = f"_z_{col}"
        master[z_col] = (master[col] - master[col].mean()) / master[col].std()
        z_cols.append(z_col)
    master["composite_exposure_score"] = master[z_cols].mean(axis=1, skipna=True)
    master = master.drop(columns=z_cols)

    cols_first = ["soc_code", "occupation_title", "aioe_score", "ilo_score",
                  "gpts_are_gpts_score", "gpts_are_gpts_human_score",
                  "composite_exposure_score", "impact_pattern", "job_zone",
                  "anthropic_1p_automation_share", "anthropic_1p_augmentation_share",
                  "employment_growth_rate"]
    # employment_growth_rate (and the underlying BLS OEWS zips) is optional
    # -- only present once >=2 years of data/raw/oesm*nat.zip are supplied --
    # so filter cols_first down to columns that actually exist this run.
    cols_first = [c for c in cols_first if c in master.columns]
    other_cols = [c for c in master.columns if c not in cols_first]
    master = master[cols_first + other_cols]

    return master


def save(master: pd.DataFrame) -> Path:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / "master_occupations.csv"
    master.to_csv(out_path, index=False)
    return out_path


def load_cip_soc_crosswalk(path: Path = CIP_SOC_CROSSWALK_PATH) -> pd.DataFrame:
    """
    NCES CIP (2020) -> SOC (2018) educational-program-to-occupation
    crosswalk: which college/diploma fields of study (CIP codes) typically
    lead to which occupations (SOC codes), published by the U.S. Dept. of
    Education. Source: https://nces.ed.gov/ipeds/cipcode/Files/CIP2020_SOC2018_Crosswalk.xlsx
    (download it and save it at this path if missing -- see
    src/data_acquisition/README.md).

    APPENDIX-STYLE, like load_statcan_noc_exposure() -- the relationship is
    many-to-many (one CIP code leads to several SOC codes and vice versa),
    so this is deliberately NOT merged into merge_all()'s one-row-per-
    occupation master table (that would multiply rows). Load it separately
    and look up matches by soc_code, e.g. to tag whether two occupations in
    the Reskilling page share a field of study (see save_cip_soc_crosswalk()
    below, which is what the Streamlit app actually reads at runtime).

    The workbook has several sheets (File Guide, CIP-SOC, SOC-CIP, ...);
    only "CIP-SOC" holds the actual mapping rows.
    """
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Download it from "
            "https://nces.ed.gov/ipeds/cipcode/Files/CIP2020_SOC2018_Crosswalk.xlsx "
            f"and save it at {path}."
        )
    df = pd.read_excel(path, sheet_name="CIP-SOC")
    df.columns = [str(c).strip() for c in df.columns]
    df = df.rename(columns={
        "CIP2020Code": "cip_code",
        "CIP2020Title": "cip_title",
        "SOC2018Code": "soc_code",
        "SOC2018Title": "soc_title",
    })
    df["soc_code"] = df["soc_code"].astype(str).str.strip()
    df["cip_code"] = df["cip_code"].astype(str).str.strip()
    df["cip_title"] = df["cip_title"].astype(str).str.rstrip(".").str.strip()
    df["soc_title"] = df["soc_title"].astype(str).str.rstrip(".").str.strip()
    return df[["cip_code", "cip_title", "soc_code", "soc_title"]]


def save_cip_soc_crosswalk(cip_soc: pd.DataFrame) -> Path:
    """
    Save a small processed copy of the CIP-SOC crosswalk to data/processed/
    (unlike data/raw/, data/processed/ IS committed to git -- see
    .gitignore) so the Streamlit app can read it without needing
    data/raw/ to exist in the deployed environment (Streamlit Community
    Cloud deploys straight from the GitHub repo, which never has
    data/raw/'s contents -- see app/utils.py's module docstring).
    """
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / "cip_soc_crosswalk.csv"
    cip_soc.to_csv(out_path, index=False)
    return out_path


def shares_field_of_study(soc_a: str, soc_b: str, cip_soc_df: pd.DataFrame):
    """
    True if soc_a and soc_b share at least one CIP (field-of-study) code in
    the NCES crosswalk -- i.e. at least one academic program the crosswalk
    lists as typically leading to BOTH occupations. False if both
    occupations appear in the crosswalk but share no CIP code. None if
    either occupation isn't in the crosswalk at all (no data either way --
    deliberately distinct from False, so the caller doesn't claim "requires
    a different field" when it simply has no information).
    """
    cips_a = set(cip_soc_df.loc[cip_soc_df["soc_code"] == soc_a, "cip_code"])
    cips_b = set(cip_soc_df.loc[cip_soc_df["soc_code"] == soc_b, "cip_code"])
    if not cips_a or not cips_b:
        return None
    return bool(cips_a & cips_b)


def nearest_lower_exposure_alternatives(source_soc, df, skill_cols, n=5, min_gap=0.0):
    """
    For a given high-exposure occupation (by soc_code), find the n occupations
    whose skill EMPHASIS pattern is most aligned with it (cosine similarity
    over per-skill z-scored O*NET Basic Skills importance ratings) among
    those with a MEANINGFULLY lower composite_exposure_score -- candidates
    for reskilling.

    IMPORTANT -- z-scored, not raw, skill vectors (fixed after a real-data
    bug report): the first version of this function ran cosine similarity
    directly on the raw 1-5 importance ratings and produced nonsense --
    e.g. Data Scientists came back 99.6-99.9% "similar" to Stonemasons,
    Electricians, Plumbers, and Machinists. Root cause, confirmed on the
    real dataset: these 10 Basic Skills columns share a strong common
    component (almost every occupation rates baseline literacy/
    communication skills like Active Listening and Reading Comprehension
    moderately-to-highly important), and raw cosine similarity is dominated
    by that shared direction rather than by what actually differs between
    occupations (Mathematics, Science, Learning Strategies, etc.). Z-scoring
    each skill column across the dataset first removes that shared
    baseline: re-run on the same real Data-Scientists-vs-trades example,
    z-scored cosine similarity dropped from ~0.997 to roughly -0.46..+0.30
    (Electricians -- the most technical of that group -- came out highest,
    which matches intuition; the others came out near zero or negative,
    i.e. no meaningful alignment). This makes the resulting `skill_similarity`
    value a signed score roughly in [-1, 1], not a 0-100% "match" -- see the
    Streamlit app's in-page glossary for the user-facing explanation.

    Moved here (out of the notebook's Professional Layer cell, where it was
    originally prototyped) so the Phase 2 Streamlit app can import the exact
    same logic instead of re-implementing or copy-pasting it. The notebook
    now imports this function rather than defining its own copy -- see
    notebooks/01_exploratory_analysis.ipynb, Professional layer section.

    Parameters
    ----------
    source_soc : str
        SOC code of the high-exposure occupation to find alternatives for.
    df : pd.DataFrame
        The master occupation table (as returned by merge_all() / loaded
        from data/processed/master_occupations.csv), must contain
        soc_code, occupation_title, composite_exposure_score, and every
        column in skill_cols. Z-score means/stds are computed across every
        row of this df that has a value for a given skill column (pandas'
        default NaN-skipping mean/std), so results are stable regardless of
        which single source_soc or candidate subset is being queried.
    skill_cols : list[str]
        The skill__* column names to compare occupations on (typically
        `[c for c in df.columns if c.startswith("skill__")]`).
    n : int
        Number of alternatives to return.
    min_gap : float
        Minimum required drop in composite_exposure_score for a candidate
        to even be considered (0.0 = any strictly lower score qualifies).

    Returns
    -------
    pd.DataFrame with columns: soc_code, occupation_title,
    composite_exposure_score, skill_similarity (z-scored cosine similarity,
    roughly -1 to 1; higher = this occupation's skill emphasis pattern
    aligns more with the source occupation's, relative to the dataset as a
    whole), and one gap__<skill> column per skill in skill_cols (candidate's
    RAW 1-5 importance rating minus the source occupation's RAW rating on
    that skill -- positive means the candidate occupation rates that skill
    MORE important than the source occupation; this one is intentionally
    NOT z-scored, so it stays interpretable on the original 1-5 scale).
    Empty DataFrame (same columns, zero rows) if source_soc isn't found or
    no qualifying candidates exist.
    """
    if source_soc not in df["soc_code"].values:
        raise ValueError(f"soc_code {source_soc} not found")

    df = df.copy()
    skill_means = df[skill_cols].mean()
    skill_stds = df[skill_cols].std()
    z_cols = [f"_z_{c}" for c in skill_cols]
    for col, z_col in zip(skill_cols, z_cols):
        df[z_col] = (df[col] - skill_means[col]) / skill_stds[col]

    source_row = df.loc[df["soc_code"] == source_soc].iloc[0]
    source_vec = source_row[z_cols].to_numpy(dtype=float)
    source_score = source_row["composite_exposure_score"]

    candidates = df.dropna(subset=z_cols + ["composite_exposure_score"]).copy()
    candidates = candidates[candidates["soc_code"] != source_soc]
    candidates = candidates[candidates["composite_exposure_score"] < source_score - min_gap]
    if candidates.empty:
        return candidates.drop(columns=z_cols, errors="ignore")

    cand_matrix = candidates[z_cols].to_numpy(dtype=float)
    sims = cosine_similarity(source_vec.reshape(1, -1), cand_matrix)[0]
    candidates = candidates.assign(skill_similarity=sims)
    top = candidates.sort_values("skill_similarity", ascending=False).head(n).copy()

    gap_cols = []
    for col in skill_cols:
        gap_col = f"gap__{col}"
        top[gap_col] = top[col] - source_row[col]
        gap_cols.append(gap_col)

    out_cols = ["soc_code", "occupation_title", "composite_exposure_score", "skill_similarity"] + gap_cols
    return top[out_cols]


if __name__ == "__main__":
    master = merge_all()
    out_path = save(master)
    print(f"\nDone. {len(master)} occupations in the master table.")
    print(f"Saved: {out_path}")
    print(f"Columns: {list(master.columns)}")

    try:
        cip_soc = load_cip_soc_crosswalk()
        cip_soc_path = save_cip_soc_crosswalk(cip_soc)
        print(f"\nSaved CIP-SOC field-of-study crosswalk: {cip_soc_path} ({len(cip_soc)} rows)")
    except FileNotFoundError as e:
        print(f"\nSkipping CIP-SOC crosswalk save (Reskilling page's field-of-study tag will be "
              f"unavailable until this is fixed): {e}")
