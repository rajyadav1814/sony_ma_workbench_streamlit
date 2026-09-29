"""Step 8: Corporate Export — summary table and Excel download."""

import io
from openpyxl import Workbook
import streamlit as st


def render_step8(data, conn, session):
    st.subheader("Step 8 — Corporate Export")
    st.caption("Review the final valuation summary and download the corporate template.")

    export = _compute_export(data)
    included = export.pop("_included")

    # KPIs
    c1, c2 = st.columns(2)
    c1.metric("Current Annual Revenue", export.get("Current Annual Revenue (USD)", ""))
    c2.metric("Local / ROW Split", f"{export.get('Local Revenue (USD)', '')} / {export.get('ROW Revenue (USD)', '')}")

    # Summary table
    summary_rows = [{"Corporate Template Field": k, "Value": str(v)} for k, v in export.items()]
    st.dataframe(summary_rows, use_container_width=True, hide_index=True, height=450)

    # Excel download
    st.markdown("#### Export")
    excel_bytes = _build_excel(export, included, data)
    catalog_name = export.get("Catalog Name", "catalog")
    fname = f"corporate_valuation_inputs_{str(catalog_name).replace(' ', '_')}.xlsx"

    st.download_button(
        label="⬇ Download Corporate Excel Template",
        data=excel_bytes,
        file_name=fname,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
    )


def _compute_export(data):
    """Build the export dictionary from current session state and data."""
    albums = data.get("albums", [])
    included_map = st.session_state.get("included_albums", {})
    included = [a for a in albums if included_map.get(a["album_id"], True)]

    market = data.get("market_growth", {})
    artist_growth = market.get("artist_growth_pct", 0)
    market_growth_pct = market.get("market_growth_pct", 0)

    local_row = data.get("local_row_revenue", {})
    age_split = data.get("catalog_age_split", {})
    local_territories = st.session_state.get("local_territories", [])
    search_term = st.session_state.get("search_term", "")
    expected_growth = st.session_state.get("expected_growth", 8.0)
    expected_decay = st.session_state.get("expected_decay", -6.0)

    total_revenue = sum(a["current_revenue_usd"] for a in included)
    total_tracks = sum(a["track_count"] for a in included)

    return {
        "Catalog Name": search_term or "Unknown",
        "Local Territories": ", ".join(local_territories),
        "Total Albums (Included)": len(included),
        "Total Tracks (Included)": total_tracks,
        "Current Annual Revenue (USD)": f"${total_revenue / 1e6:.1f}M",
        "Local Revenue (USD)": f"${local_row.get('local_revenue_usd', 0) / 1e6:.1f}M",
        "ROW Revenue (USD)": f"${local_row.get('row_revenue_usd', 0) / 1e6:.1f}M",
        "Catalog Age — Older than 10y": f"{age_split.get('older_than_10y_pct', 0)}%",
        "Catalog Age — Recent": f"{age_split.get('recent_releases_pct', 0)}%",
        "YoY Growth 2025": f"{artist_growth}%",
        "Market Growth 2025": f"{market_growth_pct}%",
        "Expected Growth Assumption": f"{expected_growth}%",
        "Expected Decay Assumption": f"{expected_decay}%",
        "_included": included,
    }


def _build_excel(export_dict, included_albums, data):
    """Generate an Excel file in memory and return bytes."""
    output = io.BytesIO()
    workbook = Workbook()
    summary_sheet = workbook.active
    summary_sheet.title = "Corporate Template Inputs"
    summary_sheet.append(["Corporate Template Field", "Value"])
    for key, value in export_dict.items():
        summary_sheet.append([key, str(value)])

    album_columns = [
        column for column in ["album_name", "release_type", "release_year", "track_count", "current_revenue_usd"]
        if any(column in album for album in included_albums)
    ]
    if included_albums:
        album_sheet = workbook.create_sheet("Album Detail")
        album_sheet.append(album_columns)
        for album in included_albums:
            album_sheet.append([album.get(column) for column in album_columns])

    release_year_rows = data.get("release_year_analysis", [])
    if release_year_rows:
        release_year_sheet = workbook.create_sheet("Release-Year Analysis")
        columns = list(release_year_rows[0])
        release_year_sheet.append(columns)
        for row in release_year_rows:
            release_year_sheet.append([row.get(column) for column in columns])

    workbook.save(output)
    return output.getvalue()
