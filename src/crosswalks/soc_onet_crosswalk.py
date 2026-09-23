"""
Occupation-classification crosswalk helpers.

See docs/From_Exposure_to_Action_Data_Dictionary.xlsx -> "Classification
Crosswalks" tab for the full picture of which system each dataset uses:

    US SOC 2018   <- BLS OEWS, AIOE
    O*NET-SOC     <- O*NET (near 1:1 with SOC; O*NET splits some SOC codes further)
    ISCO-08       <- ILO, OECD (international standard)
    Canada NOC    <- Statistics Canada (appendix only)

Guardrail reminder: keep each source's original occupation code as its own
column in the master dataset rather than collapsing to one unified code --
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

ISCO-08 <-> SOC 2018 (for ILO, OECD)
-------------------------------------
There is no single official ISCO-08 <-> SOC 2018 crosswalk. It's built here
by chaining two official BLS crosswalks (see fetch_bls_crosswalks.py):

    ISCO-08 <-> SOC 2010   (BLS's own crosswalk)
    SOC 2010 -> SOC 2018   (BLS's own revision crosswalk)

build_isco_to_soc2018() does the chaining and returns a lookup table;
isco_to_soc() looks up a single ISCO-08 code in it. This crosswalk is
many-to-many (one ISCO-08 unit group can match several SOC codes and vice
versa) -- callers should expect a list, and aggregate (e.g. mean) across
matches rather than assume a single answer.

Canada NOC
----------
Needed only for the appendix-only Canada comparison chart (see README
guardrails -- not a parallel pipeline). noc_to_onet_soc() is a placeholder
until a NOC <-> SOC/O*NET-SOC reference file (e.g. from the Labour Market
Information Council / The Dais) is added to data/raw/.
"""
import re
from pathlib import Path

import pandas as pd

ONET_VERSION = "31_0"
RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"
OCCUPATION_DATA_PATH = RAW_DIR / f"onet_db_{ONET_VERSION}" / "Occupation Data.xlsx"

ISCO_SOC2010_PATH = RAW_DIR / "ISCO_SOC_2010_Crosswalk.xls"
SOC2010_SOC2018_PATH = RAW_DIR / "SOC_2010_to_2018_Crosswalk.xlsx"

SOC_CODE_PATTERN = re.compile(r"^\d{2}-\d{4}")
# Matches plain integer codes ("2512") as well as the float-artifact form
# ("2512.0") pandas produces when a numeric column contains any NaN --
# _clean_code_series() below strips that artifact once the column is chosen.
ISCO_CODE_PATTERN = re.compile(r"^\d{1,4}(\.0)?$")


# ---------------------------------------------------------------------------
# SOC <-> O*NET-SOC
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# ISCO-08 <-> SOC 2018 (chained through SOC 2010)
# ---------------------------------------------------------------------------

def load_isco_soc2010_crosswalk(path: Path = ISCO_SOC2010_PATH) -> pd.DataFrame:
    """
    Load BLS's ISCO-08 <-> SOC 2010 crosswalk.

    Returns a DataFrame with columns ['isco_code', 'soc_2010']. Column
    detection is value-pattern-based (not just header-name-based) because
    the exact BLS header wording isn't guaranteed stable across file
    revisions, and a file can have both a "...Code" and a "...Title" column
    that both contain the same keyword (e.g. "SOC").
    """
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run fetch_bls_crosswalks.py first.")

    # Like AIOE's Appendix A, BLS crosswalk files carry a title/attribution
    # block (agency name, revision date, a contact-email note) above the
    # real header row -- find it rather than assuming row 0.
    header_row = _find_header_row(path, required_keywords=["ISCO", "SOC"])
    if header_row is None:
        raise ValueError(
            f"Could not find a header row with 'ISCO' and 'SOC' columns in the first "
            f"20 rows of {path}. Open it manually and check its layout."
        )

    df = pd.read_excel(path, header=header_row)
    df.columns = [str(c).strip() for c in df.columns]

    isco_col = _find_code_column(df, "ISCO", ISCO_CODE_PATTERN)
    soc_col = _find_code_column(df, "SOC", SOC_CODE_PATTERN)

    out = df[[isco_col, soc_col]].rename(columns={isco_col: "isco_code", soc_col: "soc_2010"})
    out["isco_code"] = _clean_isco_code_series(out["isco_code"])
    out["soc_2010"] = out["soc_2010"].astype(str).str.strip()
    return out.dropna(subset=["isco_code", "soc_2010"])


def load_soc2010_to_soc2018_crosswalk(path: Path = SOC2010_SOC2018_PATH) -> pd.DataFrame:
    """
    Load BLS's SOC 2010 -> SOC 2018 revision crosswalk.

    Returns a DataFrame with columns ['soc_2010', 'soc_2018'].
    """
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run fetch_bls_crosswalks.py first.")

    header_row = _find_header_row(path, required_keywords=["2010", "2018"])
    if header_row is None:
        raise ValueError(
            f"Could not find a header row with '2010' and '2018' columns in the first "
            f"20 rows of {path}. Open it manually and check its layout."
        )

    df = pd.read_excel(path, header=header_row)
    df.columns = [str(c).strip() for c in df.columns]

    soc2010_col = _find_code_column_by_year(df, 2010)
    soc2018_col = _find_code_column_by_year(df, 2018)

    out = df[[soc2010_col, soc2018_col]].rename(
        columns={soc2010_col: "soc_2010", soc2018_col: "soc_2018"}
    )
    out["soc_2010"] = out["soc_2010"].astype(str).str.strip()
    out["soc_2018"] = out["soc_2018"].astype(str).str.strip()
    return out.dropna(subset=["soc_2010", "soc_2018"])


def build_isco_to_soc2018() -> pd.DataFrame:
    """
    Chain ISCO-08 <-> SOC 2010 and SOC 2010 -> SOC 2018 into one lookup
    table: columns ['isco_code', 'soc_2010', 'soc_2018']. Many-to-many by
    nature (an ISCO-08 unit group can match multiple SOC codes and vice
    versa) -- aggregate (e.g. mean) across matches downstream rather than
    assume a single answer.

    A SOC 2010 code with no SOC 2018 match (rare -- most codes carried
    over unchanged between revisions) falls back to keeping its SOC 2010
    code as soc_2018, on the assumption it didn't change, and is counted
    so you can sanity-check how many fell into that fallback.
    """
    isco_soc2010 = load_isco_soc2010_crosswalk()
    soc2010_soc2018 = load_soc2010_to_soc2018_crosswalk()

    merged = isco_soc2010.merge(soc2010_soc2018, on="soc_2010", how="left")
    unmatched = merged["soc_2018"].isna().sum()
    if unmatched:
        print(
            f"Note: {unmatched} of {len(merged)} ISCO<->SOC2010 rows had no SOC2010->SOC2018 "
            "match; assuming those SOC 2010 codes carried over unchanged to SOC 2018."
        )
        merged["soc_2018"] = merged["soc_2018"].fillna(merged["soc_2010"])

    return merged[["isco_code", "soc_2010", "soc_2018"]].drop_duplicates()


def isco_to_soc(isco_code: str, crosswalk_df: pd.DataFrame | None = None) -> list[str]:
    """
    ISCO-08 unit group code -> list of matching SOC 2018 codes (usually one,
    sometimes several -- see build_isco_to_soc2018()'s docstring).

    crosswalk_df defaults to loading build_isco_to_soc2018() if not passed
    in (pass it explicitly when calling this in a loop, to avoid rebuilding
    the crosswalk on every call).
    """
    if crosswalk_df is None:
        crosswalk_df = build_isco_to_soc2018()
    matches = crosswalk_df[crosswalk_df["isco_code"] == _clean_isco_code(isco_code)]
    return matches["soc_2018"].dropna().unique().tolist()


# ---------------------------------------------------------------------------
# Canada NOC (appendix only -- placeholder until a reference file is added)
# ---------------------------------------------------------------------------

def noc_to_onet_soc(noc_code: str, crosswalk_df: pd.DataFrame | None = None) -> str | None:
    """
    Canada NOC -> O*NET-SOC lookup, for the appendix-only Canada comparison
    chart. Returns None until a reference crosswalk_df (columns: 'NOC',
    'O*NET-SOC Code') is supplied -- see the module docstring.
    """
    if crosswalk_df is None:
        return None
    code_col = _find_column(crosswalk_df, "NOC")
    onet_col = _find_column(crosswalk_df, "O*NET-SOC")
    match = crosswalk_df[crosswalk_df[code_col] == noc_code]
    if match.empty:
        return None
    return match.iloc[0][onet_col]


# ---------------------------------------------------------------------------
# Column-detection helpers
# ---------------------------------------------------------------------------

def _find_header_row(
    path: Path,
    required_keywords: list[str],
    sheet_name=0,
    max_header_cell_len: int = 30,
    max_rows_to_scan: int = 20,
) -> int | None:
    """
    BLS crosswalk files (like AIOE's Appendix A) carry a title/attribution
    block -- agency name, revision date, a "questions? email us" note --
    above the real header row, so header=0 would misread that block as
    column names. This scans the first `max_rows_to_scan` rows for the
    first one where EVERY keyword in `required_keywords` appears in some
    SHORT cell (<= max_header_cell_len chars) -- short enough that a long
    title/attribution sentence can't accidentally match even if it happens
    to contain the keyword as a substring (e.g. "...soc@bls.gov").
    """
    raw = pd.read_excel(path, sheet_name=sheet_name, header=None, nrows=max_rows_to_scan)
    for i in range(len(raw)):
        cells = raw.iloc[i].fillna("").astype(str)
        if all(
            any(kw.lower() in v.lower() and len(v) <= max_header_cell_len for v in cells)
            for kw in required_keywords
        ):
            return i
    return None


def _clean_code_series(series: pd.Series) -> pd.Series:
    """
    Stringify a code column and strip the ".0" float artifact pandas adds
    when a numeric column contains any NaN (e.g. 2512 -> "2512.0" instead
    of "2512"). Leaves already-string codes (like SOC's "15-1252") alone.
    """
    cleaned = series.astype(str).str.strip()
    return cleaned.str.replace(r"^(\d+)\.0$", r"\1", regex=True)


def _clean_code(value: str) -> str:
    """Same cleanup as _clean_code_series(), for a single lookup value."""
    value = str(value).strip()
    return re.sub(r"^(\d+)\.0$", r"\1", value)


def _clean_isco_code_series(series: pd.Series) -> pd.Series:
    """
    Same float-artifact cleanup as _clean_code_series(), plus zero-padding
    to 4 digits. ISCO-08's "Armed forces occupations" major group uses
    codes like "0110" -- if Excel stored that cell as a formatted number
    rather than text, reading it back gives 110 (leading zero lost), so
    this re-pads any purely-numeric result back to the canonical 4-digit
    form. A no-op for codes already 4 digits (e.g. "2512" -> "2512").
    """
    cleaned = _clean_code_series(series)
    is_numeric = cleaned.str.match(r"^\d+$")
    cleaned = cleaned.where(~is_numeric, cleaned.str.zfill(4))
    return cleaned


def _clean_isco_code(value) -> str:
    """Same cleanup as _clean_isco_code_series(), for a single lookup value."""
    value = _clean_code(value)
    return value.zfill(4) if value.isdigit() else value


def _find_column(df: pd.DataFrame, contains: str) -> str:
    """Case-insensitive helper: find the first column whose name contains `contains`."""
    for col in df.columns:
        if contains.lower() in str(col).lower():
            return col
    raise KeyError(f"No column containing '{contains}' found in columns: {list(df.columns)}")


def _find_code_column(df: pd.DataFrame, keyword: str, pattern: re.Pattern) -> str:
    """
    Find the column most likely to hold a CODE (not a title/description):
    among all columns whose header contains `keyword`, pick the one whose
    values best match `pattern`. Falls back to the first keyword match if
    none of them match the pattern well (e.g. codes stored with unexpected
    formatting) so this never silently returns nothing.
    """
    candidates = [c for c in df.columns if keyword.lower() in str(c).lower()]
    if not candidates:
        raise KeyError(f"No column containing '{keyword}' found in columns: {list(df.columns)}")
    if len(candidates) == 1:
        return candidates[0]

    best_col, best_ratio = candidates[0], -1.0
    for col in candidates:
        values = df[col].dropna().astype(str).str.strip()
        if len(values) == 0:
            continue
        ratio = values.str.match(pattern).mean()
        if ratio > best_ratio:
            best_ratio = ratio
            best_col = col
    return best_col


def _find_code_column_by_year(df: pd.DataFrame, year: int) -> str:
    """Among columns mentioning `year` (e.g. 2010 or 2018), pick the one that looks like a code."""
    candidates = [c for c in df.columns if str(year) in str(c)]
    if not candidates:
        raise KeyError(f"No column mentioning '{year}' found in columns: {list(df.columns)}")
    if len(candidates) == 1:
        return candidates[0]

    best_col, best_ratio = candidates[0], -1.0
    for col in candidates:
        values = df[col].dropna().astype(str).str.strip()
        if len(values) == 0:
            continue
        ratio = values.str.match(SOC_CODE_PATTERN).mean()
        if ratio > best_ratio:
            best_ratio = ratio
            best_col = col
    return best_col


if __name__ == "__main__":
    occ = load_onet_occupation_data()
    print(f"Loaded {len(occ)} O*NET-SOC occupations from {OCCUPATION_DATA_PATH.name}")
    sample_onet_code = occ.iloc[0][_find_column(occ, "O*NET-SOC Code")]
    print(f"Example: {sample_onet_code} -> SOC {onet_soc_to_soc(sample_onet_code)}")

    print("\nBuilding ISCO-08 -> SOC 2018 crosswalk ...")
    isco_crosswalk = build_isco_to_soc2018()
    print(f"Loaded {len(isco_crosswalk)} ISCO-08 <-> SOC rows")
    sample_isco_code = isco_crosswalk.iloc[0]["isco_code"]
    print(f"Example: ISCO {sample_isco_code} -> SOC {isco_to_soc(sample_isco_code, isco_crosswalk)}")
