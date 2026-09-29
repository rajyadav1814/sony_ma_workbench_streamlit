"""Step 1: Catalog Select — search mode and text input only (no SQL queries)."""

import csv
import io

import streamlit as st


def render_step1(data, conn, session):
    st.subheader("Step 1 — Catalog Select")
    st.caption("Choose how to find your catalogue: by artist/band name, label, or ISRC list.")

    mode = st.radio(
        "Search Mode",
        options=["Artist", "Label", "ISRC List"],
        horizontal=True,
        index=["Artist", "Label", "ISRC List"].index(st.session_state.get("search_mode", "Artist")),
        key="search_mode_radio",
    )
    st.session_state["search_mode"] = mode

    if mode in ("Artist", "Label"):
        term = st.text_input(
            f"{mode} Name",
            value=st.session_state.get("search_term", ""),
            placeholder=f"Type {mode.lower()} name...",
            key="search_term_input",
        )
        if term != st.session_state.get("search_term"):
            st.session_state["search_term"] = term

    else:
        uploaded = st.file_uploader("Upload ISRC CSV", type=["csv", "txt"], key="isrc_upload")
        if uploaded is not None:
            try:
                text = uploaded.getvalue().decode("utf-8-sig")
                reader = csv.DictReader(io.StringIO(text))
                columns = reader.fieldnames or []
                if not columns:
                    raise ValueError("The CSV file has no header row.")
                isrc_col = next((column for column in columns if "isrc" in column.lower()), columns[0])
                isrc_list = [
                    value.strip()
                    for row in reader
                    if (value := str(row.get(isrc_col) or "").strip())
                ]
                st.session_state["search_term"] = f"ISRC upload ({len(isrc_list)} codes)"
                st.session_state["_isrc_list"] = isrc_list
                st.info(f"Loaded {len(isrc_list)} ISRCs from column '{isrc_col}'.")
            except Exception as e:
                st.error(f"Failed to parse CSV: {e}")
