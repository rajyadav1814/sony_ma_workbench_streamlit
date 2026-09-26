"""Welcome and Resume screens rendered in Streamlit (before the HTML workbench)."""

import json
import streamlit as st
from config import MAX_STEP, MIN_STEP, STEP_LABELS
from session_manager import (
    is_valid_email,
    get_open_session,
    get_open_sessions,
    create_new_session,
    abandon_open_sessions,
    save_checkpoint,
    complete_session,
)


def render_welcome_screen(session):
    """Render the welcome / login form. Sets session_state and triggers rerun."""
    welcome_styles = """
        <style>
            [data-testid="stVerticalBlock"] {gap: 1rem !important;}
            [data-testid="stAppViewContainer"] {
                background: #F1EFE7 !important;
                padding-top: 75px;
            }
            div.block-container {
                padding: 40px 20px !important;
                max-width: 100% !important;
            }
            .welcome-card {
                background: #ffffff;
                border-radius: 16px;
                padding: 48px 40px;
                box-shadow: 0 4px 24px rgba(0,0,0,0.08);
                max-width: 640px;
                margin: 0 auto;
            }
            .welcome-card h1 {
                font-size: 28px;
                font-weight: 800;
                margin-bottom: 16px;
                color: #16a34a;
            }
            .welcome-card p {
                line-height: 1.6;
                margin-bottom: 8px;
                color: #1a1a2e;
            }
            .welcome-card .subtitle {
                opacity: 0.65;
                color: #4b5563;
            }
            /* Keep the native form, input, submit button, and messages aligned
               to the welcome card rather than stretching across the page. */
            [data-testid="stForm"],
            [data-testid="stTextInput"],
            [data-testid="stButton"],
            [data-testid="stFormSubmitButton"],
            [data-testid="stAlert"] {
                max-width: 640px;
                width: 100%;
                margin-left: auto;
                margin-right: auto;
            }
            [data-testid="stForm"] {
                border: 0 !important;
                padding: 0 !important;
            }
            /* Fix input text colors on white background */
            [data-testid="stTextInput"] label {
                color: #1a1a2e !important;
                font-size: 14px !important;
                font-weight: 600 !important;
            }
            [data-testid="stTextInput"] input {
                display: block !important;
                box-sizing: border-box !important;
                width: 100% !important;
                min-height: 44px !important;
                appearance: none !important;
                color-scheme: light !important;
                color: #1a1a2e !important;
                background: #ffffff !important;
                border: 1px solid #9ca3af !important;
                border-radius: 6px !important;
                padding: 10px 12px !important;
                font: 400 16px/1.4 Inter, Arial, sans-serif !important;
                height: 44px !important;
                outline: none !important;
                box-shadow: inset 0 1px 2px rgba(0,0,0,0.06) !important;
            }
            [data-testid="stTextInput"] input:autofill {
                -webkit-text-fill-color: #1a1a2e !important;
                -webkit-box-shadow: 0 0 0 1000px #ffffff inset !important;
                box-shadow: 0 0 0 1000px #ffffff inset !important;
            }
            [data-testid="stTextInput"] input:-webkit-autofill,
            [data-testid="stTextInput"] input:-webkit-autofill:hover,
            [data-testid="stTextInput"] input:-webkit-autofill:focus,
            [data-testid="stTextInput"] input:-webkit-autofill:active {
                -webkit-text-fill-color: #1a1a2e !important;
                -webkit-box-shadow: 0 0 0 1000px #ffffff inset !important;
                box-shadow: 0 0 0 1000px #ffffff inset !important;
            }
            [data-testid="stTextInput"] input:focus {
                border-color: #3b5de7 !important;
                box-shadow: 0 0 0 3px rgba(59,93,231,0.14) !important;
            }
            [data-testid="stTextInput"] input::placeholder {
                color: #9ca3af !important;
                font-size: 16px !important;
            }
            /* Button styling for welcome screen */
            button[data-testid="stBaseButton-primary"] {
                background-color: #3b5de7 !important;
                color: #ffffff !important;
                border-color: #3b5de7 !important;
            }
            button[data-testid="stBaseButton-primary"]:hover {
                background-color: #2d4ad0 !important;
                border-color: #2d4ad0 !important;
            }
            /* Form submit controls do not use stButton; size this one directly. */
            [data-testid="stFormSubmitButton"] {
                width: min(640px, 100%) !important;
                margin: 0 auto !important;
            }
            [data-testid="stFormSubmitButton"] > button,
            [data-testid="stFormSubmitButton"] button {
                width: 100% !important;
                min-height: 44px !important;
                font-size: 15px !important;
                font-weight: 700 !important;
                background: #3B5DE7 !important;
                border-color: #3B5DE7 !important;
                color: #FFFFFF !important;
            }
            [data-testid="stFormSubmitButton"] > button:hover,
            [data-testid="stFormSubmitButton"] button:hover {
                background: #2D4AD0 !important;
                border-color: #2D4AD0 !important;
            }
            /* Validation messages use a distinct, readable error treatment. */
            [data-testid="stAlert"] {
                background: #FFF1F2 !important;
                border: 1px solid #FDA4AF !important;
                border-radius: 10px !important;
                color: #9F1239 !important;
                padding: 14px 16px !important;
            }
            [data-testid="stAlert"] *,
            [data-testid="stAlert"] p,
            [data-testid="stAlert"] [data-testid="stMarkdownContainer"] {
                color: #9F1239 !important;
                opacity: 1 !important;
            }
        </style>
        """
    if hasattr(st, "html"):
        st.html(welcome_styles)
    else:
        st.markdown(welcome_styles, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 4, 1])
    with col2:
        st.markdown(
            """
            <div class="welcome-card">
                <h1>Welcome!</h1>
                <p>
                    To the <strong style="color: #dc2626;">Sony Music M&A Catalogue Valuation Platform</strong>.
                </p>
                <p class="subtitle">
                    Use this tool to explore catalogue data, run valuation scenarios,
                    and analyse growth trends across the portfolio.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("<div style='padding-top: 30px;'></div>", unsafe_allow_html=True)

        with st.form("welcome_login_form", border=False):
            email = st.text_input(
                "Email",
                placeholder="you@sonymusic.com",
                key="welcome_email",
            )

            st.markdown("<div style=\"padding-top: 30px;\"></div>", unsafe_allow_html=True)
            submitted = st.form_submit_button(
                "Get Started",
                type="primary",
                use_container_width=True,
            )

        if submitted:
            clean_email = email.strip().lower()
            if not clean_email:
                st.warning("Please enter your email to continue.")
                st.stop()
            if not is_valid_email(clean_email):
                st.error("Please enter a valid email address.")
                st.stop()

            st.session_state["user_email"] = clean_email

            open_sessions = get_open_sessions(session, clean_email)
            if open_sessions:
                # Multiple in-progress catalogues are possible (one per artist/label
                # search) — store the whole list so the resume screen can let the
                # user pick which one to continue, restart, or remove.
                st.session_state["_pending_resume_list"] = open_sessions
                st.session_state["_pending_resume"] = open_sessions[0]
            else:
                # No existing session — create new and go straight to dashboard.
                new_sess = create_new_session(session, clean_email)
                st.session_state["welcomed"] = True
                st.session_state["session_id"] = new_sess["session_id"]
                st.session_state["current_step"] = new_sess["current_step"]
                st.session_state["step_data"] = new_sess.get("step_data", {})
                st.session_state["_login_transition"] = True
                save_checkpoint(
                    session,
                    new_sess["session_id"],
                    new_sess["current_step"],
                    new_sess.get("step_data", {}),
                )
            st.rerun()


def render_resume_screen(session):
    """Render the 'Welcome back' resume screen matching the Next.js reference design."""
    email = st.session_state["user_email"]

    def _mark_ui_transition():
        st.session_state["_ui_transition"] = True

    sessions_list = st.session_state.get("_pending_resume_list")
    if not sessions_list:
        single = st.session_state.get("_pending_resume")
        sessions_list = [single] if single else []

    _fallback_term = ""
    _params = st.query_params
    _sd_raw = _params.get("wb_step_data", "")
    if _sd_raw:
        try:
            import json as _json
            _fallback_term = _json.loads(_sd_raw).get("searchTerm", "")
        except Exception:
            pass

    st.markdown(
        """
        <style>
            [data-testid="stVerticalBlock"] {gap: 0.8rem !important;}
            [data-testid="stAppViewContainer"] {
                background: #F1EFE7 !important;
            }
            div.block-container {
                padding: 0px 200px !important; max-width: 100% !important;
                display: flex; align-items: flex-start; justify-content: center;
                min-height: 100vh; max-height: none !important;
                overflow: visible !important;
            }
            .stApp {overflow: visible !important; background: #F1EFE7;}

            /* Top bar */
            .resume-topbar {
                width: 100%;
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding: 18px 0;
                border-bottom: 1.5px solid #141210;
                margin-bottom: 20px;
            }
            .resume-brand {
                display: flex;
                align-items: center;
                gap: 14px;
                flex: 0 0 180px;
            }
            .resume-brand-text {
                line-height: 1.2;
                display: flex;
                flex-direction: column;
            }
            .resume-brand-name {
                font-size: 11px;
                font-weight: 600;
                letter-spacing: 2.8px;
                color: #141210;
                padding-bottom: 4px;
                border-bottom: 1px solid #c9c5bb;
                margin-bottom: 3px;
            }
            .resume-brand-sub {
                font-size: 10px;
                font-weight: 600;
                letter-spacing: 2.8px;
                color: #141210;
            }
            .resume-topbar-center {
                display: flex;
                flex-direction: column;
                align-items: center;
                text-align: center;
                flex: 1;
                margin: 0 20px;
            }
            .resume-topbar-title {
                font-weight: 800;
                font-size: 26px;
                line-height: 1.1;
                color: #c51616;
            }
            .resume-topbar-desc {
                color: #5a564c;
                font-size: 15px;
                line-height: 1.4;
                max-width: 800px;
                margin-top: 6px;
            }
            .resume-logout {
                height: 36px;
                padding: 0 20px;
                border: 1px solid #d0ccc3;
                border-radius: 10px;
                background: #e70b0b;
                color: #fdfcfb;
                font-size: 13px;
                font-weight: 700;
                cursor: pointer;
            }

            /* Heading */
            .resume-heading {
                width: 100%;
            }
            .resume-heading h2 {
                color: #1b5a02;
                font-size: 32px;
                font-weight: 800;
                margin: 0 0 -17px 0;
                text-align: center;
            }
            .resume-heading .subtitle {
                color: #6b7280;
                font-size: 16px;
                margin-bottom: 22px;
                text-align: center;
            }

            /* Session card — top half; the button row closes the shape */
            .resume-session-card {
                background: transparent;
                border-radius: 0;
                padding: 0px 30px 8px;
                border: 0;
                margin-bottom: 0;
            }
            [data-testid="stVerticalBlockBorderWrapper"]:has(.catalog-card-marker),
            .st-emotion-cache-1fpp8sd:has(.catalog-card-marker) {
                display: flex !important;
                gap: 0rem !important;
                width: 100% !important;
                max-width: 100% !important;
                height: auto !important;
                min-width: 1rem !important;
                flex-flow: column !important;
                flex: 1 1 0% !important;
                align-items: flex-start !important;
                justify-content: flex-start !important;
                border: 5px solid rgb(20 19 19 / 20%) !important;
                border-radius: 2.5rem !important;
                padding: calc(1rem - 3px) !important;
                overflow: visible !important;
            }
            .resume-session-header {
                display: flex;
                align-items: center;
                gap: 16px;
                margin: 0 0 14px 0;
            }
            .resume-session-avatar {
                width: 52px;
                height: 52px;
                border-radius: 50%;
                background: linear-gradient(135deg, #e56eac 0%, #3b5de7 100%);
                display: flex;
                align-items: center;
                justify-content: center;
                color: #fff;
                font-weight: 700;
                font-size: 18px;
                flex-shrink: 0;
            }
            .resume-session-info .name {
                color: #111827;
                font-weight: 600;
                font-size: 18px;
            }
            .resume-session-info .desc {
                color: #6b7280;
                font-size: 14px;
                margin-top: 3px;
            }
            .resume-session-info .updated {
                color: #8f8a7e;
                font-size: 12px;
                margin-top: 4px;
            }
            .resume-progress-summary {
                display: flex;
                justify-content: space-between;
                margin: 0 0 10px 0;
                color: #6b7280;
                font-size: 13px;
                font-weight: 500;
            }
            /* Wrap the pills so the last steps are never clipped off-screen */
            .resume-progress-pills {
                display: flex;
                flex-wrap: wrap;
                gap: 8px;
                margin: 0;
                padding: 0;
            }
            .step-pill {
                padding: 8px 16px;
                border-radius: 24px;
                font-size: 13px;
                font-weight: 600;
                white-space: nowrap;
                flex-shrink: 0;
                display: inline-flex;
                align-items: center;
                gap: 4px;
            }
            .step-pill.completed { background: #16a34a; color: #fff; }
            .step-pill.current { background: #dc2626; color: #fff; box-shadow: 0 0 0 3px rgba(220,38,38,0.2); }
            .step-pill.future { background: #eef1f6; color: #9ca3af; }

            /* ── Action buttons ──────────────────────────────────────────────
               Colours are applied with pure CSS via an invisible marker span that
               Streamlit renders in the element container immediately before each
               button (inline <script>/onerror handlers are stripped by Snowsight,
               so JS-based colouring cannot be used).

               The element-container test id was renamed from "element-container"
               to "stElementContainer" in Streamlit 1.36, and Streamlit in
               The server tracks a newer build — so every rule is emitted for BOTH
               spellings. Targeting only the old name silently matches nothing and
               leaves all buttons on the base colour.

               The general-sibling combinator (~) is used rather than (+) so an
               extra wrapper element between the marker and the button cannot
               break the match. Each marker sits alone in its own column with a
               single button, so it cannot leak onto an unrelated control. */
            [data-testid="stButton"] { width: 100% !important; }
            [data-testid="stButton"] button {
                height: 36px !important;
                padding: 0 14px !important;
                border: none !important;
                border-radius: 8px !important;
                color: #fff !important;
                font-size: 13px !important;
                font-weight: 600 !important;
                cursor: pointer !important;
                white-space: nowrap !important;
                width: 100% !important;
                background-color: #374151 !important;
                transition: filter 0.15s ease !important;
            }
            [data-testid="stButton"] button:hover { filter: brightness(0.9); }

            [data-testid="element-container"]:has(.mk-continue) ~ [data-testid="element-container"] button,
            [data-testid="stElementContainer"]:has(.mk-continue) ~ [data-testid="stElementContainer"] button {
                background-color: #a18219 !important;
            }
            [data-testid="element-container"]:has(.mk-restart) ~ [data-testid="element-container"] button,
            [data-testid="stElementContainer"]:has(.mk-restart) ~ [data-testid="stElementContainer"] button {
                background-color: #3b5de7 !important;
            }
            [data-testid="element-container"]:has(.mk-remove) ~ [data-testid="element-container"] button,
            [data-testid="stElementContainer"]:has(.mk-remove) ~ [data-testid="stElementContainer"] button {
                background-color: #dc2626 !important;
            }
            [data-testid="element-container"]:has(.mk-startnew) ~ [data-testid="element-container"] button,
            [data-testid="stElementContainer"]:has(.mk-startnew) ~ [data-testid="stElementContainer"] button {
                background-color: #16a34a !important;
                color: #ffffff !important;
                border: 1.5px solid #16a34a !important;
                height: 38px !important;
                font-size: 13px !important;
                min-width: 110px !important;
            }
            [data-testid="element-container"]:has(.mk-logout) ~ [data-testid="element-container"] button,
            [data-testid="stElementContainer"]:has(.mk-logout) ~ [data-testid="stElementContainer"] button {
                background-color: #e70b0b !important;
                border-radius: 10px !important;
                padding: 0 20px !important;
            }

            /* Resume actions form the upper section of the catalogue card. */
            [data-testid="stHorizontalBlock"]:has(.rs-btnrow) {
                background: transparent;
                border: 0;
                border-radius: 0;
                padding: 0 16px;
                margin-top: 0 !important;
                align-items: center !important;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )

    def _marker(name: str) -> None:
        """Emit an invisible hook so the next button can be styled via CSS :has()."""
        st.markdown(
            f'<span class="mk-{name}" style="display:none"></span>',
            unsafe_allow_html=True,
        )

    def _pills_html(current_step: int) -> str:
        html = ""
        for i, label in enumerate(STEP_LABELS):
            step_num = i + 1
            if step_num < current_step:
                html += (
                    f'<span class="step-pill completed">'
                    f'&#10003; {step_num} &middot; {label}'
                    f'</span>'
                )
            elif step_num == current_step:
                html += f'<span class="step-pill current">{step_num} &middot; {label}</span>'
            else:
                html += f'<span class="step-pill future">{step_num} &middot; {label}</span>'
        return html

    # ─── Top bar ─────────────────────────────────────────────────────────────
    # Load Sony Music logo as base64 for inline display
    import base64
    from pathlib import Path
    _logo_path = Path(__file__).parent.parent / "sonymusic.png"
    _logo_b64 = ""
    if _logo_path.exists():
        _logo_b64 = base64.b64encode(_logo_path.read_bytes()).decode()

    topbar_left, topbar_center, topbar_right = st.columns([1, 3, 1], gap="small")

    with topbar_left:
        _logo_img = f'<img src="data:image/png;base64,{_logo_b64}" alt="Sony Music" height="42" width="42" style="object-fit:contain;"/>' if _logo_b64 else ''
        st.markdown(
            f"""
            <div class="resume-brand">
                {_logo_img}
                <div class="resume-brand-text">
                    <span class="resume-brand-name">SONY MUSIC</span>
                    <span class="resume-brand-sub">LATIN</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with topbar_center:
        st.markdown(
            """
            <div class="resume-topbar-center">
                <div class="resume-topbar-title">M&amp;A CATALOG VALUATION PLATFORM</div>
                <div class="resume-topbar-desc">An intelligent solution that identifies music catalogues, resolves artist and catalogue ambiguities, maps ownership and distribution territories, and generates decision-ready valuation insights.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with topbar_right:
        _marker("logout")
        if st.button("Logout", key="logout_btn", on_click=_mark_ui_transition):
            for key in list(st.session_state.keys()):
                if key not in ("_session_tables_checked", "_ui_transition"):
                    del st.session_state[key]
            st.rerun()

    st.markdown("<hr style='border:none;border-top:1.5px solid #141210;margin:0 0 20px 0;'>", unsafe_allow_html=True)

    # ─── Heading with Start new action on the right ────────────────────────────
    _n = len(sessions_list)
    _subtitle = (
        f"You have {_n} catalogues in progress. Would you like to Continue, Restart, or Remove an existing catalogue and Start New" if _n > 1
        else "Pick up where you left off or start fresh"
    )
    heading_col, start_col = st.columns([4, 1], gap="small")
    with heading_col:
        st.markdown(
            f"""<div class="resume-heading">
                <h2>Welcome back!</h2>
                <div class="subtitle">{_subtitle}</div>
            </div>""",
            unsafe_allow_html=True,
        )
    with start_col:
        st.markdown("<div style='padding-top: 18px;'></div>", unsafe_allow_html=True)
        _marker("startnew")
        if st.button(
            "Start new",
            use_container_width=True,
            key="start_new_btn",
            on_click=_mark_ui_transition,
        ):
            new_sess = create_new_session(session, email)
            st.session_state["welcomed"] = True
            st.session_state["session_id"] = new_sess["session_id"]
            st.session_state["current_step"] = new_sess["current_step"]
            st.session_state["step_data"] = new_sess["step_data"]
            st.session_state["_login_transition"] = True
            st.session_state.pop("_pending_resume", None)
            st.session_state.pop("_pending_resume_list", None)
            st.session_state.pop("_force_resume", None)
            st.rerun()

    for pending in sessions_list:
        if not pending:
            continue
        current_step = pending["current_step"]
        step_data_resume = pending.get("step_data", {}) or {}
        artist_name = (
            step_data_resume.get("searchTerm", "") if isinstance(step_data_resume, dict) else ""
        ) or _fallback_term or "Catalogue"
        search_mode = step_data_resume.get("searchMode") if isinstance(step_data_resume, dict) else None
        display_name = f"{artist_name} ({search_mode})" if search_mode in ("Artist", "Label") else artist_name
        initials = "".join([w[0].upper() for w in artist_name.split()[:2]]) if artist_name else "CA"
        is_returning = current_step > MIN_STEP or bool(step_data_resume)
        raw_updated = pending.get("updated_at", "")
        if raw_updated:
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(str(raw_updated).replace("Z", "+00:00")) if isinstance(raw_updated, str) else raw_updated
                updated_label = dt.strftime("%b %d, %Y, %-I:%M %p")
            except Exception:
                updated_label = str(raw_updated)
        else:
            updated_label = "Date unavailable"
        sid = pending["session_id"]
        catalog_card = st.container(border=True)
        catalog_card.markdown('<span class="catalog-card-marker" style="display:none"></span>', unsafe_allow_html=True)

        # Keep the catalogue identity and actions on one compact card row.
        info_col, btn_a, btn_b, btn_c = catalog_card.columns([3, 1, 1, 1], gap="small")
        with info_col:
            st.markdown(
                f"""
                <div class="resume-session-header">
                    <div class="resume-session-avatar">{initials}</div>
                    <div class="resume-session-info">
                        <div class="name">{display_name}</div>
                        <div class="desc">Catalogue valuation {'in progress' if is_returning else 'ready'}</div>
                        <div class="updated">Last updated: {updated_label}</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with btn_a:
            st.markdown('<span class="rs-btnrow" style="display:none"></span>', unsafe_allow_html=True)
            _marker("continue")
            if st.button(
                "Continue",
                use_container_width=True,
                key=f"resume_continue_{sid}",
                on_click=_mark_ui_transition,
            ):
                st.session_state["welcomed"] = True
                st.session_state["session_id"] = pending["session_id"]
                st.session_state["current_step"] = pending["current_step"]
                st.session_state["step_data"] = pending["step_data"]
                st.session_state["_login_transition"] = True
                st.session_state.pop("_pending_resume", None)
                st.session_state.pop("_pending_resume_list", None)
                st.session_state.pop("_force_resume", None)
                st.rerun()
        with btn_b:
            _marker("restart")
            if st.button(
                "Restart",
                use_container_width=True,
                key=f"resume_restart_{sid}",
                on_click=_mark_ui_transition,
            ):
                save_checkpoint(session, sid, 1, {})
                st.session_state["welcomed"] = True
                st.session_state["session_id"] = sid
                st.session_state["current_step"] = 1
                st.session_state["step_data"] = {}
                st.session_state["_login_transition"] = True
                st.session_state.pop("_pending_resume", None)
                st.session_state.pop("_pending_resume_list", None)
                st.session_state.pop("_force_resume", None)
                st.rerun()
        with btn_c:
            _marker("remove")
            if st.button(
                "Remove",
                use_container_width=True,
                key=f"resume_remove_{sid}",
                on_click=_mark_ui_transition,
            ):
                complete_session(session, sid)
                remaining = [s for s in sessions_list if s and s["session_id"] != sid]
                if remaining:
                    st.session_state["_pending_resume_list"] = remaining
                    st.session_state["_pending_resume"] = remaining[0]
                else:
                    new_sess = create_new_session(session, email)
                    st.session_state["welcomed"] = True
                    st.session_state["session_id"] = new_sess["session_id"]
                    st.session_state["current_step"] = new_sess["current_step"]
                    st.session_state["step_data"] = new_sess.get("step_data", {})
                    st.session_state["_login_transition"] = True
                    st.session_state.pop("_pending_resume", None)
                    st.session_state.pop("_pending_resume_list", None)
                st.session_state.pop("_force_resume", None)
                st.rerun()

        # Progress remains beneath the compact identity/action row.
        catalog_card.markdown(
            f"""
            <div class="resume-session-card">
                <div class="resume-progress-summary">
                    <span>Overall progress</span>
                    <span>{current_step} of {MAX_STEP} steps</span>
                </div>
                <div class="resume-progress-pills">{_pills_html(current_step)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Gap between stacked session cards
        st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)



