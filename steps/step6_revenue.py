"""Step 6: Revenue & PPD — release-year analysis with charts."""

import streamlit as st
import altair as alt


def render_step6(data, conn, session):
    st.subheader("Step 6 — Revenue & PPD")

    local_row = data.get("local_row_revenue", {})
    col1, col2 = st.columns(2)
    col1.metric("Local Revenue", _fmt_usd(local_row.get("local_revenue_usd", 0)))
    col2.metric("ROW Revenue", _fmt_usd(local_row.get("row_revenue_usd", 0)))

    # Release year analysis
    ry = data.get("release_year_analysis", [])
    if not ry:
        st.info("No release-year analysis data available.")
        return

    # Year range filter
    col_from, col_to = st.columns(2)
    all_years = sorted(row["bucket"] for row in ry)
    with col_from:
        from_year = st.selectbox("From", options=[None] + all_years, index=0, key="ry_from")
    with col_to:
        to_year = st.selectbox("To", options=[None] + all_years, index=0, key="ry_to")

    if from_year:
        ry = [row for row in ry if row["bucket"] >= from_year]
    if to_year:
        ry = [row for row in ry if row["bucket"] <= to_year]

    # Tabbed charts
    tab_cons, tab_rev, tab_growth = st.tabs(["Consumption", "Revenue", "Growth"])

    with tab_cons:
        chart = alt.Chart(ry).mark_bar(color="#E1261C").encode(
            x=alt.X("bucket:N", title="Year"),
            y=alt.Y("consumption_streams:Q", title="Streams"),
        ).properties(height=260)
        st.altair_chart(chart, use_container_width=True)

    with tab_rev:
        chart = alt.Chart(ry).mark_bar(color="#2A63C7").encode(
            x=alt.X("bucket:N", title="Year"),
            y=alt.Y("revenue_usd:Q", title="Revenue (USD)"),
        ).properties(height=260)
        st.altair_chart(chart, use_container_width=True)

    with tab_growth:
        chart = alt.Chart(ry).mark_bar(color="#1E9E5A").encode(
            x=alt.X("bucket:N", title="Year"),
            y=alt.Y("yoy_growth_pct:Q", title="YoY Growth %"),
        ).properties(height=260)
        st.altair_chart(chart, use_container_width=True)

    # Data table
    st.dataframe(
        [{
            "Year": row.get("bucket"),
            "Consumption": row.get("consumption_streams"),
            "Revenue (USD)": row.get("revenue_usd"),
            "YoY Growth %": row.get("yoy_growth_pct"),
        } for row in ry],
        use_container_width=True,
        hide_index=True,
    )

    # PPD splits
    ppd = data.get("ppd", {})
    if ppd:
        st.markdown("#### PPD Splits")
        rows = []
        for k, v in ppd.get("current_splits", {}).items():
            rows.append({"Type": "Current", "Segment": k, "PPD (USD)": f"${v:.4f}"})
        for k, v in ppd.get("future_splits", {}).items():
            rows.append({"Type": "Future-State", "Segment": k, "PPD (USD)": f"${v:.4f}"})
        st.dataframe(rows, use_container_width=True, hide_index=True)


def _fmt_usd(v):
    m = v / 1_000_000
    return f"${m:.1f}M"
