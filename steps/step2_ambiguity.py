"""Step 2: Resolve Ambiguity — select which entities to include."""

import streamlit as st
import pandas as pd


def render_step2(data, conn, session):
    st.subheader("Step 2 — Resolve Ambiguity")
    st.caption("Select the matching entities to include in the valuation scope.")

    matches = _get_ambiguity_matches(data)

    if not matches:
        st.info("No ambiguity matches available. Go back and search for a catalogue first.")
        return

    df = pd.DataFrame(matches)
    display_cols = ["name", "track_count"]
    if "confidence" in df.columns:
        display_cols.append("confidence")

    # Show as an editable table with checkboxes
    already_selected = st.session_state.get("resolved_entities", [])
    df["Select"] = df["name"].isin(already_selected)

    edited_df = st.data_editor(
        df[["Select"] + display_cols],
        column_config={
            "Select": st.column_config.CheckboxColumn("Select", default=False),
            "name": st.column_config.TextColumn("Name"),
            "track_count": st.column_config.NumberColumn("Album Count", format="%d"),
        },
        disabled=display_cols,
        hide_index=True,
        use_container_width=True,
        key="ambiguity_editor",
    )

    # Update session state from edits
    selected_names = edited_df[edited_df["Select"]]["name"].tolist()
    st.session_state["resolved_entities"] = selected_names

    if selected_names:
        st.success(f"Selected: **{', '.join(selected_names)}**")
    else:
        st.info("Select at least one entity to continue.")


def _get_ambiguity_matches(data):
    """Pull matches from injected data, using the current search term or first available."""
    am = data.get("ambiguity_matches", {})
    search_term = st.session_state.get("search_term", "")
    if search_term and search_term in am:
        return am[search_term]
    keys = list(am.keys())
    if keys:
        return am[keys[0]]
    return []
