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

Status: SOC <-> O*NET-SOC needs no external file — O*NET's own
"Occupation Data.xlsx" already lists both the O*NET-SOC code and the
underlying SOC code for every occupation. This module will grow to include:

    - soc_to_onet_soc(code: str) -> list[str]
    - onet_soc_to_soc(code: str) -> str
    - isco_to_soc(code: str) -> str | None   (approximate; see ILO/OECD docs)
    - noc_to_onet_soc(code: str) -> str | None   (via LMIC-CIMT / The Dais
      crosswalk, appendix use only)

TODO: implement once O*NET's Occupation Data.xlsx and the ISCO/NOC
crosswalk reference files have been pulled into data/raw/.
"""

raise NotImplementedError(
    "Crosswalk functions are not implemented yet — this is a placeholder "
    "for the next step, after fetch_onet.py has been run and "
    "data/raw/onet_db_31_0/Occupation Data.xlsx exists."
)
