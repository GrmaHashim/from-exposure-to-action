# From Exposure to Action
### A Data-Driven Career Compass for the AI Era

**Will AI replace human jobs, and which occupations are most at risk of AI-driven displacement, transformation, or augmentation — and what should students and working professionals actually do about it?**

This project answers that question with data instead of headlines, then turns the findings into a practical guide for two audiences: people choosing an academic/career path, and people deciding whether to reskill or pivot.

---

## Why this project is different

Most public discussion collapses AI's effect on jobs into a single yes/no: *"will AI take my job?"* This project deliberately avoids that trap by classifying every occupation into one of three patterns instead of a binary:

| Pattern | Meaning |
|---|---|
| **Automation** | AI performs the task itself; human labor input for that task drops toward zero. |
| **Transformation** | The job's mix of tasks changes shape — some tasks automate, others emerge or grow in importance — the occupation persists but looks different. |
| **Augmentation** | AI extends or enhances human output on a task rather than replacing the human performing it. |

It also separates **theoretical exposure** (what AI *could* do, per capability indices) from **realized impact** (what has actually shown up in employment and wage data so far) — a distinction the International Labour Organization explicitly warns is often missing from public conversation.

## Research questions

- **Main question** — Will AI replace human jobs, and which occupations are most at risk of AI-driven displacement, transformation, or augmentation?
- **RQ1** — Consolidated risk ranking: how do occupations rank across independent AI-exposure indices, and where do those indices agree or disagree?
- **RQ2** — Which occupations are Automation-, Transformation-, or Augmentation-dominant?
- **RQ3** — Which specific tasks within an occupation are most vulnerable to AI automation?
- **RQ4** — What skill profile (analytical, social, creative, physical, supervisory) protects an occupation from AI exposure?
- **RQ5** — Is higher AI exposure already associated with real employment/wage changes, or is the risk still mostly theoretical?
- **Student layer** — For a given education path, what is the typical AI-exposure profile of the occupations it leads to?
- **Professional layer** — For someone in a high-exposure occupation (including a career changer), what are the nearest lower-exposure occupations by skill similarity, and what is the skill gap?
- **Appendix** — Where does Canada fit relative to the global/US picture (one comparison only, using Statistics Canada's own NOC-based estimates)?

Full definitions, hypotheses, and target variables are in [`docs/From_Exposure_to_Action_Data_Dictionary.xlsx`](docs/From_Exposure_to_Action_Data_Dictionary.xlsx) — the living reference for this project (dataset registry, classification crosswalks, research question map, framework & definitions, Phase 2 design spec).

## Guardrails (deliberately out of scope)

- **No US-vs-Canada framing.** Canada appears once, as a contextual comparison, not a parallel analysis.
- **No forecasting.** Every dataset used is a point-in-time measure or historical panel — the project stays descriptive/associative, never predictive.
- **No prescriptive advice.** Outputs are decision-support (evidence → risks → opportunities → skills → alternatives), never "AI says you should become X."
- **No native mobile app.** Phase 2 is a responsive web app — same Python stack as Phase 1, no separate app-dev track.

## Data sources

| Dataset | Publisher | Classification | Used for |
|---|---|---|---|
| [AIOE](https://github.com/AIOE-Data/AIOE) (Felten, Raj & Seamans) | Academic / open | US SOC | RQ1 |
| [OECD AI Exposure Measure](https://www.oecd.org/en/publications/the-oecd-ai-exposure-measure_f3da0f0a-en.html) | OECD | ISCO-aligned | RQ1 |
| [ILO Generative AI and Jobs (2025 update)](https://www.ilo.org/publications/generative-ai-and-jobs-refined-global-index-occupational-exposure) | ILO | ISCO-08, task-level | RQ2, RQ3 |
| [O\*NET Database](https://www.onetcenter.org/database.html) | US Dept. of Labor | O\*NET-SOC | RQ4, student layer, professional layer |
| [BLS OEWS](https://www.bls.gov/oes/tables.htm) | US Bureau of Labor Statistics | US SOC | RQ5 |
| [GPTs are GPTs](https://www.science.org/doi/10.1126/science.adj0998) (Eloundou et al.) | OpenAI / Science | O\*NET-SOC | RQ1 |
| [Anthropic Economic Index](https://www.anthropic.com/economic-index) | Anthropic | O\*NET task categories | RQ2, RQ5 |
| [Statistics Canada AI Occupational Exposure](https://www150.statcan.gc.ca/n1/pub/36-28-0001/2026001/article/00001-eng.htm) | Statistics Canada | NOC | Appendix |

Every source keeps its own license/citation requirement — see the header comment in each `src/data_acquisition/*.py` script and cite the original authors in any published notebook or report.

## Repository structure

```
from-exposure-to-action/
├── data/
│   ├── raw/          # downloaded, unmodified source files (gitignored — regenerate with fetch scripts)
│   ├── interim/       # cleaned/joined intermediate tables (gitignored)
│   └── processed/     # final master dataset(s) — small enough to commit / publish as a Kaggle Dataset
├── src/
│   ├── data_acquisition/  # one fetch_<source>.py script per dataset
│   ├── crosswalks/        # SOC <-> O*NET-SOC <-> ISCO-08 <-> NOC mapping helpers
│   └── analysis/          # scripts that build the master joined dataset and compute target variables
├── notebooks/              # the Kaggle/Jupyter analysis notebook(s) — Phase 1 deliverable
├── docs/                   # Data Dictionary workbook and any supporting reference material
└── outputs/figures/        # exported charts for the notebook/report
```

## Roadmap

- [x] Research framework locked (questions, typology, hypotheses, target variables, guardrails)
- [x] Data Dictionary workbook (dataset registry, crosswalks, research question map, Phase 2 spec)
- [x] Repository scaffold
- [x] **Phase 1 — Data acquisition:** pull and cache all 8 datasets (`src/data_acquisition/`) — 7 of 8 fetched; OECD's AI Exposure Measure investigated and dropped (no downloadable dataset exists, only PDF text) rather than pending
- [x] **Phase 1 — Crosswalk & join:** build the master occupation-level table (`src/analysis/build_master_dataset.py`)
- [x] **Phase 1 — Analysis notebook:** answer RQ1–RQ5 + student/professional layers + Canada appendix (`notebooks/`)
- [x] **Phase 1 — Publish:** push notebook + processed dataset to Kaggle, push repo to GitHub
- [ ] **Phase 2 — Web app:** Streamlit/Gradio app built on Phase 1's outputs

## Setup

```bash
python -m venv .venv && source .venv/bin/activate   # or use conda
pip install -r requirements.txt
```

Note: the fetch scripts in `src/data_acquisition/` need an internet connection to the original data hosts (GitHub, onetcenter.org, bls.gov, oecd.org, ilo.org, statcan.gc.ca) — run them from your own machine, Colab, or directly inside the Kaggle notebook (Kaggle's execution environment has internet access when enabled in notebook settings).

## Author

Mohamed Ali — [LinkedIn](#) — Calgary, AB, Canada

## License

Code in this repository is released under the MIT License (see `LICENSE`). Each dataset in `data/` retains its original publisher's license and citation requirement, listed above and in the Data Dictionary.
