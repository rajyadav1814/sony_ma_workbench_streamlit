"""Step 5: Catalog Analytics — KPIs, tabbed charts."""

import streamlit as st
import altair as alt


def _melt_records(rows, value_columns):
    return [
        {"bucket": row.get("bucket"), "Series": column, "Value": row.get(column)}
        for row in rows
        for column in value_columns
    ]


def render_step5(data, conn, session):
    st.subheader("Step 5 — Catalog Analytics")

    market = data.get("market_growth", {})
    age_split = data.get("catalog_age_split", {})
    artist_growth = market.get("artist_growth_pct", 0)
    market_growth = market.get("market_growth_pct", 0)

    # KPIs
    c1, c2, c3 = st.columns(3)
    c1.metric("Catalog from Releases older 10Years", f"{age_split.get('older_than_10y_pct', 0)}%")
    c2.metric("Catalog from last 5 years Releases", f"{age_split.get('recent_releases_pct', 0)}%")
    c3.metric("Artist Growth", f"{artist_growth}%")

    # Tabbed charts
    matrix = data.get("consumption_matrix", [])
    growth_trend = data.get("growth_trend", [])

    tabs = st.tabs(["All", "Audio", "Video", "Premium", "Ad Supported", "Growth Trend"])

    if matrix:
        with tabs[0]:
            # Multi-line chart for all series
            melted = _melt_records(matrix, ["audio_premium", "audio_ad_supported", "video_premium", "video_ad_supported"])
            color_scale = alt.Scale(
                domain=["audio_premium", "audio_ad_supported", "video_premium", "video_ad_supported"],
                range=["#E1261C", "#8A8A8A", "#2A63C7", "#B9861F"]
            )
            chart = alt.Chart(melted).mark_line(point=True).encode(
                x=alt.X("bucket:N", title="Period"),
                y=alt.Y("Value:Q", title="Streams"),
                color=alt.Color("Series:N", scale=color_scale),
            ).properties(height=320)
            st.altair_chart(chart, use_container_width=True)

        with tabs[1]:
            melted = _melt_records(matrix, ["audio_premium", "audio_ad_supported"])
            chart = alt.Chart(melted).mark_bar().encode(
                x=alt.X("bucket:N", title="Period"),
                y=alt.Y("Value:Q", title="Streams", stack="zero"),
                color=alt.Color("Series:N", scale=alt.Scale(range=["#E1261C", "#8A8A8A"])),
            ).properties(height=280)
            st.altair_chart(chart, use_container_width=True)

        with tabs[2]:
            melted = _melt_records(matrix, ["video_premium", "video_ad_supported"])
            chart = alt.Chart(melted).mark_bar().encode(
                x=alt.X("bucket:N", title="Period"),
                y=alt.Y("Value:Q", title="Streams", stack="zero"),
                color=alt.Color("Series:N", scale=alt.Scale(range=["#2A63C7", "#8A8A8A"])),
            ).properties(height=280)
            st.altair_chart(chart, use_container_width=True)

        with tabs[3]:
            melted = _melt_records(matrix, ["audio_premium", "video_premium"])
            chart = alt.Chart(melted).mark_bar().encode(
                x=alt.X("bucket:N", title="Period"),
                y=alt.Y("Value:Q", title="Streams"),
                color=alt.Color("Series:N", scale=alt.Scale(range=["#E1261C", "#2A63C7"])),
                xOffset="Series:N",
            ).properties(height=280)
            st.altair_chart(chart, use_container_width=True)

        with tabs[4]:
            melted = _melt_records(matrix, ["audio_ad_supported", "video_ad_supported"])
            chart = alt.Chart(melted).mark_bar().encode(
                x=alt.X("bucket:N", title="Period"),
                y=alt.Y("Value:Q", title="Streams"),
                color=alt.Color("Series:N", scale=alt.Scale(range=["#B9861F", "#8A8A8A"])),
                xOffset="Series:N",
            ).properties(height=280)
            st.altair_chart(chart, use_container_width=True)

    with tabs[5]:
        if growth_trend:
            chart = alt.Chart(growth_trend).mark_line(point=True, color="#E1261C").encode(
                x=alt.X("year:O", title="Year"),
                y=alt.Y("yoy_growth_pct:Q", title="YoY Growth %"),
            ).properties(height=280)
            st.altair_chart(chart, use_container_width=True)

            st.markdown(
                f"**Market Growth Comparison:** Artist Growth **{artist_growth}%** vs "
                f"Market Growth **{market_growth}%**"
            )
        else:
            st.info("No growth trend data available.")
