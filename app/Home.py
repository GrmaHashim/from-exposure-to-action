"""
Phase 2 MVP entry point: `streamlit run app/Home.py`

Covers the "Overview" slice of the 5 dashboard dimensions marked Ready in
the Phase 1 notebook's Summary section: AI Exposure (composite), Task
Automation share, and Impact Pattern, at the whole-dataset level. Per-
occupation detail lives on the Explore page; reskilling search lives on
the Alternatives page (see app/pages/).
"""
import plotly.express as px
import streamlit as st

from utils import IMPACT_PATTERN_DEFINITIONS, load_master

st.set_page_config(
    page_title="From Exposure to Action",
    page_icon="\U0001F9ED",
    layout="wide",
)

st.title("From Exposure to Action")
st.caption("A Data-Driven Career Compass for the AI Era — Phase 2 MVP")

st.markdown(
    """
Most public discussion collapses AI's effect on jobs into a single yes/no:
*"will AI take my job?"* This tool classifies occupations into one of three
patterns instead of a binary — **Automation**, **Transformation**, or
**Augmentation** — and separates *theoretical exposure* (what AI could do)
from decision-support evidence you can weigh yourself.

**This tool shows evidence, not verdicts.** Nothing here says "you should
become X." Use the **Explore Occupation** and **Reskilling Alternatives**
pages in the sidebar to dig into a specific occupation.
"""
)

try:
    master = load_master()
except (FileNotFoundError, ValueError) as e:
    st.error(str(e))
    st.stop()

n_occ = len(master)
n_with_pattern = master["impact_pattern"].notna().sum() if "impact_pattern" in master.columns else 0

col1, col2, col3 = st.columns(3)
col1.metric("Occupations analyzed", f"{n_occ:,}")
col2.metric("With an Impact Pattern classification", f"{n_with_pattern:,}")
if "composite_exposure_score" in master.columns:
    col3.metric("Median composite exposure score", f"{master['composite_exposure_score'].median():.2f}")

st.divider()

left, right = st.columns([3, 2])

with left:
    st.subheader("Composite AI Exposure Score — distribution across occupations")
    st.caption(
        "Standardized (z-scored) average of AIOE, ILO, and GPTs-are-GPTs exposure indices. "
        "0 = average exposure across all occupations in this dataset; positive = more exposed."
    )
    fig = px.histogram(
        master.dropna(subset=["composite_exposure_score"]),
        x="composite_exposure_score",
        nbins=40,
        labels={"composite_exposure_score": "Composite exposure score"},
    )
    fig.update_layout(yaxis_title="Number of occupations", bargap=0.05)
    st.plotly_chart(fig, use_container_width=True)

with right:
    if "impact_pattern" in master.columns and n_with_pattern:
        st.subheader("Impact Pattern mix")
        counts = master["impact_pattern"].value_counts().reset_index()
        counts.columns = ["impact_pattern", "count"]
        fig2 = px.pie(counts, names="impact_pattern", values="count", hole=0.45)
        st.plotly_chart(fig2, use_container_width=True)
        with st.expander("What do these patterns mean?"):
            for pattern, definition in IMPACT_PATTERN_DEFINITIONS.items():
                st.markdown(f"**{pattern}** — {definition}")

st.divider()

st.subheader("Highest- and lowest-exposure occupations")
tab_top, tab_bottom = st.tabs(["Highest exposure", "Lowest exposure"])

display_cols = [c for c in
                 ["occupation_title", "composite_exposure_score", "impact_pattern", "job_zone"]
                 if c in master.columns]
ranked = master.dropna(subset=["composite_exposure_score"]).sort_values(
    "composite_exposure_score", ascending=False
)

with tab_top:
    st.dataframe(ranked[display_cols].head(15), use_container_width=True, hide_index=True)
with tab_bottom:
    st.dataframe(ranked[display_cols].tail(15).iloc[::-1], use_container_width=True, hide_index=True)

st.divider()
st.caption(
    "Data and methodology: see the full Phase 1 analysis notebook and Data Dictionary at "
    "github.com/GrmaHashim/from-exposure-to-action. This MVP currently covers 5 of the 10 "
    "planned dashboard dimensions (AI Exposure, Task Automation share, Impact Pattern, Required "
    "education/Job Zone, Nearest lower-exposure alternatives); the rest are marked Partial/Missing "
    "in the notebook's Summary section pending additional O*NET/BLS data."
)
