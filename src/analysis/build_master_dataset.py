"""
Build the master occupation-level analysis table by joining every source in
data/raw/ on occupation code (see src/crosswalks/).

Planned columns (see docs/From_Exposure_to_Action_Data_Dictionary.xlsx ->
"Framework & Definitions" tab for exact definitions):

    - occupation_code (SOC), occupation_title
    - aioe_score                          (AIOE)
    - oecd_exposure_score                 (OECD AI Exposure Measure)
    - ilo_task_automation_share           (ILO, aggregated from task-level)
    - gpts_are_gpts_score                 (Eloundou et al.)
    - composite_exposure_score            (standardized average of the four above)
    - impact_pattern                      (Automation / Transformation / Augmentation)
    - anthropic_usage_automation_share    (Anthropic Economic Index)
    - anthropic_usage_augmentation_share  (Anthropic Economic Index)
    - employment_growth_rate              (BLS OEWS, multi-year)
    - job_zone                            (O*NET — education/experience/training)
    - skill_profile_vector                (O*NET Skills/Abilities, for similarity calc)

Status: TODO — write once at least AIOE and O*NET have been pulled
(src/data_acquisition/fetch_aioe.py, fetch_onet.py). This is the next
concrete step after data acquisition.
"""

raise NotImplementedError("Not started yet — see the module docstring for the planned join.")
