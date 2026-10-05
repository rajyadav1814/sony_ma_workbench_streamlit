"""
Sony Music — M&A Catalogue Valuation Workbench
Streamlit host shell: auth gate, data loading, HTML workbench rendering.
"""

import os
import json
import base64
import time
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from config import CACHE_TTL_SECONDS, DB, SCHEMA, MAX_STEP, MIN_STEP, STEP_LABELS
from session_manager import (
    is_valid_email,
    clamp_step,
    ensure_session_tables,
    get_open_session,
    get_open_sessions,
    create_new_session,
    save_checkpoint,
    complete_session,
    abandon_open_sessions,
)
from data_loader import load_data_from_postgres, search_catalog, ensure_isrc_temp_table, compute_analytics_from_monthly_detail, invalidate_analytics
from build_progress import NULL_PROGRESS, BuildProgress
from catalog_builder import create_step1_selection_table, create_catalog_table, create_step2_table, _make_table_name, pull_monthly_detail
from postgres_connection import get_connection

# ─── Page config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Sony Music | M&A Catalog Valuation Workbench",
    page_icon="🎵",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Hide Streamlit default furniture for full-bleed HTML + proper spinner overlay
_app_styles = """<style>
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
    /* The step loader shell already reports progress; hide the native spinner under it. */
    [data-testid="stSpinner"] { display: none !important; }

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
    [data-testid="stComponentLoading"],
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

    /* While a rerun is in progress Streamlit hides the previous run's elements (data-stale) but leaves
       the bordered catalogue-card shells behind as empty outlines. Hide a card whose marker is stale. */
    [data-testid="stLayoutWrapper"]:has(> [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"][data-stale="true"] .catalog-card-marker),
    [data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"][data-stale="true"] .catalog-card-marker) {
        display: none !important;
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

    /* Loader layers (build card, plain overlay, step-loader shell) are fixed over the page and stay until the
       workbench reports it has painted (it adds .wb-loader--out), so there is no blank gap between them.
       Failsafe: once the script run is finished (the .wb-run-done marker exists) any layer still showing
       fades away on its own, so a blocked parent-page script can never leave the screen covered. */
    .stElementContainer:has(> iframe[srcdoc*="wb-loader-shell-marker"]) {
        position: fixed !important;
        inset: 0 !important;
        z-index: 999998;
        height: 100vh;
        background: #F1EFE7;
    }
    .stElementContainer:has(> iframe[srcdoc*="wb-loader-shell-marker"]) > iframe { height: 100vh !important; }
    .wb-loader--out { animation: wb-loader-out .28s ease forwards !important; }
    .stApp:has(.wb-run-done) :is(.wb-build-loader, .stElementContainer:has(> iframe[srcdoc*="wb-loader-shell-marker"])) {
        animation: wb-loader-out .4s ease 8s forwards;
    }
    @keyframes wb-loader-out { to { opacity: 0; visibility: hidden; pointer-events: none; } }
    .stElementContainer:has(.wb-run-done) { display: none !important; }

    @media (prefers-reduced-motion: reduce) {
        .wb-build-loader__spinner, .wb-progress__spin { animation-duration: 2.4s; }
        .wb-progress__fill, .wb-progress__fill::after { animation: none; }
        .wb-loader--out { animation-duration: .01s !important; }
    }
    /* Translucent variant: the screen underneath stays visible, only the loader card is shown. */
    .wb-build-loader--over {
        background: rgba(241, 239, 231, 0.55);
        -webkit-backdrop-filter: blur(2px);
        backdrop-filter: blur(2px);
    }

    /* Live catalog-build progress card (driven by build_progress.BuildProgress). */
    .wb-progress__card {
        width: min(560px, 92vw);
        max-height: 92vh;
        overflow-y: auto;
        padding: 36px 44px 30px;
        border: 1px solid rgba(20, 18, 14, 0.12);
        border-radius: 14px;
        background: #fff;
        box-shadow: 0 14px 34px rgba(20, 18, 14, 0.14);
        color: #141210;
        font-family: Inter, Arial, sans-serif;
        text-align: center;
    }
    .wb-progress__title { font-size: 1.25rem; font-weight: 700; margin-bottom: 6px; }
    .wb-progress__sub { font-size: .88rem; color: #6b665c; margin-bottom: 22px; }
    .wb-progress__bar { height: 14px; border-radius: 10px; background: #E5E1D8; overflow: hidden; }
    /* Each progress update replaces the card's DOM, so a CSS transition would never run. build_progress
       passes the previous percentage as --from and the bar animates from there to its new width. */
    .wb-progress__fill {
        position: relative;
        height: 100%;
        border-radius: 10px;
        background: linear-gradient(90deg, #E1261C 0%, #ff6b5e 100%);
        animation: wb-fill .45s ease-out both;
        overflow: hidden;
    }
    @keyframes wb-fill { from { width: var(--from, 0%); } }
    /* A moving sheen shows the build is alive even while one long query is running. */
    .wb-progress__fill::after {
        content: "";
        position: absolute;
        inset: 0;
        background: linear-gradient(100deg, transparent 30%, rgba(255,255,255,.38) 50%, transparent 70%);
        background-size: 200% 100%;
        animation: wb-sheen 1.6s linear infinite;
    }
    @keyframes wb-sheen { from { background-position: 200% 0; } to { background-position: -200% 0; } }
    .wb-progress__fill--failed { background: #b3261e; animation: none; }
    .wb-progress__fill--failed::after { display: none; }
    .wb-progress__step--failed { color: #b3261e; font-weight: 600; }
    .wb-progress__pct { margin-top: 12px; font-size: 1.15rem; font-weight: 700; color: #E1261C; }
    .wb-progress__meta { margin-top: 4px; font-size: .8rem; color: #8a8579; }
    .wb-progress__steps { list-style: none; margin: 22px 0 0; padding: 16px 0 0; border-top: 1px solid #ECE8DE; text-align: left; }
    .wb-progress__step { display: flex; gap: 10px; align-items: flex-start; padding: 4px 0; font-size: .86rem; line-height: 1.35; }
    .wb-progress__icon { flex: 0 0 18px; text-align: center; }
    .wb-progress__step--done { color: #1E9E5A; }
    .wb-progress__step--active { color: #141210; font-weight: 600; }
    .wb-progress__step--todo { color: #a8a396; }
    .wb-progress__detail { display: block; font-weight: 400; font-size: .78rem; color: #6b665c; }
    .wb-progress__spin {
        display: inline-block; width: 12px; height: 12px; margin-top: 2px;
        border: 2px solid #E5E1D8; border-top-color: #E1261C; border-radius: 50%;
        animation: wb-build-spin .8s linear infinite;
    }

    </style>"""
if hasattr(st, "html"):
    st.html(_app_styles)
else:
    st.markdown(_app_styles, unsafe_allow_html=True)

APP_DIR = Path(__file__).resolve().parent


EMPTY_TERRITORIES = {"countries": [], "codes": {}, "regions": {}, "default_local": []}


def _read_html(filename: str) -> str:
    return (APP_DIR / "html" / filename).read_text(encoding="utf-8")


def _logo_data_uri() -> str:
    logo_path = APP_DIR / "sonymusic.png"
    if logo_path.exists():
        b64 = base64.b64encode(logo_path.read_bytes()).decode("ascii")
        return f"data:image/png;base64,{b64}"
    return "sonymusic.png"


def _step_loader_html(title: str, step: int, completed_steps: list) -> str:
    """Workbench header + step tabs with the loader card over the step content only."""
    html = "\n".join([
        _read_html("head_xlsx_shim.html"),
        "<script>",
        f"window.__SHELL_STEP__ = {int(step)};",
        f"window.__SHELL_DONE__ = {json.dumps(completed_steps)};",
        f"window.__SHELL_LABEL__ = {json.dumps(title)};",
        f"window.__USER_EMAIL__ = {json.dumps(st.session_state.get('user_email', '') or _params.get('wb_email', ''))};",
        "</script>",
        _read_html("screens.html"),
        _read_html("styles.html"),
        _read_html("body_open.html"),
        _read_html("loader.html"),
        _read_html("loader_shell.html"),
        _read_html("body_close.html"),
    ])
    return html.replace('src="sonymusic.png"', f'src="{_logo_data_uri()}"')


_params = st.query_params
# Home button: the workbench passes the current step so the header/tabs can be redrawn while reloading.
# The move_resume handler below reruns the script, so the step is also kept in session state for that rerun.
_home_loader = st.session_state.pop("_home_loader", None)
if _params.get("wb_action") == "move_resume" and _params.get("wb_shell_step"):
    try:
        _home_loader = {
            "step": int(_params.get("wb_shell_step")),
            "done": [int(n) for n in json.loads(_params.get("wb_shell_done", "[]"))],
        }
    except (ValueError, TypeError):
        pass
_catalog_build_requested = (
    _params.get("wb_create_table") == "1"
    and _params.get("wb_step2_created") != "1"
)
_step_navigation_requested = (
    _params.get("wb_step") in {str(step) for step in range(MIN_STEP, MAX_STEP + 1)}
    and not _catalog_build_requested
)
_login_transition_requested = st.session_state.get("_login_transition", False)
_ui_transition_requested = st.session_state.get("_ui_transition", False)
_transition_loader_requested = (
    _catalog_build_requested
    or _step_navigation_requested
    or _login_transition_requested
    or _ui_transition_requested
    or _params.get("wb_action") == "move_resume"
    or bool(_home_loader)
    or _params.get("wb_reset") == "1"
)
_transition_loader = st.empty()
_loader_slot_used = False
_loader_is_overlay = False   # True when the loader is a fixed layer that the workbench dismisses itself
_build_progress = None


def _loader_overlay_html(title: str, over: bool = False) -> str:
    return f"""
    <div id="wb-navigation-loader" class="wb-build-loader{' wb-build-loader--over' if over else ''}" role="status" aria-live="polite">
      <div class="wb-build-loader__card">
        <div class="wb-build-loader__spinner" aria-hidden="true"></div>
        <div>{title}</div>
      </div>
    </div>
    """


if _transition_loader_requested:
    if _catalog_build_requested:
        _loader_title = "Building catalog…"
    elif _step_navigation_requested and _params.get("wb_step") == "2":
        _loader_title = "Processing matching catalogues…"
    elif _step_navigation_requested:
        _loader_title = "Processing…"
    elif st.session_state.get("_pending_login"):
        _loader_title = "Signing in…"
    else:
        _loader_title = "Processing Workbench…"
    if _catalog_build_requested:
        # Catalog build: a live card whose percentage is driven by the real database work below.
        _build_progress = BuildProgress(_transition_loader)
        _build_progress.stage("prepare", "Starting")
        _loader_slot_used = _loader_is_overlay = True
    elif _step_navigation_requested or _home_loader:
        # Step changes keep the header and tabs on screen; only the content area shows the loader.
        if _home_loader and not (_catalog_build_requested or _step_navigation_requested):
            _shell_step = clamp_step(_home_loader["step"])
            _shell_done = _home_loader["done"]
        else:
            _shell_step = clamp_step(int(_params.get("wb_step") or st.session_state.get("current_step", MIN_STEP)))
            try:
                _shell_done = [int(n) for n in json.loads(_params.get("wb_step_data", "{}")).get("completedSteps", [])]
            except (ValueError, TypeError, AttributeError):
                _shell_done = []
        with _transition_loader.container():
            components.html(_step_loader_html(_loader_title, _shell_step, _shell_done), height=760, scrolling=False)
        _loader_slot_used = _loader_is_overlay = True
    elif st.session_state.get("_pending_login"):
        # Login → welcome back: keep the Welcome screen visible, loader card on top only.
        from steps.welcome import render_welcome_screen
        with _transition_loader.container():
            render_welcome_screen(None, backdrop=True)
            st.markdown(_loader_overlay_html(_loader_title, over=True), unsafe_allow_html=True)
        _loader_slot_used = True
    elif _ui_transition_requested and st.session_state.get("_resume_backdrop"):
        # Start new / Continue / Restart / Remove: keep the resume screen visible, loader card on top only.
        from steps.welcome import render_resume_screen
        with _transition_loader.container():
            render_resume_screen(None, backdrop=True)
            st.markdown(_loader_overlay_html(_loader_title, over=True), unsafe_allow_html=True)
        _loader_slot_used = True
    else:
        _transition_loader.markdown(_loader_overlay_html(_loader_title), unsafe_allow_html=True)
        _loader_slot_used = _loader_is_overlay = True

if _params.get("wb_logout") == "1":
    for key in list(st.session_state.keys()):
        if key != "_session_tables_checked":
            del st.session_state[key]
    for key in list(st.query_params.keys()):
        if key.startswith("wb_"):
            del st.query_params[key]
    _transition_loader.empty()
    from steps.welcome import render_welcome_screen
    render_welcome_screen(None)
    st.stop()

if not st.session_state.get("user_email") and "wb_email" not in _params:
    st.session_state.pop("_ui_transition", None)
    st.session_state.pop("_login_transition", None)
    _transition_loader.empty()
    from steps.welcome import render_welcome_screen
    render_welcome_screen(None)
    st.stop()

# ─── PostgreSQL connection ──────────────────────────────────────────────────
# One long-lived connection per user, shared by every page load (each step click reloads the page into a
# new Streamlit session; opening a connection costs seconds).
if _build_progress:
    _build_progress.note("Connecting to the database")   # the first connection of a user takes a few seconds
conn = get_connection(st.session_state.get("user_email") or _params.get("wb_email", ""))
session = conn.session()

if not conn.state.get("session_tables_ready"):
    try:
        ensure_session_tables(session)
        conn.state["session_tables_ready"] = True
    except Exception:
        pass

_resume_action = st.session_state.pop("_pending_resume_action", None)
if isinstance(_resume_action, dict):
    _action = _resume_action.get("action")
    if _action == "start_new":
        _new_sess = create_new_session(session, st.session_state.get("user_email", ""))
        st.session_state["welcomed"] = True
        st.session_state["session_id"] = _new_sess["session_id"]
        st.session_state["current_step"] = _new_sess["current_step"]
        st.session_state["step_data"] = _new_sess["step_data"]
        st.session_state.pop("_pending_resume", None)
        st.session_state.pop("_pending_resume_list", None)
        st.session_state.pop("_force_resume", None)
    elif _action == "restart":
        _restart_data = _resume_action.get("step_data", {})
        _restart_data = dict(_restart_data) if isinstance(_restart_data, dict) else {}
        _restart_data["currentStep"] = 1
        _restart_data["completedSteps"] = []
        _restart_session_id = _resume_action.get("session_id", "")
        save_checkpoint(session, _restart_session_id, 1, _restart_data)
        st.session_state["welcomed"] = True
        st.session_state["session_id"] = _restart_session_id
        st.session_state["current_step"] = 1
        st.session_state["step_data"] = _restart_data
        st.session_state.pop("_pending_resume", None)
        st.session_state.pop("_pending_resume_list", None)
        st.session_state.pop("_force_resume", None)
        for _param in ("wb_step", "wb_step_data", "wb_create_table"):
            st.query_params.pop(_param, None)
    elif _action == "remove":
        _removed_session_id = _resume_action.get("session_id", "")
        complete_session(session, _removed_session_id)
        _remaining_sessions = [
            item
            for item in _resume_action.get("pending_sessions", [])
            if item and item.get("session_id") != _removed_session_id
        ]
        if _remaining_sessions:
            st.session_state["_pending_resume_list"] = _remaining_sessions
            st.session_state["_pending_resume"] = _remaining_sessions[0]
        else:
            _new_sess = create_new_session(session, st.session_state.get("user_email", ""))
            st.session_state["welcomed"] = True
            st.session_state["session_id"] = _new_sess["session_id"]
            st.session_state["current_step"] = _new_sess["current_step"]
            st.session_state["step_data"] = _new_sess.get("step_data", {})
            st.session_state.pop("_pending_resume", None)
            st.session_state.pop("_pending_resume_list", None)
        st.session_state.pop("_force_resume", None)

# ─── Restore session from query params (after JS-triggered reload) ────────────

if _params.get("wb_action") == "move_resume":
    _email = st.session_state.get("user_email", "") or _params.get("wb_email", "")
    from session_manager import get_open_sessions as _get_open_sessions
    open_sessions = _get_open_sessions(session, _email) if _email else []
    for key in list(st.session_state.keys()):
        if key not in ("user_email", "_session_tables_checked"):
            del st.session_state[key]
    if _home_loader:
        st.session_state["_home_loader"] = _home_loader
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
    if _params.get("wb_view") == "resume" and is_valid_email(_params["wb_email"]):
        # Browser refresh on the "Welcome back" screen: show it again instead of logging out.
        _restored = get_open_sessions(session, _params["wb_email"])
        if _restored:
            st.session_state["_pending_resume_list"] = _restored
            st.session_state["_pending_resume"] = _restored[0]
        st.session_state["_force_resume"] = True
    else:
        st.session_state["welcomed"] = True
if "wb_session_id" in _params and "session_id" not in st.session_state:
    st.session_state["session_id"] = _params["wb_session_id"]
if "wb_step" in _params:
    st.session_state["current_step"] = clamp_step(int(_params["wb_step"]))

if st.session_state.pop("_pending_login", False):
    _email = st.session_state.get("user_email", "")
    open_sessions = get_open_sessions(session, _email) if _email else []
    if open_sessions:
        st.session_state["_pending_resume_list"] = open_sessions
        st.session_state["_pending_resume"] = open_sessions[0]
        st.session_state.pop("_login_transition", None)
    else:
        new_sess = create_new_session(session, _email)
        st.session_state["welcomed"] = True
        st.session_state["session_id"] = new_sess["session_id"]
        st.session_state["current_step"] = new_sess["current_step"]
        st.session_state["step_data"] = new_sess.get("step_data", {})
        save_checkpoint(
            session,
            new_sess["session_id"],
            new_sess["current_step"],
            new_sess.get("step_data", {}),
        )

# ─── Auth gate ───────────────────────────────────────────────────────────────
if not st.session_state.get("user_email"):
    st.session_state.pop("_ui_transition", None)
    st.session_state.pop("_login_transition", None)
    _transition_loader.empty()
    from steps.welcome import render_welcome_screen
    render_welcome_screen(session)
    st.stop()

if (
    "_pending_resume" in st.session_state
    or "_pending_resume_list" in st.session_state
    or st.session_state.get("_force_resume")
) and "welcomed" not in st.session_state:
    st.session_state.pop("_ui_transition", None)
    _transition_loader.empty()
    from steps.welcome import render_resume_screen
    render_resume_screen(session)
    st.stop()

# Past the resume screen: drop the params that only existed to restore it, so a later refresh
# in the workbench behaves as before (the workbench writes its own wb_* params as you navigate).
if st.query_params.get("wb_view") == "resume":
    st.query_params.pop("wb_view", None)
    st.query_params.pop("wb_email", None)

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

# ─── Load all data & compute (wrapped in spinner for loading feedback) ────────
# Most functions use @st.cache_data so subsequent reloads are fast (cache hit).
with st.container():
    _requested_step = clamp_step(
        int(params.get("wb_step", st.session_state.get("current_step", MIN_STEP)) or MIN_STEP)
    )
    _needs_full_data = _requested_step >= 3 or params.get("wb_step2_created") == "1"
    if _needs_full_data:
        try:
            injected_data = load_data_from_postgres(conn)
        except Exception:
            injected_data = {"albums": [], "ambiguity_matches": {}, "tracks": [], "track_album_bridge": [],
                             "consumption_matrix": [], "growth_trend": [], "release_year_analysis": [],
                             "new_release_tracks": [], "catalog_options": {"artists": [], "labels": []},
                             "territories": EMPTY_TERRITORIES}
    else:
        injected_data = {
            "albums": [], "ambiguity_matches": {}, "tracks": [], "track_album_bridge": [],
            "consumption_matrix": [], "growth_trend": [], "release_year_analysis": [],
            "new_release_tracks": [], "catalog_options": {"artists": [], "labels": []},
            "territories": EMPTY_TERRITORIES,
        }

    # Cache the latest live matches in the active Streamlit session. The Step 1
    # → Step 2 navigation reloads the host, so this guarantees the rows remain
    # available to the freshly created workbench iframe.
    _live_match_cache = st.session_state.get("_live_ambiguity_matches", {})
    if not isinstance(_live_match_cache, dict):
        _live_match_cache = {}

    # The ISRC upload table has to exist before an "ISRC List" search can use it.
    if wb_isrc_file and wb_isrc_filename:
        try:
            ensure_isrc_temp_table(
                conn, base64.b64decode(wb_isrc_file), st.session_state.get("user_email", "unknown"), wb_isrc_filename
            )
        except Exception as e:
            st.session_state["_isrc_error"] = f"{type(e).__name__}: {e}"

    # The workbench re-sends the search term on every reload, so only query when it is new for this
    # mode and ISRC upload (or the stored answer has aged out). Empty answers count; failed queries do not.
    if wb_search_term and wb_search_term.strip():
        _live_search_key = wb_search_term.strip()
        _memo_key = f"{wb_search_mode}|{conn.state.get('isrc_hash', '')}|{_live_search_key}"
        _search_memo = conn.state.setdefault("search_memo", {})
        _memo_hit = _search_memo.get(_memo_key)
        if not _memo_hit or time.time() - _memo_hit[0] > CACHE_TTL_SECONDS:
            try:
                _search_memo[_memo_key] = (time.time(), search_catalog(conn, wb_search_mode, _live_search_key))
            except Exception as e:
                st.session_state["_search_error"] = f"{type(e).__name__}: {e}"
        if _memo_key in _search_memo and _search_memo[_memo_key][1]:
            _live_match_cache[_live_search_key] = _search_memo[_memo_key][1]
            st.session_state["_live_ambiguity_matches"] = _live_match_cache
    if _live_match_cache:
        injected_data["ambiguity_matches"].update(_live_match_cache)

    user_email = st.session_state.get("user_email", "")
    catalog_created = False

    current_wb_step = int(params.get("wb_step", "0"))
    _sid = st.session_state.get("session_id", params.get("wb_session_id", ""))
    _session_step_data = st.session_state.get("step_data", {})
    if not isinstance(_session_step_data, dict):
        _session_step_data = {}
    _search_term = _session_step_data.get("searchTerm", "")
    _search_mode = _session_step_data.get("searchMode", "Artist")
    wb_step_data_raw = params.get("wb_step_data", "")
    if wb_step_payload:
        _search_term = wb_step_payload.get("searchTerm") or _search_term
        _search_mode = wb_step_payload.get("searchMode") or _search_mode
    if not _search_term:
        _search_term = params.get("wb_search_term") or "catalog"

    _selected_entities = []
    if wb_step_payload:
        _selected_entities = (
            wb_step_payload.get("confirmed_mrelg_ids")
            or wb_step_payload.get("resolvedEntities")
            or wb_step_payload.get("entities")
            or _session_step_data.get("confirmed_mrelg_ids")
            or _session_step_data.get("resolvedEntities")
            or []
        )
    else:
        _selected_entities = (
            _session_step_data.get("confirmed_mrelg_ids")
            or _session_step_data.get("resolvedEntities")
            or []
        )

    _progress = _build_progress or NULL_PROGRESS
    if current_wb_step >= 2 and params.get("wb_create_table") == "1" and params.get("wb_step2_created") != "1":
        # Progress is shown by the live card (_build_progress), updated as each query completes.
        with st.container():
            st.session_state["_table_creation_error"] = ""
            if not _search_term or not _sid:
                st.session_state["_table_creation_error"] = "Catalog creation is missing the search term or session ID. Please return to Step 1 and try again."
            else:
                try:
                    step1_result = None
                    # Fallback: if no entities selected but we have a search term, use it as the entity.
                    step1_result = create_step1_selection_table(
                        session, _search_term, user_email, _selected_entities or [_search_term],
                        search_mode=_search_mode, session_id=_sid, progress=_progress,
                        isrc_table=conn.state.get("isrc_table"),
                    )
                    if step1_result and step1_result["status"] == "success" and step1_result.get("row_count", 0) > 0:
                        step1_table = step1_result["table_name"]
                        st.session_state["_step1_table_name"] = step1_table
                        step2_table = create_step2_table(session, step1_table, _selected_entities, user_email, _search_term, session_id=_sid, progress=_progress)
                        st.session_state["_catalog_table_name"] = step2_table
                        invalidate_analytics(step2_table)   # same table name is reused when a catalogue is rebuilt
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
    if not step2_table_name and _requested_step >= 3 and _sid and _search_term != "catalog":
        step2_table_name = f"{DB}.{_make_table_name(2, user_email, _search_term, _sid)}"
        st.session_state["_catalog_table_name"] = step2_table_name
    if step2_table_name and (params.get("wb_step2_created") == "1" or catalog_created or st.session_state.get("_catalog_table_name")):
        _progress.stage("albums", "Reading the catalog albums")
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

    # Steps 4-8: every figure is computed from the database for this catalog
    # (see analytics.py). Cached per catalog table; albums are passed as JSON for hashability.
    if step2_table_name and injected_data.get("albums"):
        try:
            albums_json = json.dumps(injected_data["albums"], default=str)
            computed = compute_analytics_from_monthly_detail(session, step2_table_name, albums_json, progress=_progress)
            injected_data.update(computed)
        except Exception as e:
            # Surface the failure in the UI rather than showing invented numbers.
            injected_data["analytics_error"] = f"{type(e).__name__}: {e}"

    # Debug info for troubleshooting step 2→3 data flow
    injected_data["_debug"] = {
        "step2_table_name": st.session_state.get("_catalog_table_name", ""),
        "wb_step2_created": params.get("wb_step2_created", ""),
        "catalog_created": catalog_created,
        "album_count": len(injected_data.get("albums", [])),
        "table_creation_error": st.session_state.get("_table_creation_error", ""),
        "album_load_error": st.session_state.get("_album_load_error", ""),
        "search_error": st.session_state.get("_search_error", ""),
        "isrc_error": st.session_state.get("_isrc_error", ""),
        "selected_entities": _selected_entities[:5] if _selected_entities else [],
        "search_term": _search_term,
        "current_wb_step": current_wb_step,
    }

# ─── Assemble HTML workbench ─────────────────────────────────────────────────


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
    _read_html("screens.html"),
    _read_html("styles.html"),
    _read_html("body_open.html"),
    _read_html("loader.html"),
    _read_html("workbench_scripts.html"),
    "</script>",
    _read_html("body_close.html"),
]

html_full = "\n".join(html_parts)
html_full = html_full.replace('src="sonymusic.png"', f'src="{_logo_data_uri()}"')

_build_failed = bool(
    st.session_state.get("_table_creation_error")
    or st.session_state.get("_album_load_error")
    or injected_data.get("analytics_error")
)
if _build_progress:
    # Leave the card up (showing "Done", or where it stopped) until the workbench takes over.
    _build_progress.finish(failed=_build_failed)
if _loader_slot_used and not _loader_is_overlay:
    # Welcome / resume backdrops sit in the page flow, so they have to go before the workbench appears.
    _transition_loader.empty()
# Fixed loader layers stay up until the workbench iframe paints and dismisses them itself
# (workbench_scripts.html), so there is no blank gap. The marker below starts a CSS failsafe that
# removes them a few seconds after this run ends, whatever happens in the browser.
components.html(html_full, height=900, scrolling=True)
if _loader_is_overlay:
    st.html('<div class="wb-run-done"></div>')
st.session_state.pop("_ui_transition", None)
if _login_transition_requested:
    st.session_state.pop("_login_transition", None)

# Session checkpoints are persisted immediately after query parameters are parsed.
