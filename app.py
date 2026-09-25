"""
Sony Music — M&A Catalogue Valuation Workbench
Streamlit host shell: auth gate, data loading, HTML workbench rendering.
"""

import os
import json
import base64
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from config import DB, SCHEMA, MAX_STEP, MIN_STEP, STEP_LABELS
from session_manager import (
    is_valid_email,
    clamp_step,
    ensure_session_tables,
    get_open_session,
    create_new_session,
    save_checkpoint,
    abandon_open_sessions,
)
from data_loader import load_data_from_postgres, search_catalog, create_isrc_temp_table, compute_analytics_from_monthly_detail, load_bobwa_consumption_matrix, load_bobwa_ppd, search_artists_dropdown, search_labels_dropdown, load_available_years
from catalog_builder import create_step1_selection_table, create_catalog_table, create_step2_table, pull_monthly_detail
from postgres_connection import PostgresConnection

# ─── Page config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Sony Music | M&A Catalog Valuation Workbench",
    page_icon="🎵",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Hide Streamlit default furniture for full-bleed HTML + proper spinner overlay
st.markdown(
    """<style>
    .stMainBlockContainer { padding: 0 !important; max-width: 100% !important; }
    header[data-testid="stHeader"] { display: none !important; }
    footer { display: none !important; }
    .stDeployButton { display: none !important; }
    #MainMenu { display: none !important; }
    html, body { height: auto !important; overflow-x: hidden !important; overflow-y: auto !important; background: #F1EFE7 !important; }
    .stApp { height: auto !important; overflow-x: hidden !important; overflow-y: visible !important; background: #F1EFE7 !important; }
    [data-testid="stAppViewContainer"] { height: auto !important; overflow: visible !important; }
    section[data-testid="stMain"] { height: auto !important; overflow: visible !important; }
    .stMainBlockContainer, [data-testid="stMainBlockContainer"] { height: auto !important; overflow: visible !important; }

    /* Hide Streamlit's default connection error dialog */
    [data-testid="stConnectionStatus"],
    .stConnectionStatus,
    div[class*="ConnectionStatus"],
    div[kind="error"][class*="stAlert"],
    .stException {
        display: none !important;
    }

    [data-testid="stDialogOverlay"],
    .stDialogOverlay,
    [data-baseweb="modal"] {
        display: none !important;
    }

    /* Custom connection error popup */
    .wb-connection-error-overlay {
        display: none !important;
        position: fixed;
        top: 0; left: 0; right: 0; bottom: 0;
        background: rgba(0, 0, 0, 0.5);
        backdrop-filter: blur(4px);
        z-index: 999999;
        display: flex;
        align-items: center;
        justify-content: center;
        animation: fadeIn 0.2s ease;
    }
    @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
    .wb-connection-error-card {
        background: #ffffff;
        border-radius: 16px;
        padding: 40px 36px;
        max-width: 440px;
        width: 90%;
        box-shadow: 0 20px 60px rgba(0, 0, 0, 0.15);
        text-align: center;
        animation: slideUp 0.3s ease;
    }
    @keyframes slideUp { from { transform: translateY(20px); opacity: 0; } to { transform: translateY(0); opacity: 1; } }
    .wb-connection-error-card .error-icon {
        width: 56px; height: 56px;
        margin: 0 auto 16px;
        background: #FEF2F2;
        border-radius: 50%;
        display: flex; align-items: center; justify-content: center;
        font-size: 24px;
    }
    .wb-connection-error-card h3 { font-size: 1.25rem; font-weight: 700; color: #111827; margin: 0 0 8px 0; }
    .wb-connection-error-card p { font-size: 0.9rem; color: #6b7280; margin: 0 0 24px 0; line-height: 1.5; }
    .wb-connection-error-card button {
        background: #3b5de7; color: #fff; border: none; border-radius: 8px;
        padding: 12px 32px; font-size: 0.9rem; font-weight: 600; cursor: pointer;
    }
    .wb-connection-error-card button:hover { background: #2d4ad0; }

    /* Hide ALL Streamlit skeleton/loading/stale placeholders */
    [data-testid="stSkeleton"],
    .stSkeleton,
    [class*="skeleton"],
    [class*="Skeleton"],
    .element-container:has([data-testid="stSkeleton"]),
    .stale-element,
    [data-stale="true"],
    div[data-testid="element-container"] > div[style*="skeleton"],
    .glideDataEditor {
        display: none !important;
        visibility: hidden !important;
        height: 0 !important;
        overflow: hidden !important;
        opacity: 0 !important;
    }

    /* Keep a visible handoff while the workbench iframe is rebuilt. */
    [data-testid="stComponentLoading"] {
        display: flex !important;
        visibility: visible !important;
        position: fixed !important;
        inset: 0 !important;
        z-index: 999997 !important;
        align-items: center !important;
        justify-content: center !important;
        height: auto !important;
        min-height: 100vh !important;
        overflow: visible !important;
        opacity: 1 !important;
        background: #F1EFE7 !important;
    }
    [data-testid="stComponentLoading"]::before {
        content: "";
        width: 34px;
        height: 34px;
        border: 4px solid #E5E1D8;
        border-top-color: #E1261C;
        border-radius: 50%;
        animation: wb-build-spin .8s linear infinite;
    }

    iframe[title*="streamlit"] {
        background: transparent !important;
        opacity: 1 !important;
        filter: none !important;
    }
    [data-testid="stAppViewContainer"],
    [data-testid="stMainBlockContainer"],
    section[data-testid="stMain"] {
        opacity: 1 !important;
        filter: none !important;
    }

    /* Keep catalog-build feedback visible while Streamlit recreates the iframe. */
    .wb-build-loader {
        position: fixed;
        inset: 0;
        z-index: 999998;
        display: flex;
        align-items: center;
        justify-content: center;
        background: #F1EFE7;
    }
    .wb-build-loader__card {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 16px;
        min-width: 280px;
        padding: 32px 42px;
        border: 1px solid rgba(20, 18, 14, 0.12);
        border-radius: 14px;
        background: #fff;
        box-shadow: 0 14px 34px rgba(20, 18, 14, 0.14);
        color: #141210;
        font: 600 15px Inter, Arial, sans-serif;
    }
    .wb-build-loader__spinner {
        width: 34px;
        height: 34px;
        border: 4px solid #E5E1D8;
        border-top-color: #E1261C;
        border-radius: 50%;
        animation: wb-build-spin .8s linear infinite;
    }
    @keyframes wb-build-spin { to { transform: rotate(360deg); } }

    </style>""",
    unsafe_allow_html=True,
)

# ─── Resolve app directory (so we can read html/ partials) ───────────────────
APP_DIR = Path(__file__).resolve().parent

# ─── PostgreSQL connection ──────────────────────────────────────────────────
conn = PostgresConnection()
session = conn.session()

if "_session_tables_checked" not in st.session_state:
    try:
        ensure_session_tables(session)
    except Exception:
        pass
    st.session_state["_session_tables_checked"] = True

# ─── Restore session from query params (after JS-triggered reload) ────────────
_params = st.query_params

if _params.get("wb_logout") == "1":
    for key in list(st.session_state.keys()):
        if key != "_session_tables_checked":
            del st.session_state[key]
    for k in list(st.query_params.keys()):
        if k.startswith("wb_"):
            del st.query_params[k]
    st.rerun()

if _params.get("wb_action") == "move_resume":
    _email = st.session_state.get("user_email", "") or _params.get("wb_email", "")
    from session_manager import get_open_sessions as _get_open_sessions
    open_sessions = _get_open_sessions(session, _email) if _email else []
    for key in list(st.session_state.keys()):
        if key not in ("user_email", "_session_tables_checked"):
            del st.session_state[key]
    if _email:
        st.session_state["user_email"] = _email
    if open_sessions:
        st.session_state["_pending_resume_list"] = open_sessions
        st.session_state["_pending_resume"] = open_sessions[0]
    st.session_state["_force_resume"] = True
    for k in list(st.query_params.keys()):
        if k.startswith("wb_"):
            del st.query_params[k]
    st.rerun()

_do_reset = _params.get("wb_reset") == "1" or st.session_state.get("_reset_pending")
if _do_reset:
    _email = st.session_state.get("user_email", "")
    for key in list(st.session_state.keys()):
        if key not in ("user_email", "welcomed", "_session_tables_checked"):
            del st.session_state[key]
    if _email:
        new_sess = create_new_session(session, _email)
        st.session_state["session_id"] = new_sess["session_id"]
        st.session_state["current_step"] = 1
        st.session_state["step_data"] = {}
    else:
        st.session_state["current_step"] = 1
        st.session_state["step_data"] = {}
    for k in list(st.query_params.keys()):
        if k.startswith("wb_"):
            del st.query_params[k]
    st.rerun()

if "wb_email" in _params and not st.session_state.get("user_email"):
    st.session_state["user_email"] = _params["wb_email"]
    st.session_state["welcomed"] = True
if "wb_session_id" in _params and "session_id" not in st.session_state:
    st.session_state["session_id"] = _params["wb_session_id"]
if "wb_step" in _params:
    st.session_state["current_step"] = clamp_step(int(_params["wb_step"]))

# ─── Auth gate ───────────────────────────────────────────────────────────────
if not st.session_state.get("user_email"):
    from steps.welcome import render_welcome_screen
    render_welcome_screen(session)
    st.stop()

if (
    "_pending_resume" in st.session_state
    or "_pending_resume_list" in st.session_state
    or st.session_state.get("_force_resume")
) and "welcomed" not in st.session_state:
    from steps.welcome import render_resume_screen
    render_resume_screen(session)
    st.stop()

if "session_id" not in st.session_state:
    new_sess = create_new_session(session, st.session_state["user_email"])
    st.session_state["welcomed"] = True
    st.session_state["session_id"] = new_sess["session_id"]
    st.session_state["current_step"] = new_sess["current_step"]
    st.session_state["step_data"] = new_sess.get("step_data", {})
    # The welcome submit already triggers a rerun. Only request another one
    # when this initialization happened during a non-login browser load.
    if not st.session_state.pop("_login_transition", False):
        st.rerun()

# ─── Read query params for JS → Python communication ────────────────────────
params = st.query_params
wb_step_payload = {}

if "wb_step" in params:
    new_step = clamp_step(int(params["wb_step"]))
    st.session_state["current_step"] = new_step
    _wb_sd = params.get("wb_step_data", "")
    if _wb_sd:
        try:
            _parsed_sd = json.loads(_wb_sd)
            if isinstance(_parsed_sd, dict):
                wb_step_payload = _parsed_sd
        except (json.JSONDecodeError, TypeError):
            pass

    if wb_step_payload:
        step_data = dict(st.session_state.get("step_data", {}))
        step_data.update(wb_step_payload)
        # Keep the server checkpoint compatible with both older and newer UI payloads.
        entities = step_data.get("resolvedEntities") or step_data.get("confirmed_mrelg_ids") or step_data.get("entities")
        if entities is not None:
            step_data["resolvedEntities"] = entities
            step_data["confirmed_mrelg_ids"] = entities
        st.session_state["step_data"] = step_data
        save_checkpoint(
            session,
            st.session_state["session_id"],
            new_step,
            step_data,
        )
        if new_step >= MAX_STEP:
            from session_manager import complete_session
            complete_session(session, st.session_state["session_id"])

wb_search_term = params.get("wb_search_term", "")
wb_search_mode = params.get("wb_search_mode", "Artist")
wb_dropdown_search = params.get("wb_dropdown_search", "")
wb_dropdown_mode = params.get("wb_dropdown_mode", wb_search_mode)
wb_isrc_file = params.get("wb_isrc_file", "")
wb_isrc_filename = params.get("wb_isrc_filename", "")

# Step 2 → 3 triggers a host reload so Python can create the catalog table.
# Render this outside the iframe before database work to avoid a blank screen.
_catalog_build_requested = (
    params.get("wb_create_table") == "1"
    and params.get("wb_step2_created") != "1"
)
_step2_navigation_requested = (
    params.get("wb_step") == "2"
    and not _catalog_build_requested
)
_step_navigation_requested = (
    params.get("wb_step") in {str(step) for step in range(MIN_STEP, MAX_STEP + 1)}
    and not _catalog_build_requested
)
_login_transition_requested = st.session_state.get("_login_transition", False)
_catalog_build_loader = st.empty()
if _catalog_build_requested or _step_navigation_requested or _login_transition_requested:
    if _catalog_build_requested:
        _loader_title = "Building catalog…"
    elif _step_navigation_requested and params.get("wb_step") == "2":
        _loader_title = "Loading matching catalogues…"
    elif _step_navigation_requested:
        _loader_title = f"Loading Step {params.get('wb_step')}…"
    else:
        _loader_title = "Loading workbench…"
    _catalog_build_loader.markdown(
        f"""
        <div id="wb-navigation-loader" class="wb-build-loader" role="status" aria-live="polite">
          <div class="wb-build-loader__card">
            <div class="wb-build-loader__spinner" aria-hidden="true"></div>
            <div>{_loader_title}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ─── Load all data & compute (wrapped in spinner for loading feedback) ────────
# Most functions use @st.cache_data so subsequent reloads are fast (cache hit).
with st.container():
    try:
        injected_data = load_data_from_postgres(conn)
    except Exception:
        injected_data = {"albums": [], "ambiguity_matches": {}, "tracks": [], "track_album_bridge": [],
                         "consumption_matrix": [], "growth_trend": [], "release_year_analysis": [],
                         "new_release_tracks": [], "catalog_options": {"artists": [], "labels": []},
                         "territories": {"countries": ["United States", "Mexico", "Colombia"],
                                         "regions": {"Latin America": ["Mexico", "Colombia"],
                                                     "North America": ["United States"]}}}

    # Cache the latest live matches in the active Streamlit session. The Step 1
    # → Step 2 navigation reloads the host, so this guarantees the rows remain
    # available to the freshly created workbench iframe.
    _live_match_cache = st.session_state.get("_live_ambiguity_matches", {})
    if not isinstance(_live_match_cache, dict):
        _live_match_cache = {}
    if wb_search_term and wb_search_term.strip():
        _live_search_key = wb_search_term.strip()
        try:
            live_results = search_catalog(conn, wb_search_mode, _live_search_key)
            if live_results:
                _live_match_cache[_live_search_key] = live_results
                st.session_state["_live_ambiguity_matches"] = _live_match_cache
        except Exception:
            pass
    if _live_match_cache:
        injected_data["ambiguity_matches"].update(_live_match_cache)

    _dropdown_term = wb_dropdown_search.strip() if wb_dropdown_search else wb_search_term.strip()
    _dropdown_mode = wb_dropdown_mode if wb_dropdown_search else wb_search_mode
    if _dropdown_term and len(_dropdown_term) >= 2:
        try:
            if _dropdown_mode == "Label":
                injected_data["dropdown_results"] = search_labels_dropdown(conn, _dropdown_term)
            else:
                injected_data["dropdown_results"] = search_artists_dropdown(conn, _dropdown_term)
        except Exception:
            injected_data["dropdown_results"] = []
    else:
        injected_data["dropdown_results"] = []

    if wb_isrc_file and wb_isrc_filename:
        try:
            csv_bytes = base64.b64decode(wb_isrc_file)
            user_email = st.session_state.get("user_email", "unknown")
            temp_table = create_isrc_temp_table(conn, csv_bytes, user_email, wb_isrc_filename)
            st.session_state["_isrc_temp_table"] = temp_table
        except Exception:
            pass

    user_email = st.session_state.get("user_email", "")
    catalog_created = False

    current_wb_step = int(params.get("wb_step", "0"))
    _sid = st.session_state.get("session_id", params.get("wb_session_id", ""))
    _search_term = ""
    _search_mode = "Artist"
    wb_step_data_raw = params.get("wb_step_data", "")
    if wb_step_payload:
        _search_term = wb_step_payload.get("searchTerm", "")
        _search_mode = wb_step_payload.get("searchMode", "Artist")
    if not _search_term:
        _search_term = params.get("wb_search_term", "catalog")

    _selected_entities = []
    if wb_step_payload:
        _selected_entities = (
            wb_step_payload.get("confirmed_mrelg_ids")
            or wb_step_payload.get("resolvedEntities")
            or wb_step_payload.get("entities")
            or []
        )

    if current_wb_step >= 2 and params.get("wb_create_table") == "1" and params.get("wb_step2_created") != "1":
        # Native Streamlit status is supported by both local and hosted
        # deployments, unlike a manually injected HTML overlay.
        with st.spinner("Building catalog…", show_time=True):
            st.session_state["_table_creation_error"] = ""
            if not _search_term or not _sid:
                st.session_state["_table_creation_error"] = "Catalog creation is missing the search term or session ID. Please return to Step 1 and try again."
            else:
                try:
                    step1_result = None
                    if _selected_entities:
                        step1_result = create_step1_selection_table(session, _search_term, user_email, _selected_entities, search_mode=_search_mode, session_id=_sid)
                    else:
                        # Fallback: if no entities selected but we have a search term, use it as the entity.
                        step1_result = create_step1_selection_table(session, _search_term, user_email, [_search_term], search_mode=_search_mode, session_id=_sid)
                    if step1_result and step1_result["status"] == "success" and step1_result.get("row_count", 0) > 0:
                        step1_table = step1_result["table_name"]
                        st.session_state["_step1_table_name"] = step1_table
                        step2_table = create_step2_table(session, step1_table, _selected_entities, user_email, _search_term, session_id=_sid)
                        st.session_state["_catalog_table_name"] = step2_table
                        catalog_created = True
                        st.query_params.update({"wb_step2_created": "1", "wb_step2_table": step2_table})
                    elif step1_result and step1_result.get("status") == "error":
                        st.session_state["_table_creation_error"] = step1_result.get("error", "Step 1 table creation failed.")
                    else:
                        st.session_state["_table_creation_error"] = "Step 1 table was created but contains no matching catalog records."
                except Exception as e:
                    st.session_state["_table_creation_error"] = str(e)
    elif params.get("wb_step2_created") == "1":
        catalog_created = True
        if not st.session_state.get("_catalog_table_name"):
            st.session_state["_catalog_table_name"] = params.get("wb_step2_table", "")

    step2_table_name = st.session_state.get("_catalog_table_name", "") or params.get("wb_step2_table", "")
    if step2_table_name and (params.get("wb_step2_created") == "1" or catalog_created or st.session_state.get("_catalog_table_name")):
        try:
            step2_df = session.sql(f"""
                SELECT *
                FROM {step2_table_name}
                ORDER BY TITLE
            """).collect()
            injected_data["albums"] = []
            for r in step2_df:
                r = {str(key).upper(): value for key, value in dict(r).items()}
                ry = 0
                if r["RELEASE_YEAR"] is not None:
                    try:
                        ry = int(r["RELEASE_YEAR"])
                    except (ValueError, TypeError):
                        ry = 0
                if ry == 0:
                    try:
                        rd = str(r["RELEASE_DATE"] or "")
                        # Strip extra quotes from Luminate data
                        rd = rd.strip('"').strip("'")
                        ry = int(rd[:4]) if len(rd) >= 4 and rd[:4].isdigit() else 0
                    except (ValueError, TypeError, KeyError):
                        ry = 0
                injected_data["albums"].append({
                    "album_id": str(r["MRELG_ID"]),
                    "album_name": str(r["TITLE"] or ""),
                    "display_artist": str(r["DISPLAY_ARTIST"] or ""),
                    "release_type": str(r["RELEASE_TYPE"] or ""),
                    "release_year": ry,
                    "track_count": 0,
                    "total_consumption_streams": 0,
                    "current_revenue_usd": 0,
                    "isrc": "",
                    "imprint": str(r["IMPRINT"] or ""),
                    "product_format": str(r["PRODUCT_FORMAT"] or ""),
                })
        except Exception as e:
            st.session_state["_album_load_error"] = str(e)

    # Compute analytics — uses @st.cache_data, pass albums as JSON string for hashability
    if step2_table_name and params.get("wb_step2_created") == "1" and injected_data.get("albums"):
        try:
            albums_json = json.dumps(injected_data["albums"], default=str)
            computed = compute_analytics_from_monthly_detail(session, step2_table_name, albums_json)
            if computed:
                for key in ("territories", "consumption_matrix", "growth_trend",
                            "market_growth", "catalog_age_split", "release_year_analysis",
                            "local_row_revenue", "ppd", "new_release_tracks", "albums",
                            "release_year_consumption", "release_year_consumption_segments"):
                    if key in computed:
                        injected_data[key] = computed[key]
        except Exception:
            try:
                from data_loader import _compute_from_album_metadata
                from datetime import datetime
                fallback = _compute_from_album_metadata(injected_data["albums"], datetime.now().year)
                if fallback:
                    for key in ("territories", "consumption_matrix", "growth_trend",
                                "market_growth", "catalog_age_split", "release_year_analysis",
                                "local_row_revenue", "ppd", "new_release_tracks", "albums",
                                "release_year_consumption", "release_year_consumption_segments"):
                        if key in fallback:
                            injected_data[key] = fallback[key]
            except Exception:
                pass

    # BOBWA data — now @st.cache_data cached
    try:
        bobwa_matrix = load_bobwa_consumption_matrix(session)
        if bobwa_matrix:
            injected_data["consumption_matrix"] = bobwa_matrix
    except Exception:
        pass

    try:
        bobwa_ppd = load_bobwa_ppd(session)
        if bobwa_ppd:
            injected_data["ppd"] = {
                "current_splits": bobwa_ppd["current_splits"],
                "future_splits": bobwa_ppd["future_splits"],
            }
            injected_data["ppd_by_year"] = bobwa_ppd.get("ppd_by_year", [])
            injected_data["ppd_by_country"] = bobwa_ppd.get("ppd_by_country", [])
    except Exception:
        pass

    # Available years from MONTHLY_MR_SUMMARY for year filters
    try:
        available_years = load_available_years(session)
        if available_years:
            injected_data["available_years"] = available_years
    except Exception:
        pass

    # Debug info for troubleshooting step 2→3 data flow
    injected_data["_debug"] = {
        "step2_table_name": st.session_state.get("_catalog_table_name", ""),
        "wb_step2_created": params.get("wb_step2_created", ""),
        "catalog_created": catalog_created,
        "album_count": len(injected_data.get("albums", [])),
        "table_creation_error": st.session_state.get("_table_creation_error", ""),
        "album_load_error": st.session_state.get("_album_load_error", ""),
        "selected_entities": _selected_entities[:5] if _selected_entities else [],
        "search_term": _search_term,
        "current_wb_step": current_wb_step,
    }

# ─── Assemble HTML workbench ─────────────────────────────────────────────────


def _read_html(filename: str) -> str:
    return (APP_DIR / "html" / filename).read_text(encoding="utf-8")


def _logo_data_uri() -> str:
    logo_path = APP_DIR / "sonymusic.png"
    if logo_path.exists():
        b64 = base64.b64encode(logo_path.read_bytes()).decode("ascii")
        return f"data:image/png;base64,{b64}"
    return "sonymusic.png"


data_json = json.dumps(injected_data, default=str)
current_step = st.session_state.get("current_step", 1)

html_parts = [
    _read_html("head_xlsx_shim.html"),
    "<script>",
    f"window.__INJECTED_DATA__ = {data_json};",
    f"const DATA = window.__INJECTED_DATA__;",
    f"window.__INITIAL_STEP__ = {current_step};",
    f"window.__CATALOG_CREATED__ = {'true' if catalog_created else 'false'};",
    f"window.__USER_EMAIL__ = {json.dumps(st.session_state.get('user_email', ''))};",
    f"window.__SESSION_ID__ = {json.dumps(st.session_state.get('session_id', ''))};",
    f"window.__STEP_DATA__ = {json.dumps(st.session_state.get('step_data', {}), default=str)};",
    "</script>",
    _read_html("styles.html"),
    _read_html("body_open.html"),
    _read_html("workbench_scripts.html"),
    "</script>",
    _read_html("body_close.html"),
]

html_full = "\n".join(html_parts)
html_full = html_full.replace('src="sonymusic.png"', f'src="{_logo_data_uri()}"')

components.html(html_full, height=900, scrolling=True)
if _login_transition_requested:
    st.session_state.pop("_login_transition", None)

# Session checkpoints are persisted immediately after query parameters are parsed.
