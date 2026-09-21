"""
Occupation-classification crosswalk helpers.

See docs/From_Exposure_to_Action_Data_Dictionary.xlsx -> "Classification
Crosswalks" tab for the full picture of which system each dataset uses:

    US SOC 2018   <- BLS OEWS, AIOE
    O*NET-SOC     <- O*NET (near 1:1 with SOC; O*NET splits some SOC codes further)
    ISCO-08       <- ILO, OECD (international standard)
    Canada NOC    <- Statistics Canada (appendix only)

Guardrail reminder: keep each source's original occupation code as its own
column in the master dataset rather than collapsing to one unified code —
no crosswalk here is perfectly 1:1, and this preserves traceability.

SOC <-> O*NET-SOC
-----------------
No external reference file is needed for this one. O*NET-SOC codes are built
by extending the 6-digit SOC 2018 detailed occupation code with a two-digit
suffix after a period, e.g.:

    SOC 15-1252            (Software Developers)
    O*NET-SOC 15-1252.00   (O*NET does not split this SOC code further)

    SOC 29-1141            (Registered Nurses)
    O*NET-SOC 29-1141.00, 29-1141.01  (O*NET splits this SOC code into
                                        sub-specialties)

So onet_soc_to_soc() is a pure string operation, and soc_to_onet_soc() is a
lookup against O*NET's own "Occupation Data.xlsx" (which is what
load_onet_occupation_data() below reads). Both directions are exact.

ISCO-08 and Canada NOC
-----------------------
These are NOT 1:1 derivable from SOC by a string rule — they need an actual
reference crosswalk table. Two practical options once you're ready to bring
ILO/OECD (ISCO-08) or Statistics Canada (NOC) into the join:

    - ISCO-08 <-> SOC: use the US BLS's own published SOC-to-ISCO-08
      crosswalk (https://www.bls.gov/soc/) or the OECD's correspondence
      tables, loaded as a small reference CSV in data/raw/.
    - NOC <-> SOC/O*NET-SOC: use a published NOC-SOC crosswalk (e.g. from
      the Labour Market Information Council / The Dais), also loaded as a
      reference CSV.

Both functions below accept that reference table as a DataFrame argument
rather than hard-coding a URL, since neither crosswalk is bundled with this
repo yet (appendix-only scope — see README guardrails). Until a reference
table is supplied, they return None for every input rather than raising, so
the rest of the pipeline can run without ISCO/NOC support.
"""
from pathlib import Path

import pandas as pd

ONET_VERSION = "31_0"
RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"
OCCUPATION_DATA_PATH = RAW_DIR / f"onet_db_{ONET_VERSION}" / "Occupation Data.xlsx"


def load_onet_occupation_data(path: Path = OCCUPATION_DATA_PATH) -> pd.DataFrame:
    """Load O*NET's Occupation Data.xlsx (O*NET-SOC Code, Title, Description)."""
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run fetch_onet.py first to download and extract it."
        )
    df = pd.read_excel(path)
    df.columns = [c.strip() for c in df.columns]
    return df


def onet_soc_to_soc(onet_soc_code: str) -> str:
    """
    '15-1252.00' -> '15-1252'

    Strips the O*NET-specific suffix after the period, returning the
    underlying 6-digit SOC 2018 detailed occupation code.
    """
    return onet_soc_code.strip().split(".")[0]


def soc_to_onet_soc(soc_code: str, occupation_df: pd.DataFrame | None = None) -> list[str]:
    """
    '15-1252' -> ['15-1252.00'] (or multiple codes if O*NET split this SOC
    code into sub-specialties, e.g. '29-1141' -> ['29-1141.00', '29-1141.01', ...])

    occupation_df defaults to loading Occupation Data.xlsx if not passed in.
    """
    if occupation_df is None:
        occupation_df = load_onet_occupation_data()
    code_col = _find_column(occupation_df, "O*NET-SOC Code")
    prefix = soc_code.strip()
    matches = occupation_df[occupation_df[code_col].str.startswith(prefix + ".")]
    return matches[code_col].tolist()


def isco_to_soc(isco_code: str, crosswalk_df: pd.DataFrame | None = None) -> str | None:
    """
    Approximate ISCO-08 -> SOC 2018 lookup. Returns None until a reference
    crosswalk_df (columns: 'ISCO-08', 'SOC') is supplied — see the module
    docstring for where to source one. Not needed for Phase 1's US-anchored
    analysis; only relevant if ILO/OECD data is later joined at the
    individual-occupation level rather than via its own SOC-coded exports.
    """
    if crosswalk_df is None:
        return None
    code_col = _find_column(crosswalk_df, "ISCO")
    soc_col = _find_column(crosswalk_df, "SOC")
    match = crosswalk_df[crosswalk_df[code_col] == isco_code]
    if match.empty:
        return None
    return match.iloc[0][soc_col]


def noc_to_onet_soc(noc_code: str, crosswalk_df: pd.DataFrame | None = None) -> str | None:
    """
    Canada NOC -> O*NET-SOC lookup, for the appendix-only Canada comparison
    chart. Returns None until a reference crosswalk_df (columns: 'NOC',
    'O*NET-SOC Code') is supplied — see the module docstring.
    """
    if crosswalk_df is None:
        return None
    code_col = _find_column(crosswalk_df, "NOC")
    onet_col = _find_column(crosswalk_df, "O*NET-SOC")
    match = crosswalk_df[crosswalk_df[code_col] == noc_code]
    if match.empty:
        return None
    return match.iloc[0][onet_col]


def _find_column(df: pd.DataFrame, contains: str) -> str:
    """Case-insensitive helper: find the first column whose name contains `contains`."""
    for col in df.columns:
        if contains.lower() in str(col).lower():
            return col
    raise KeyError(f"No column containing '{contains}' found in columns: {list(df.columns)}")


if __name__ == "__main__":
    occ = load_onet_occupation_data()
    print(f"Loaded {len(occ)} O*NET-SOC occupations from {OCCUPATION_DATA_PATH.name}")
    sample_onet_code = occ.iloc[0][_find_column(occ, "O*NET-SOC Code")]
    print(f"Example: {sample_onet_code} -> SOC {onet_soc_to_soc(sample_onet_code)}")
