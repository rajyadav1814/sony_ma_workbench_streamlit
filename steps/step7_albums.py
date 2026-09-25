"""Step 7: Album Analysis — included albums chart and table."""

import streamlit as st
import pandas as pd
import altair as alt


def render_step7(data, conn, session):
    st.subheader("Step 7 — Album Analysis")

    albums = data.get("albums", [])
    if not albums:
        st.info("No album data available.")
        return

    df = pd.DataFrame(albums)
    included_map = st.session_state.get("included_albums", {})
    df["Status"] = df["album_id"].map(lambda aid: "Include" if included_map.get(aid, True) else "Exclude")

    # Filters
    col_filter, col_year = st.columns([1, 1])
    with col_filter:
        filter_val = st.selectbox("Filter", options=["All", "Include", "Exclude"], key="album_filter_select")
    with col_year:
        all_years = sorted(df["release_year"].dropna().unique().tolist(), reverse=True)
        year_filter = st.multiselect("Release Year", options=all_years, key="album_year_ms")

    view = df.copy()
    if filter_val != "All":
        view = view[view["Status"] == filter_val]
    if year_filter:
        view = view[view["release_year"].isin(year_filter)]

    # KPIs
    included = df[df["Status"] == "Include"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Albums in Scope", len(included))
    c2.metric("Total Tracks", int(included["track_count"].sum()))
    total_cons = included["total_consumption_streams"].sum() if "total_consumption_streams" in included.columns else 0
    c3.metric("Total Consumption", f"{total_cons / 1e6:.1f}M")
    c4.metric("Total Revenue", f"${included['current_revenue_usd'].sum() / 1e6:.1f}M")

    # Table
    display_cols = ["album_name", "release_type", "release_year", "track_count", "current_revenue_usd", "Status"]
    if "total_consumption_streams" in view.columns:
        display_cols.insert(4, "total_consumption_streams")

    st.dataframe(
        view[[c for c in display_cols if c in view.columns]].rename(columns={
            "album_name": "Album", "release_type": "Type", "release_year": "Year",
            "track_count": "Tracks", "total_consumption_streams": "Streams",
            "current_revenue_usd": "Revenue (USD)", "Status": "Status",
        }),
        use_container_width=True,
        hide_index=True,
        height=350,
    )

    # Chart
    st.markdown("#### Album Analysis Chart (Included)")
    chart_tab = st.radio("Metric", ["Revenue", "Consumption"], horizontal=True, key="album_chart_metric")

    sort_col = "current_revenue_usd" if chart_tab == "Revenue" else "total_consumption_streams"
    if sort_col not in included.columns:
        sort_col = "current_revenue_usd"

    sorted_inc = included.sort_values(sort_col, ascending=False).head(20)

    if chart_tab == "Revenue":
        chart = alt.Chart(sorted_inc).mark_bar(color="#E1261C").encode(
            y=alt.Y("album_name:N", sort="-x", title=""),
            x=alt.X("current_revenue_usd:Q", title="Revenue (USD)"),
        ).properties(height=max(280, len(sorted_inc) * 22 + 60))
    else:
        x_col = "total_consumption_streams" if "total_consumption_streams" in sorted_inc.columns else "current_revenue_usd"
        chart = alt.Chart(sorted_inc).mark_bar(color="#2A63C7").encode(
            y=alt.Y("album_name:N", sort="-x", title=""),
            x=alt.X(f"{x_col}:Q", title="Streams"),
        ).properties(height=max(280, len(sorted_inc) * 22 + 60))

    st.altair_chart(chart, use_container_width=True)
