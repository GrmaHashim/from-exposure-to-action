"""
Professional/reskilling layer: for a chosen (typically high-exposure)
occupation, find the most skill-similar occupations with a meaningfully
lower composite exposure score, and show the skill gap for each.

Mirrors notebooks/01_exploratory_analysis.ipynb's Professional layer
section, but calls the shared nearest_lower_exposure_alternatives()
function from src/analysis/build_master_dataset.py instead of a
duplicated copy, so both surfaces stay in sync.
"""
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import pandas as pd
import plotly.express as px
import streamlit as st

from utils import get_alternatives, get_skill_cols, load_master

st.set_page_config(page_title="Reskilling Alternatives", page_icon="\U0001F504", layout="wide")
st.title("Nearest lower-exposure alternatives")

st.markdown(
    """
This is **evidence to weigh, not a recommendation**. It ranks occupations by how
similar their required skill profile is to your starting occupation (O\\*NET Basic
Skills importance ratings, cosine similarity) — restricted to occupations with a
meaningfully lower composite AI-exposure score. A close skill match with a real
exposure gap is worth investigating further; it is not a guarantee of an easier
transition.
"""
)

with st.expander("What do the terms on this page mean?"):
    st.markdown(
        """
**Exposure score** — how exposed an occupation is to AI, on a scale centered at 0
(0 = average across all occupations analyzed; higher = more exposed, lower = less).
It blends several independent research indices, standardized onto the same scale
so they can be compared and averaged.

**Skill similarity** — how alike two occupations' *required* skills are (not your
personal skills), from 0% to 100%. It compares each occupation's O\\*NET skill
profile (how important things like Critical Thinking, Mathematics, or Active
Listening are rated for that occupation) and measures how closely the patterns
match. 100% would mean identical skill requirements.

**Minimum exposure gap required** *(slider)* — how much lower an alternative
occupation's exposure score must be than your starting occupation's, before it's
even considered a candidate. At 0, any occupation with a lower score qualifies —
even by a tiny amount. Raise it to only see alternatives with a clearly
meaningful drop in exposure, filtering out ones where the difference is small
enough to not mean much in practice.

**Importance rating difference** *(skill gap chart)* — for one specific skill,
the alternative occupation's O\\*NET importance rating (1-5 scale) minus your
starting occupation's rating for that same skill. It describes what the two
*occupations* typically require, not how good you personally are at that skill.
Green/positive = that skill matters more in the alternative role (a possible gap
to close); red/negative = it matters less there.
"""
    )

try:
    master = load_master()
except (FileNotFoundError, ValueError) as e:
    st.error(str(e))
    st.stop()

skill_cols = get_skill_cols(master)
if not skill_cols:
    st.error("No O*NET skill columns (skill__*) found in the dataset — this page needs them.")
    st.stop()

usable = master.dropna(subset=skill_cols + ["composite_exposure_score"])
titled = usable.dropna(subset=["occupation_title"]).sort_values("occupation_title")
options = titled["occupation_title"] + "  (" + titled["soc_code"].astype(str) + ")"

col_select, col_n, col_gap = st.columns([3, 1, 1])
with col_select:
    choice = st.selectbox("Starting occupation (yours, or one you're considering leaving)",
                           options.tolist(), index=None,
                           placeholder="Start typing an occupation title...")
with col_n:
    n = st.slider(
        "How many alternatives", min_value=3, max_value=15, value=5,
        help="Number of alternative occupations to list, ranked by skill similarity.",
    )
with col_gap:
    min_gap = st.slider(
        "Minimum exposure gap required", min_value=0.0, max_value=2.0, value=0.0, step=0.1,
        help=(
            "How much lower an alternative's exposure score must be than your starting "
            "occupation's to qualify as a candidate. 0 = any lower score qualifies, even a "
            "tiny one. Raise it to require a clearly meaningful drop in exposure. See "
            "'What do the terms on this page mean?' above for more."
        ),
    )

if choice is None:
    st.info("Pick a starting occupation above.")
    st.stop()

soc_code = choice.split("(")[-1].rstrip(")")
source_row = master.loc[master["soc_code"] == soc_code].iloc[0]

st.subheader(f"Alternatives to: {source_row['occupation_title']}")
st.caption(f"Its composite exposure score: {source_row['composite_exposure_score']:.2f}")

results = get_alternatives(soc_code, master, skill_cols, n=n, min_gap=min_gap)

if results.empty:
    st.warning(
        "No occupations found with a meaningfully lower exposure score and complete skill data. "
        "Try lowering the minimum exposure gap slider."
    )
    st.stop()

left, right = st.columns([3, 2])

with left:
    st.markdown("**Candidate alternatives**")
    st.caption(
        "Skill similarity: how closely the alternative's required skill profile matches your "
        "starting occupation's (100% = identical). See the glossary above for details."
    )
    show = results[["occupation_title", "composite_exposure_score", "skill_similarity"]].copy()
    show["skill_similarity"] = (show["skill_similarity"] * 100).round(1)
    show = show.rename(columns={
        "occupation_title": "Occupation",
        "composite_exposure_score": "Exposure score",
        "skill_similarity": "Skill similarity (%)",
    })
    st.dataframe(show, use_container_width=True, hide_index=True)

with right:
    fig = px.bar(
        results.sort_values("skill_similarity"),
        x="skill_similarity", y="occupation_title", orientation="h",
        labels={"skill_similarity": "Skill similarity", "occupation_title": ""},
    )
    fig.update_layout(xaxis_tickformat=".0%")
    st.plotly_chart(fig, use_container_width=True)

st.divider()
st.subheader("Skill gap detail")
top_choice_title = st.selectbox(
    "Show the skill gap for:", results["occupation_title"].tolist(), index=0,
)
top_row = results.loc[results["occupation_title"] == top_choice_title].iloc[0]
gap_cols = [c for c in results.columns if c.startswith("gap__")]
gap_df = pd.DataFrame({
    "skill": [c.replace("gap__skill__", "").replace("_", " ").title() for c in gap_cols],
    "gap": [top_row[c] for c in gap_cols],
})
gap_df = gap_df.sort_values("gap")
fig2 = px.bar(
    gap_df, x="gap", y="skill", orientation="h",
    color="gap", color_continuous_scale=["#EF553B", "#B0B0B0", "#00CC96"],
    color_continuous_midpoint=0,
    labels={"gap": "Importance rating difference vs. starting occupation", "skill": ""},
)
st.plotly_chart(fig2, use_container_width=True)
st.caption(
    "Each bar compares how important a skill is rated for the two occupations (O*NET 1-5 importance "
    "scale), not your personal skill level. Positive/green = this skill matters more in the "
    "alternative occupation than in your starting one — a possible skill gap to close. "
    "Negative/red = it matters less there."
)
