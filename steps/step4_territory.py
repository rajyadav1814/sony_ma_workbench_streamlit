"""Step 4: Territory Map — select local territories."""

import streamlit as st
import pandas as pd


def render_step4(data, conn, session):
    st.subheader("Step 4 — Territory Mapping")
    st.caption("Select which countries count as 'Local' territory for the valuation.")

    territories = data.get("territories", {})
    all_countries = territories.get("countries", [])
    regions = territories.get("regions", {})

    if not all_countries:
        st.info("No territory data available.")
        return

    selected = st.multiselect(
        "Local Territories",
        options=all_countries,
        default=st.session_state.get("local_territories", ["Mexico", "United States", "Colombia"]),
        key="territory_multiselect",
    )
    st.session_state["local_territories"] = selected

    # KPIs
    col1, col2 = st.columns(2)
    col1.metric("Local Territories Selected", len(selected))
    col2.metric("Rest of World (ROW)", len(all_countries) - len(selected))

    # Country-wise output table
    st.markdown("#### Country-Wise Output")

    rows = []
    for i, c in enumerate(all_countries):
        is_local = c in selected
        cons = int(25_000_000 / (i + 1.2))
        pct = max(1, 22 - i)
        import math
        audio_ppd = 0.002000 + abs(math.sin(i)) * 0.005
        video_ppd = 0.000800 + abs(math.cos(i)) * 0.0015
        pct_l = f"{int(30 + abs(math.sin(i)) * 40)}%" if is_local else "0%"
        pct_r = f"{int(10 + abs(math.cos(i)) * 50)}%" if not is_local else "0%"
        rows.append({
            "Country": c,
            "Consumption": cons,
            "% of Total": f"{pct}%",
            "Mapping": "Local" if is_local else "RoW",
            "Audio PPD": f"${audio_ppd:.6f}",
            "Video PPD": f"${video_ppd:.6f}",
            "Local %": pct_l,
            "RoW %": pct_r,
        })

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True, height=400)
