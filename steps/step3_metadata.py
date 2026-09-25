"""Step 3: Metadata — filter and include/exclude albums."""

import streamlit as st
import pandas as pd


def render_step3(data, conn, session):
    st.subheader("Step 3 — Metadata to Include")
    st.caption("Review albums and choose which to include in the valuation scope.")

    albums = data.get("albums", [])
    if not albums:
        st.info("No album data available yet.")
        return

    df = pd.DataFrame(albums)

    # Filters
    col_search, col_year = st.columns([3, 1])
    with col_search:
        search = st.text_input("Search by Album or ISRC", key="metadata_search_input")
    with col_year:
        all_years = sorted(df["release_year"].dropna().unique().tolist(), reverse=True)
        year_filter = st.multiselect("Release Year", options=all_years, key="metadata_year_filter")

    # Apply filters for display
    filtered = df.copy()
    if search:
        mask = (
            filtered["album_name"].str.contains(search, case=False, na=False)
            | filtered.get("isrc", pd.Series(dtype=str)).fillna("").str.contains(search, case=False, na=False)
        )
        filtered = filtered[mask]
    if year_filter:
        filtered = filtered[filtered["release_year"].isin(year_filter)]

    # Add Include column
    included_map = st.session_state.get("included_albums", {})
    filtered = filtered.copy()
    filtered["Include"] = filtered["album_id"].map(lambda aid: included_map.get(aid, True))

    display_cols = ["Include", "album_name", "release_type", "release_year", "track_count", "current_revenue_usd"]
    available_cols = [c for c in display_cols if c in filtered.columns]

    edited = st.data_editor(
        filtered[available_cols],
        column_config={
            "Include": st.column_config.CheckboxColumn("Include", default=True),
            "album_name": st.column_config.TextColumn("Album"),
            "release_type": st.column_config.TextColumn("Release Type"),
            "release_year": st.column_config.NumberColumn("Year", format="%d"),
            "track_count": st.column_config.NumberColumn("Tracks", format="%d"),
            "current_revenue_usd": st.column_config.NumberColumn("Revenue (USD)", format="$%.0f"),
        },
        disabled=[c for c in available_cols if c != "Include"],
        hide_index=True,
        use_container_width=True,
        key="metadata_editor",
    )

    # Sync edits back to session
    if "Include" in edited.columns:
        for idx, row in edited.iterrows():
            aid = filtered.iloc[idx]["album_id"] if idx < len(filtered) else None
            if aid:
                st.session_state["included_albums"][aid] = bool(row["Include"])

    included_count = sum(1 for v in st.session_state["included_albums"].values() if v)
    st.metric("Albums Included", included_count)
