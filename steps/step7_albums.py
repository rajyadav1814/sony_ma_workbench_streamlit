"""Step 7: Album Analysis — included albums chart and table."""

import streamlit as st
import altair as alt


def render_step7(data, conn, session):
    st.subheader("Step 7 — Album Analysis")

    albums = data.get("albums", [])
    if not albums:
        st.info("No album data available.")
        return

    included_map = st.session_state.get("included_albums", {})
    records = [
        {**album, "Status": "Include" if included_map.get(album["album_id"], True) else "Exclude"}
        for album in albums
    ]

    # Filters
    col_filter, col_year = st.columns([1, 1])
    with col_filter:
        filter_val = st.selectbox("Filter", options=["All", "Include", "Exclude"], key="album_filter_select")
    with col_year:
        all_years = sorted({row.get("release_year") for row in records if row.get("release_year") is not None}, reverse=True)
        year_filter = st.multiselect("Release Year", options=all_years, key="album_year_ms")

    view = records
    if filter_val != "All":
        view = [row for row in view if row["Status"] == filter_val]
    if year_filter:
        view = [row for row in view if row.get("release_year") in year_filter]

    # KPIs
    included = [row for row in records if row["Status"] == "Include"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Albums in Scope", len(included))
    c2.metric("Total Tracks", sum(int(row.get("track_count") or 0) for row in included))
    total_cons = sum(row.get("total_consumption_streams", 0) or 0 for row in included)
    c3.metric("Total Consumption", f"{total_cons / 1e6:.1f}M")
    c4.metric("Total Revenue", f"${sum(row.get('current_revenue_usd', 0) or 0 for row in included) / 1e6:.1f}M")

    # Table
    display_cols = ["album_name", "release_type", "release_year", "track_count", "current_revenue_usd", "Status"]
    if any("total_consumption_streams" in row for row in view):
        display_cols.insert(4, "total_consumption_streams")

    st.dataframe(
        [{
            output_name: row.get(input_name)
            for input_name, output_name in {
                "album_name": "Album", "release_type": "Type", "release_year": "Year",
                "track_count": "Tracks", "total_consumption_streams": "Streams",
                "current_revenue_usd": "Revenue (USD)", "Status": "Status",
            }.items()
            if input_name in display_cols
        } for row in view],
        use_container_width=True,
        hide_index=True,
        height=350,
    )

    # Chart
    st.markdown("#### Album Analysis Chart (Included)")
    chart_tab = st.radio("Metric", ["Revenue", "Consumption"], horizontal=True, key="album_chart_metric")

    sort_col = "current_revenue_usd" if chart_tab == "Revenue" else "total_consumption_streams"
    if not any(sort_col in row for row in included):
        sort_col = "current_revenue_usd"

    sorted_inc = sorted(included, key=lambda row: row.get(sort_col) or 0, reverse=True)[:20]

    if chart_tab == "Revenue":
        chart = alt.Chart(sorted_inc).mark_bar(color="#E1261C").encode(
            y=alt.Y("album_name:N", sort="-x", title=""),
            x=alt.X("current_revenue_usd:Q", title="Revenue (USD)"),
        ).properties(height=max(280, len(sorted_inc) * 22 + 60))
    else:
        x_col = "total_consumption_streams" if any("total_consumption_streams" in row for row in sorted_inc) else "current_revenue_usd"
        chart = alt.Chart(sorted_inc).mark_bar(color="#2A63C7").encode(
            y=alt.Y("album_name:N", sort="-x", title=""),
            x=alt.X(f"{x_col}:Q", title="Streams"),
        ).properties(height=max(280, len(sorted_inc) * 22 + 60))

    st.altair_chart(chart, use_container_width=True)
