"""
Fetch the ILO "Generative AI and Jobs" occupational exposure dataset (2025 update).

Source:   Gmyrek, P., Berg, J., & Bescond, D. (2025). Generative AI and Jobs:
          A Refined Global Index of Occupational Exposure. ILO Working Paper 140.
          Geneva: International Labour Organization.
Paper:    https://www.ilo.org/publications/generative-ai-and-jobs-refined-global-index-occupational-exposure
Repo:     https://github.com/pgmyrek/2025_GenAI_scores_ISCO08 (lead author's own
          data repo, linked from the working paper's own interactive-data note
          under Figure 16, and cited by the World Bank Reproducible Research
          Repository as the source for this index's replication data)
License:  No explicit license stated in the repo; cite ILO Working Paper 140
          (above) whenever this data is used, per standard ILO working-paper
          citation practice. Keep this citation in any notebook, report, or
          app that uses this data.

Two files are pulled:
    - Final_Scores_ISCO08_Gmyrek_et_al_2025.xlsx  -- occupation-level exposure
      scores by ISCO-08 code (feeds the composite_exposure_score and RQ1).
    - 4digits_with_tasks.xlsx                     -- task-level exposure scores
      underneath each ISCO-08 occupation, ~30k tasks (feeds RQ2's impact-pattern
      classification via per-task score variance, and RQ3).

Usage:
    python fetch_ilo_genai.py

Requires internet access to raw.githubusercontent.com -- run this from your
own machine, Colab, or inside the Kaggle notebook (with internet enabled in
notebook settings). It will not reach the source from a network-restricted
sandbox.
"""
import sys
from pathlib import Path

import requests

RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"

# (output filename, candidate URLs to try in order -- default branch first,
# a fallback branch name second, in case the repo's default branch changes)
FILES = {
    "occupation_level": (
        "ILO_Final_Scores_ISCO08_Gmyrek_et_al_2025.xlsx",
        [
            "https://raw.githubusercontent.com/pgmyrek/2025_GenAI_scores_ISCO08/main/Final_Scores_ISCO08_Gmyrek_et_al_2025.xlsx",
            "https://raw.githubusercontent.com/pgmyrek/2025_GenAI_scores_ISCO08/master/Final_Scores_ISCO08_Gmyrek_et_al_2025.xlsx",
        ],
    ),
    "task_level": (
        "ILO_4digits_with_tasks.xlsx",
        [
            "https://raw.githubusercontent.com/pgmyrek/2025_GenAI_scores_ISCO08/main/4digits_with_tasks.xlsx",
            "https://raw.githubusercontent.com/pgmyrek/2025_GenAI_scores_ISCO08/master/4digits_with_tasks.xlsx",
        ],
    ),
}


def fetch_one(out_name: str, candidate_urls: list[str]) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RAW_DIR / out_name
    last_error = None
    for url in candidate_urls:
        try:
            resp = requests.get(url, timeout=60)
            if resp.status_code == 200 and resp.content[:2] == b"PK":  # xlsx = zip magic bytes
                out_path.write_bytes(resp.content)
                print(f"Saved: {out_path}  ({len(resp.content):,} bytes)  from {url}")
                return out_path
            last_error = f"HTTP {resp.status_code} from {url}"
        except requests.RequestException as exc:
            last_error = f"{exc} ({url})"
    raise RuntimeError(
        f"Could not download {out_name} from any candidate URL. "
        f"Last error: {last_error}. Check "
        "https://github.com/pgmyrek/2025_GenAI_scores_ISCO08 in case a filename "
        "or branch changed."
    )


def fetch() -> list[Path]:
    saved = []
    for key, (out_name, urls) in FILES.items():
        print(f"Downloading ILO {key} data ...")
        saved.append(fetch_one(out_name, urls))
    return saved


def list_sheets(path: Path) -> None:
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True)
    print(f"Sheets in {path.name}:")
    for name in wb.sheetnames:
        print(f"  - {name}")


if __name__ == "__main__":
    paths = fetch()
    for path in paths:
        try:
            list_sheets(path)
        except Exception as exc:  # pragma: no cover
            print(f"Downloaded {path.name} but could not list sheets automatically: {exc}", file=sys.stderr)
    print(
        "\nDone. Occupation-level scores are keyed by ISCO-08 code; task-level "
        "scores break each occupation down by individual task. See "
        "src/crosswalks/ for mapping ISCO-08 to SOC / O*NET-SOC once a "
        "reference crosswalk table is added."
    )
