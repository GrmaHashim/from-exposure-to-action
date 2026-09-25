"""
Explore a single occupation: composite exposure score (with percentile
context), Impact Pattern, task automation summary, and required
education/experience (Job Zone).
"""
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import plotly.graph_objects as go
import streamlit as st

from utils import IMPACT_PATTERN_DEFINITIONS, exposure_percentile, job_zone_label, load_master

st.set_page_config(page_title="Explore Occupation", page_icon="\U0001F50D", layout="wide")
st.title("Explore an occupation")

try:
    master = load_master()
except (FileNotFoundError, ValueError) as e:
    st.error(str(e))
    st.stop()

titled = master.dropna(subset=["occupation_title"]).sort_values("occupation_title")
options = titled["occupation_title"] + "  (" + titled["soc_code"].astype(str) + ")"
choice = st.selectbox("Search or select an occupation", options.tolist(), index=None,
                       placeholder="Start typing an occupation title...")

if choice is None:
    st.info("Pick an occupation above to see its AI-exposure profile.")
    st.stop()

soc_code = choice.split("(")[-1].rstrip(")")
row = master.loc[master["soc_code"] == soc_code].iloc[0]

st.subheader(row["occupation_title"])
st.caption(f"SOC code: {soc_code}")

col1, col2, col3 = st.columns(3)

score = row.get("composite_exposure_score")
with col1:
    if score is not None and score == score:  # present and not NaN
        pct = exposure_percentile(master, score)
        st.metric("Composite exposure score", f"{score:.2f}")
        if pct == pct:  # not NaN
            st.caption(f"More exposed than {pct:.0f}% of occupations in this dataset.")
    else:
        st.metric("Composite exposure score", "N/A")

with col2:
    pattern = row.get("impact_pattern")
    st.metric("Impact Pattern", pattern if isinstance(pattern, str) else "Not classified")
    if isinstance(pattern, str) and pattern in IMPACT_PATTERN_DEFINITIONS:
        st.caption(IMPACT_PATTERN_DEFINITIONS[pattern])

with col3:
    jz = row.get("job_zone")
    st.metric("Required preparation (Job Zone)", job_zone_label(jz) if jz == jz else "N/A")
    st.caption("O*NET Job Zone: typical education / experience / training needed.")

if isinstance(row.get("impact_pattern"), str):
    st.caption(
        "Note: Impact Pattern is a provisional classification derived from ILO task-level score "
        "variance (see notebook RQ2) — the research found it does not yet cleanly predict real-world "
        "AI usage patterns (Anthropic Economic Index cross-check), so treat it as one input, not a verdict."
    )

st.divider()

st.subheader("Task automation exposure")
task_mean = row.get("ilo_task_mean")
task_std = row.get("ilo_task_std")
if task_mean == task_mean:  # not NaN
    c1, c2 = st.columns(2)
    c1.metric("Average task-level exposure (ILO)", f"{task_mean:.2f}")
    if task_std == task_std:
        c2.metric("Spread across this occupation's tasks", f"{task_std:.2f}")
    st.caption(
        "Higher spread means this occupation's own tasks vary a lot in how exposed they are "
        "(consistent with a Transformation pattern); low spread with a high mean is more "
        "consistent with broad Automation; low spread with a low mean, broad Augmentation-only exposure."
    )
else:
    st.caption("Task-level ILO data not available for this occupation.")

st.divider()

st.subheader("Where this occupation sits vs. the dataset median")
median_score = master["composite_exposure_score"].median()
fig = go.Figure()
fig.add_trace(go.Bar(
    x=["This occupation", "Dataset median"],
    y=[score if score == score else 0, median_score],
    marker_color=["#636EFA", "#B0B0B0"],
))
fig.update_layout(yaxis_title="Composite exposure score", showlegend=False)
st.plotly_chart(fig, use_container_width=True)

st.caption("Looking for lower-exposure alternatives to this occupation? Open **Reskilling Alternatives** in the sidebar.")
