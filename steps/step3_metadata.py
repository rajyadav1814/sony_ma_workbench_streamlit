"""Step 3: Metadata — filter and include/exclude albums."""

import streamlit as st


def render_step3(data, conn, session):
    st.subheader("Step 3 — Metadata to Include")
    st.caption("Review albums and choose which to include in the valuation scope.")

    albums = data.get("albums", [])
    if not albums:
        st.info("No album data available yet.")
        return

    # Filters
    col_search, col_year = st.columns([3, 1])
    with col_search:
        search = st.text_input("Search by Album or ISRC", key="metadata_search_input")
    with col_year:
        all_years = sorted({a.get("release_year") for a in albums if a.get("release_year") is not None}, reverse=True)
        year_filter = st.multiselect("Release Year", options=all_years, key="metadata_year_filter")

    # Apply filters for display
    filtered = albums
    if search:
        search_lower = search.casefold()
        filtered = [
            album for album in filtered
            if search_lower in str(album.get("album_name") or "").casefold()
            or search_lower in str(album.get("isrc") or "").casefold()
        ]
    if year_filter:
        filtered = [album for album in filtered if album.get("release_year") in year_filter]

    # Add Include column
    included_map = st.session_state.get("included_albums", {})
    editor_rows = [
        {
            "Include": included_map.get(album["album_id"], True),
            **{key: album.get(key) for key in ["album_name", "release_type", "release_year", "track_count", "current_revenue_usd"]},
        }
        for album in filtered
    ]

    display_cols = ["Include", "album_name", "release_type", "release_year", "track_count", "current_revenue_usd"]

    edited = st.data_editor(
        editor_rows,
        column_config={
            "Include": st.column_config.CheckboxColumn("Include", default=True),
            "album_name": st.column_config.TextColumn("Album"),
            "release_type": st.column_config.TextColumn("Release Type"),
            "release_year": st.column_config.NumberColumn("Year", format="%d"),
            "track_count": st.column_config.NumberColumn("Tracks", format="%d"),
            "current_revenue_usd": st.column_config.NumberColumn("Revenue (USD)", format="$%.0f"),
        },
        disabled=[c for c in display_cols if c != "Include"],
        hide_index=True,
        use_container_width=True,
        key="metadata_editor",
    )

    # Sync edits back to session
    for album, row in zip(filtered, edited):
        st.session_state["included_albums"][album["album_id"]] = bool(row.get("Include"))

    included_count = sum(1 for v in st.session_state["included_albums"].values() if v)
    st.metric("Albums Included", included_count)
