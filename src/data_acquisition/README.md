# Data acquisition scripts

One `fetch_<source>.py` per dataset in the Data Dictionary's **Dataset Registry** tab. Each script downloads the source's raw file(s) into `data/raw/` and does nothing else — cleaning and joining happens in `src/analysis/`.

| Script | Dataset | Status |
|---|---|---|
| `fetch_aioe.py` | AIOE (Felten, Raj & Seamans) | ✅ implemented |
| `fetch_onet.py` | O\*NET core files (Tasks, Skills, Abilities, Job Zones) | ✅ implemented (FILES_OF_INTEREST corrected for v31.0's renamed files) |
| `fetch_ilo_genai.py` | ILO Generative AI and Jobs (2025 update, Working Paper 140) | ✅ implemented (occupation-level + task-level files) |
| `fetch_bls_crosswalks.py` | BLS ISCO-08<->SOC2010 and SOC2010->SOC2018 reference crosswalks | ✅ implemented (needed to join ILO/OECD's ISCO-08 codes onto the SOC-keyed master table) |
| `fetch_oecd_exposure.py` | OECD AI Exposure Measure | ⬜ next |
| `fetch_bls_oews.py` | BLS OEWS employment & wages (multi-year) | ⬜ next |
| `fetch_gpts_are_gpts.py` | GPTs are GPTs (Eloundou et al.) | ⬜ next |
| `fetch_anthropic_economic_index.py` | Anthropic Economic Index | ⬜ next |
| `fetch_statcan_canada.py` | Statistics Canada AI occupational exposure (appendix) | ⬜ later (appendix only) |

Run each script from an environment with internet access to the source's own domain (your machine, Colab, or the Kaggle notebook itself with internet enabled) — this project's cloud dev sandbox has restricted network egress and cannot execute these downloads directly.
