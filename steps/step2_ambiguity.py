"""Step 2: Resolve Ambiguity — select which entities to include."""

import streamlit as st


def render_step2(data, conn, session):
    st.subheader("Step 2 — Resolve Ambiguity")
    st.caption("Select the matching entities to include in the valuation scope.")

    matches = _get_ambiguity_matches(data)

    if not matches:
        st.info("No ambiguity matches available. Go back and search for a catalogue first.")
        return

    display_cols = ["name", "track_count"]
    if any("confidence" in match for match in matches):
        display_cols.append("confidence")

    # Show as an editable table with checkboxes
    already_selected = st.session_state.get("resolved_entities", [])
    rows = [
        {**match, "Select": match.get("name") in already_selected}
        for match in matches
    ]

    edited_df = st.data_editor(
        [{key: row.get(key) for key in ["Select"] + display_cols} for row in rows],
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
    selected_names = [row["name"] for row in edited_df if row.get("Select")]
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
