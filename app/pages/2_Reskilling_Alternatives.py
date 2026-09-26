"""
Professional/reskilling layer: for a chosen (typically high-exposure)
occupation, find the occupations whose skill EMPHASIS pattern is most
aligned with it (not raw skill-rating similarity -- see
nearest_lower_exposure_alternatives()'s docstring for why raw cosine
similarity is misleading) among those with a meaningfully lower composite
exposure score, show the skill gap for each, and tag whether the
alternative shares a field of study (NCES CIP-SOC crosswalk).

Skill alignment is computed over three combined O*NET column families
(see utils.get_skill_cols()): the 10 generic Basic Skills, the 24 more
specific Cross-Functional/Technical Skills, and the 33 Knowledge domains --
not just the 10 Basic Skills alone, which real-data testing showed was too
generic to meaningfully distinguish occupations.

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

from utils import (
    field_of_study_tag,
    get_alternatives,
    get_skill_cols,
    load_cip_soc_crosswalk,
    load_master,
    typical_fields_of_study,
)

st.set_page_config(page_title="Reskilling Alternatives", page_icon="\U0001F504", layout="wide")
st.title("Nearest lower-exposure alternatives")

st.markdown(
    """
This is **evidence to weigh, not a recommendation**. It ranks occupations by how
closely their skill EMPHASIS pattern lines up with your starting occupation's —
which skills matter *relatively* more or less there, compared to the typical
occupation — restricted to occupations with a meaningfully lower composite
AI-exposure score. A close alignment with a real exposure gap is worth
investigating further; it is not a guarantee of an easier transition.
"""
)

with st.expander("What do the terms on this page mean?"):
    st.markdown(
        """
**Exposure score** — how exposed an occupation is to AI, on a scale centered at 0
(0 = average across all occupations analyzed; higher = more exposed, lower = less).
It blends several independent research indices, standardized onto the same scale
so they can be compared and averaged.

**Skill alignment** — how closely two occupations' skill *emphasis patterns*
match, on a scale that's typically around -1 to +1 (higher = more aligned; 0 or
negative = little to no meaningful alignment). This is **not** a "percent match" —
it compares which skills each occupation leans on *more than usual*, relative to
the typical occupation, not the raw importance ratings themselves. That
distinction matters: almost every occupation rates baseline skills like Active
Listening or Reading Comprehension as moderately-to-highly important, so
comparing raw ratings directly would make nearly any two occupations look
"similar" just because they share that common baseline. This tool corrects for
it by looking at each occupation's *distinctive* profile instead, across three
combined O\\*NET sources: 10 general Basic Skills (Reading Comprehension,
Mathematics, Critical Thinking...), 24 more specific Cross-Functional/Technical
Skills (Programming, Troubleshooting, Repairing, Negotiation...), and 33
Knowledge domains (Computers and Electronics, Mechanical, Medicine and
Dentistry...) — so, for example, Data Scientists' emphasis on Programming and
Computers and Electronics is what gets compared, not the fact that both a data
scientist and an electrician need to be able to read and communicate at a
basic level.

**Field of study** — whether the U.S. Dept. of Education's official CIP-SOC
crosswalk lists at least one college/diploma program in common as typically
leading to both occupations. *Same field of study* = a realistic path without
a new degree is plausible on paper. *Different field of study* = the
government crosswalk lists no shared program — a real signal worth taking
seriously (you generally can't become a physician on skill alignment alone),
but read it as "different formal program," not "unrelated in practice." The
CIP taxonomy is sometimes more fine-grained than real career ladders: for
example, it treats Registered Nursing and Licensed Practical/Vocational
Nursing as two entirely separate programs with zero overlap, even though
RN-to-LPN is one of the most walkable transitions in healthcare. *Not in
field-of-study data* means the crosswalk simply has no entry for one of the
two occupations — not a "same" or "different" verdict, just missing
information.

**Minimum exposure gap required** *(slider)* — how much lower an alternative
occupation's exposure score must be than your starting occupation's, before it's
even considered a candidate. At 0, any occupation with a lower score qualifies —
even by a tiny amount. Raise it to only see alternatives with a clearly
meaningful drop in exposure, filtering out ones where the difference is small
enough to not mean much in practice. Raising it can also lower the skill
alignment of the results: occupations most aligned in skills with your starting
one are often similarly exposed to AI, so requiring a bigger exposure drop can
filter them out, leaving only more distant matches. A warning appears below when
this happens.

**Importance rating difference** *(skill gap chart)* — for one specific skill,
the alternative occupation's O\\*NET importance rating (1-5 scale) minus your
starting occupation's rating for that same skill. It describes what the two
*occupations* typically require, not how good you personally are at that skill.
Green/positive = that skill matters more in the alternative role (a possible gap
to close); red/negative = it matters less there. (Unlike Skill alignment above,
this one uses the raw 1-5 ratings, so it stays easy to read directly.)
"""
    )

try:
    master = load_master()
except (FileNotFoundError, ValueError) as e:
    st.error(str(e))
    st.stop()

skill_cols = get_skill_cols(master)
if not skill_cols:
    st.error(
        "No O*NET skill/knowledge columns (skill__*, xfskill__*, knowledge__*) found in the "
        "dataset — this page needs them."
    )
    st.stop()

cip_soc_df = load_cip_soc_crosswalk()

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
        help="Number of alternative occupations to list, ranked by skill alignment.",
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
source_fields = typical_fields_of_study(soc_code, cip_soc_df)
if source_fields:
    st.caption(
        "Typical field(s) of study for this occupation (NCES CIP-SOC crosswalk): "
        + ", ".join(source_fields) + ("..." if len(source_fields) == 6 else "")
    )
elif cip_soc_df is not None:
    st.caption("No field-of-study data found for this occupation in the NCES crosswalk.")

results = get_alternatives(soc_code, master, skill_cols, n=n, min_gap=min_gap)

if results.empty:
    st.warning(
        "No occupations found with a meaningfully lower exposure score and complete skill data. "
        "Try lowering the minimum exposure gap slider."
    )
    st.stop()

avg_alignment = results["skill_similarity"].mean()
if avg_alignment < 0.3:
    st.warning(
        f"With 'Minimum exposure gap required' set this high, the alternatives below have a "
        f"large exposure drop from your starting occupation, but only weak skill overlap with "
        f"it (average skill alignment: {avg_alignment:.2f}). That's an expected trade-off, not "
        "an error -- the occupations most aligned in skills with your starting one are often "
        "similarly exposed to AI, so requiring a bigger exposure drop leaves fewer, more "
        "distant matches. Lower the slider to see closer skill matches, at the cost of a "
        "smaller exposure gap."
    )

left, right = st.columns([3, 2])

with left:
    st.markdown("**Candidate alternatives**")
    st.caption(
        "Skill alignment: how closely the alternative's distinctive skill emphasis matches your "
        "starting occupation's (roughly -1 to +1; not a percent match). Field of study: whether "
        "a shared educational path is plausible on paper (NCES crosswalk) — this can understate "
        "real-world adjacency for closely related credentials; see the glossary above."
    )
    show = results[["occupation_title", "composite_exposure_score", "skill_similarity"]].copy()
    show["skill_similarity"] = show["skill_similarity"].round(2)
    show["Field of study"] = [
        field_of_study_tag(soc_code, r, cip_soc_df) for r in results["soc_code"]
    ]
    show = show.rename(columns={
        "occupation_title": "Occupation",
        "composite_exposure_score": "Exposure score",
        "skill_similarity": "Skill alignment",
    })
    st.dataframe(show, use_container_width=True, hide_index=True)

with right:
    fig = px.bar(
        results.sort_values("skill_similarity"),
        x="skill_similarity", y="occupation_title", orientation="h",
        color="skill_similarity", color_continuous_scale=["#EF553B", "#B0B0B0", "#00CC96"],
        color_continuous_midpoint=0,
        labels={"skill_similarity": "Skill alignment", "occupation_title": ""},
    )
    fig.update_layout(coloraxis_showscale=False)
    st.plotly_chart(fig, use_container_width=True)

st.divider()
st.subheader("Skill gap detail")

CATEGORY_LABELS = {
    "skill__": "Basic Skill",
    "xfskill__": "Technical/Cross-Functional Skill",
    "knowledge__": "Knowledge Domain",
}


def _prettify_gap_col(col: str):
    """'gap__xfskill__programming' -> ('Technical/Cross-Functional Skill', 'Programming')."""
    raw = col[len("gap__"):]
    for prefix, category in CATEGORY_LABELS.items():
        if raw.startswith(prefix):
            return category, raw[len(prefix):].replace("_", " ").title()
    return "Other", raw.replace("_", " ").title()


col_choice, col_top_n = st.columns([3, 1])
with col_choice:
    top_choice_title = st.selectbox(
        "Show the skill gap for:", results["occupation_title"].tolist(), index=0,
    )
with col_top_n:
    top_n_gaps = st.slider(
        "How many skills to show", min_value=5, max_value=20, value=10,
        help="Across all 67 skill/knowledge dimensions used for alignment, show only the ones "
             "that differ the most between the two occupations -- the ones most worth reading.",
    )

top_row = results.loc[results["occupation_title"] == top_choice_title].iloc[0]
gap_cols = [c for c in results.columns if c.startswith("gap__")]
gap_records = []
for c in gap_cols:
    category, label = _prettify_gap_col(c)
    gap_records.append({"category": category, "skill": label, "gap": top_row[c]})
gap_df = pd.DataFrame(gap_records)
gap_df["abs_gap"] = gap_df["gap"].abs()
top_gap_df = gap_df.sort_values("abs_gap", ascending=False).head(top_n_gaps).sort_values("gap")
SHORT_CATEGORY = {
    "Basic Skill": "Basic", "Technical/Cross-Functional Skill": "Technical", "Knowledge Domain": "Knowledge",
}
top_gap_df["label"] = top_gap_df["skill"] + " (" + top_gap_df["category"].map(SHORT_CATEGORY) + ")"

fig2 = px.bar(
    top_gap_df, x="gap", y="label", orientation="h",
    color="gap", color_continuous_scale=["#EF553B", "#B0B0B0", "#00CC96"],
    color_continuous_midpoint=0,
    labels={"gap": "Importance rating difference vs. starting occupation", "label": ""},
)
fig2.update_layout(coloraxis_showscale=False)
st.plotly_chart(fig2, use_container_width=True)
st.caption(
    f"Showing the {top_n_gaps} skills/knowledge areas with the biggest difference (out of "
    f"{len(gap_cols)} compared) between the two occupations, each labeled with its source "
    "(Basic / Technical / Knowledge). Positive/green = matters more in the alternative "
    "occupation than in your starting one — a possible gap to close. Negative/red = it matters "
    "less there. These are O*NET 1-5 importance ratings for the occupations, not your personal "
    "skill level."
)
