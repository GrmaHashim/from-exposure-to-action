"""
Fetch the "GPTs are GPTs" LLM occupational-exposure dataset.

Source:   Eloundou, T., Manning, S., Mishkin, P., & Rock, D. (2023/2024). GPTs
          are GPTs: An early look at the labor market impact potential of
          large language models. arXiv:2303.10130. Published version: Science
          384(6702), 1306-1308 (2024). https://doi.org/10.1126/science.adj0998
Repo:     https://github.com/openai/GPTs-are-GPTs (the authors' own repo,
          under the openai GitHub org -- Eloundou, Mishkin, and Manning are
          OpenAI-affiliated). The Science journal page for the published
          version is paywalled and its own "supplementary materials" are not
          the machine-readable data; this repo is the actual replication data.
License:  MIT License (OpenAI, 2024) -- see the repo's LICENSE file. No
          citation is legally required under MIT, but cite the paper above
          whenever this data is used, per standard academic practice.

The repo's data/ directory holds many intermediate files; the one used in
this project is occ_level.csv, the occupation-level exposure table. Per the
repo's own README:

    "Occupation level codes are in occ_level.csv!
     - dv_rating is the GPT-4 rating and human is from the annotators
     - _alpha=E1, _beta = E1+.5*E2, _gamma=E1+E2"

It is keyed by O*NET-SOC Code (column "O*NET-SOC Code", e.g. "11-1011.00"),
one row per occupation (923 rows, no duplicate codes), with six exposure
score columns: dv_rating_alpha/beta/gamma (GPT-4-generated labels) and
human_rating_alpha/beta/gamma (human-annotator labels), where alpha/beta/gamma
correspond to the paper's E1 / E1+0.5*E2 / E1+E2 exposure definitions.

CONFIRMED against the paper's own text (arXiv:2303.10130 abstract/body, not
inferred): beta IS the paper's headline measure -- "Based on the β values,
we estimate that 80% of workers belong to an occupation with at least 10%
of its tasks exposed to LLMs, while 19% of workers are in an occupation
where over half of its tasks are labeled as exposed." BUT that oft-cited
80%/19% figure is specifically **human_rating_beta**, not dv_rating_beta --
the paper states human annotations are its primary result, with GPT-4
("dv") used only as a validation/robustness check against the human
labels (the two are reported as highly correlated). If matching the
paper's headline number exactly matters downstream, use
human_rating_beta; dv_rating_beta is a defensible, well-validated
GPT-4-only alternative if a fully automated/scalable measure is preferred
instead, consistent with this project's AIOE/ILO indices.

Usage:
    python fetch_gpts_are_gpts.py

Requires internet access to raw.githubusercontent.com -- run this from your
own machine, Colab, or inside the Kaggle notebook (with internet enabled in
notebook settings). It will not reach the source from a network-restricted
sandbox.
"""
import sys
from pathlib import Path

import requests

RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"
OUT_FILE = RAW_DIR / "GPTs_are_GPTs_occ_level.csv"

# Try both common default-branch names; GitHub repos vary between the two.
CANDIDATE_URLS = [
    "https://raw.githubusercontent.com/openai/GPTs-are-GPTs/main/data/occ_level.csv",
    "https://raw.githubusercontent.com/openai/GPTs-are-GPTs/master/data/occ_level.csv",
]

# Column expected in a genuine occ_level.csv header, used to sanity-check the
# download isn't an HTML error/login page (GitHub raw 404s sometimes still
# return HTTP 200 with an HTML body instead of the CSV).
EXPECTED_HEADER_MARKER = "O*NET-SOC Code"


def _looks_like_csv(content: bytes) -> bool:
    head = content[:2000].decode("utf-8", errors="ignore")
    if "<html" in head.lower() or "<!doctype" in head.lower():
        return False
    return EXPECTED_HEADER_MARKER in head


def fetch() -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    last_error = None
    for url in CANDIDATE_URLS:
        try:
            resp = requests.get(url, timeout=60)
            if resp.status_code == 200 and _looks_like_csv(resp.content):
                OUT_FILE.write_bytes(resp.content)
                print(f"Saved: {OUT_FILE}  ({len(resp.content):,} bytes)  from {url}")
                return OUT_FILE
            last_error = f"HTTP {resp.status_code} from {url}"
        except requests.RequestException as exc:
            last_error = f"{exc} ({url})"
    raise RuntimeError(
        "Could not download occ_level.csv from either branch. "
        f"Last error: {last_error}. Check https://github.com/openai/GPTs-are-GPTs "
        "in case the filename or branch changed."
    )


def preview(path: Path) -> None:
    import pandas as pd

    df = pd.read_csv(path)
    print(f"\nColumns: {df.columns.tolist()}")
    print(f"Rows: {len(df)}")
    print(df.head())


if __name__ == "__main__":
    out = fetch()
    try:
        preview(out)
    except Exception as exc:  # pragma: no cover
        print(f"Downloaded the file but could not preview it automatically: {exc}", file=sys.stderr)
