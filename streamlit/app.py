"""STRETCH — Streamlit dashboard for fda-signal-watch.

Run:  streamlit run streamlit/app.py
"""

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.cache import list_cache  # noqa: E402
from src.client import OpenFDAClient  # noqa: E402
from src.signals import collect_window, quarterly_windows, score_windows, track_emergence  # noqa: E402

st.set_page_config(page_title="FDA Signal Watch", layout="wide")
st.title("FDA Signal Watch — pharmacovigilance early warning")

drug = st.text_input("Drug (medicinalproduct)", "aspirin")
n_windows = st.slider("Windows (quarters, most recent first)", 2, 12, 6)
min_consec = st.slider("Min consecutive hot windows", 1, 4, 2)

if st.button("Run analysis", type="primary"):
    windows = quarterly_windows(2024, 2026)[-n_windows:]
    client = OpenFDAClient(max_requests_per_run=4 * n_windows + 10)
    with st.spinner("Pulling FAERS aggregations (cached where possible)…"):
        data = collect_window(client, drug, windows)
        scored = score_windows(data)
        emergence = track_emergence(scored, min_consecutive=min_consec)
    st.success(f"Done — {client.requests_made} API calls, "
               f"{client.cache_hits} cache hits")
    latest_label = windows[-1][0]
    st.subheader(f"Top signals — {latest_label}")
    st.dataframe(scored[latest_label][
        ["term", "a_raw", "prr", "prr_lo", "prr_hi", "ror", "chi2",
         "is_signal"]].head(25))
    st.subheader("Emerging signals")
    st.dataframe(emergence if len(emergence) else pd.DataFrame(
        {"note": ["No emergent signals under current rule."]}))

st.sidebar.header("Cache")
for row in list_cache():
    st.sidebar.caption(f"{row['key']}: {str(row['params'])[:80]}… "
                       f"({row['age_days']}d old)")
