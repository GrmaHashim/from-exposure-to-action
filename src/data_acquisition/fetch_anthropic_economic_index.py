"""
Fetch the Anthropic Economic Index (AEI) -- Anthropic's own published dataset
of real Claude usage patterns by occupation, including a human-AI
collaboration split (automation vs. augmentation) per occupation.

This is real-world *usage evidence*, not a theoretical exposure score like
AIOE or the ILO GenAI index. Keep it as its own variable in the master
table -- do not merge it into composite_exposure_score.

Source:   Massenkoff, M., Lyubich, E., Sacher, S., Hitzig, Z., Zhang, S.,
          Heller, R., & McCrory, P. (2026). Anthropic Economic Index report:
          Cadences. Anthropic. https://www.anthropic.com/research/economic-index-june-2026-report
Release:  6th release, dated 2026-06-26 (covers usage data for April and May
          2026) -- the most recent occupation-level release as of 2026-09-23.
          Confirmed via the dataset repo's own README, which lists this as
          the newest of six releases running Feb 2025 -> Jun 2026.
Repo:     https://huggingface.co/datasets/Anthropic/EconomicIndex
          (folder: release_2026_06_26/data/)
License:  Data released under CC-BY; code released under MIT. Cite the
          report above (or see the dataset repo's README.md for the full
          BibTeX) whenever this data is used.

Two files are pulled from the latest release, both in the same long/tidy
schema (one row per geography x category x metric x node):
    - aei_claude_ai_2026-06-26.csv -- Claude.ai (chat/Cowork, Free/Pro/Max)
      usage, ~220MB, with global/country/subregion breakdowns.
    - aei_1p_api_2026-06-26.csv    -- Anthropic 1P API usage (excl. Claude
      Code), ~75MB, global breakdown only.

Each file mixes several `category_name` values (overall, onet, request,
soc_occupation). Filter to category_name == "soc_occupation" for the
occupation-level table used by this project. Occupations are keyed by
`node_external_id`, an O*NET-SOC code (e.g. "53-3031.00"); `node_name` is
the occupation title. The automation/augmentation split lives in the
metric_id column as collaboration_bucket_automation_pct and
collaboration_bucket_augmentation_pct (percent of conversations for that
occupation falling in each bucket). Only the `pct` metric is published at
country/subregion grain for soc_occupation -- the collaboration/artifact/
time-estimate metrics are global-only. See release_2026_06_26/
data_documentation.md (also mirrored alongside the CSVs on the Hugging Face
repo) for the full metric list.

Usage:
    python fetch_anthropic_economic_index.py

Requires internet access to huggingface.co -- run this from your own
machine, Colab, or inside the Kaggle notebook (with internet enabled in
notebook settings). It will not reach the source from a network-restricted
sandbox.
"""
import sys
from pathlib import Path

import requests

RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"

# (output filename, candidate URLs to try in order -- current release path
# first, with a couple of historical-release fallbacks in case the "latest"
# release folder gets renamed or this pinned release is superseded. Check
# https://huggingface.co/datasets/Anthropic/EconomicIndex for the current
# newest release_YYYY_MM_DD folder if all of these fail.)
FILES = {
    "claude_ai_usage": (
        "AEI_aei_claude_ai_2026-06-26.csv",
        [
            "https://huggingface.co/datasets/Anthropic/EconomicIndex/resolve/main/release_2026_06_26/data/aei_claude_ai_2026-06-26.csv",
            "https://huggingface.co/datasets/Anthropic/EconomicIndex/raw/main/release_2026_06_26/data/aei_claude_ai_2026-06-26.csv",
        ],
    ),
    "first_party_api_usage": (
        "AEI_aei_1p_api_2026-06-26.csv",
        [
            "https://huggingface.co/datasets/Anthropic/EconomicIndex/resolve/main/release_2026_06_26/data/aei_1p_api_2026-06-26.csv",
            "https://huggingface.co/datasets/Anthropic/EconomicIndex/raw/main/release_2026_06_26/data/aei_1p_api_2026-06-26.csv",
        ],
    ),
}


def _looks_like_csv(content: bytes) -> bool:
    """Reject HTML error/login pages masquerading as a 200 response."""
    head = content[:2048].lstrip().lower()
    if head.startswith(b"<!doctype") or head.startswith(b"<html"):
        return False
    # Real file starts with the known header row.
    return b"date_start" in content[:512]


def fetch_one(out_name: str, candidate_urls: list[str]) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RAW_DIR / out_name
    last_error = None
    for url in candidate_urls:
        try:
            # These files are ~75-220MB; stream instead of buffering in memory.
            with requests.get(url, timeout=180, stream=True) as resp:
                if resp.status_code != 200:
                    last_error = f"HTTP {resp.status_code} from {url}"
                    continue
                first_chunk = b""
                chunks = []
                for chunk in resp.iter_content(chunk_size=1024 * 1024):
                    chunks.append(chunk)
                    if not first_chunk:
                        first_chunk = chunk
                content = b"".join(chunks)
                if not _looks_like_csv(content):
                    last_error = f"Downloaded content from {url} does not look like the expected CSV (got HTML or unexpected header)."
                    continue
                out_path.write_bytes(content)
                print(f"Saved: {out_path}  ({len(content):,} bytes)  from {url}")
                return out_path
        except requests.RequestException as exc:
            last_error = f"{exc} ({url})"
    raise RuntimeError(
        f"Could not download {out_name} from any candidate URL. "
        f"Last error: {last_error}. Check "
        "https://huggingface.co/datasets/Anthropic/EconomicIndex in case the "
        "release folder or filename changed."
    )


def fetch() -> list[Path]:
    saved = []
    for key, (out_name, urls) in FILES.items():
        print(f"Downloading Anthropic Economic Index {key} ...")
        saved.append(fetch_one(out_name, urls))
    return saved


if __name__ == "__main__":
    paths = fetch()
    print(f"\nDone. {len(paths)} file(s) saved under {RAW_DIR}.")
    print(
        "Next: filter to category_name == 'soc_occupation' and "
        "hierarchy_level == 0 in each file to get detailed-occupation rows, "
        "keyed by node_external_id (O*NET-SOC code). The automation vs. "
        "augmentation split is in metric_id == "
        "'collaboration_bucket_automation_pct' / "
        "'collaboration_bucket_augmentation_pct'. Keep this as its own "
        "usage-evidence variable -- do not merge it into "
        "composite_exposure_score alongside AIOE/ILO."
    )
