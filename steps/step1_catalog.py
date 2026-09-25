"""Step 1: Catalog Select — search mode and text input only (no SQL queries)."""

import streamlit as st
import pandas as pd


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
                df = pd.read_csv(uploaded)
                isrc_col = None
                for c in df.columns:
                    if "isrc" in c.lower():
                        isrc_col = c
                        break
                if isrc_col is None:
                    isrc_col = df.columns[0]
                isrc_list = df[isrc_col].dropna().astype(str).tolist()
                st.session_state["search_term"] = f"ISRC upload ({len(isrc_list)} codes)"
                st.session_state["_isrc_list"] = isrc_list
                st.info(f"Loaded {len(isrc_list)} ISRCs from column '{isrc_col}'.")
            except Exception as e:
                st.error(f"Failed to parse CSV: {e}")
