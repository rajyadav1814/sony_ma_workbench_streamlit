"""Welcome and Resume screens rendered in Streamlit (before the HTML workbench)."""

import base64
import html
import json
from pathlib import Path

import streamlit as st
import auth
from config import MAX_STEP, MIN_STEP, STEP_LABELS
from theme import LIGHT_CSS, THEME_CSS, render_theme_toggle
from session_manager import (
    is_valid_email,
)


def render_welcome_screen(session, backdrop=False):
    """Render the welcome / login form and process its submit callback.

    backdrop=True is used while the login loader is shown: the CSS is emitted inline
    (st.markdown) so it is removed together with the loader slot. st.html puts it in a
    page-level container that outlives the slot and would restyle the next screen.
    """
    def _handle_login_submit():
        clean_email = st.session_state.get("welcome_email", "").strip().lower()
        if not clean_email:
            st.session_state["_welcome_error"] = "Please enter your email to continue."
            return
        if not is_valid_email(clean_email):
            st.session_state["_welcome_error"] = "Please enter a valid email address."
            return

        st.session_state.pop("_welcome_error", None)
        st.session_state["user_email"] = clean_email
        st.session_state["_pending_login"] = True
        st.session_state["_login_transition"] = True

    welcome_styles = """
        <style>
            """ + LIGHT_CSS + """
            [data-testid="stAppViewContainer"] {
                background:
                    radial-gradient(900px 520px at 88% -8%, rgba(225,38,28,0.09), transparent 62%),
                    radial-gradient(800px 500px at -4% 108%, rgba(20,18,16,0.07), transparent 62%),
                    var(--wb-bg) !important;
            }
            div.block-container {
                padding: 9vh 20px 40px !important;
                max-width: 100% !important;
            }

            /* One wide card, split in two: a dark brand panel on the left, the sign-in form on the right. */
            CARD {
                position: relative;
                width: 100% !important;
                max-width: 1020px !important;
                margin: 0 auto !important;
                padding: 0 !important;
                gap: 0 !important;
                background: var(--wb-surface) !important;
                border-radius: 24px !important;
                box-shadow: 0 2px 4px rgba(20,18,16,0.06), 0 40px 80px -24px rgba(20,18,16,0.35);
                overflow: hidden !important;
            }
            [data-testid="stHorizontalBlock"]:has(.wl-hero) {
                gap: 0 !important;
                align-items: stretch !important;
            }

            /* Left: brand panel */
            COL_HERO {
                position: relative;
                min-width: 300px;
                padding: 48px 46px 44px !important;
                color: #F4F1EA;
                background:
                    radial-gradient(560px 380px at 105% -5%, rgba(225,38,28,0.75), transparent 62%),
                    radial-gradient(420px 300px at -10% 110%, rgba(225,38,28,0.28), transparent 62%),
                    #0B0B0B;
                overflow: hidden;
            }
            COL_HERO [data-testid="stVerticalBlock"] { gap: 0 !important; height: 100%; position: relative; z-index: 1; }
            /* Halftone dot sphere (the Sony Music Latin logo motif) glowing behind the text */
            COL_HERO::after {
                content: "";
                position: absolute;
                width: 400px; height: 400px;
                right: -120px; top: -70px;
                border-radius: 50%;
                background: radial-gradient(circle, #FF3B30 1.7px, transparent 2.2px) 0 0 / 13px 13px;
                -webkit-mask-image: radial-gradient(circle at 42% 58%, #000 0%, rgba(0,0,0,0.5) 40%, transparent 68%);
                mask-image: radial-gradient(circle at 42% 58%, #000 0%, rgba(0,0,0,0.5) 40%, transparent 68%);
                filter: drop-shadow(0 0 14px rgba(255,59,48,0.55));
                pointer-events: none;
                z-index: 0;
            }
            .wl-brand { display: flex; align-items: center; gap: 12px; margin-bottom: 44px; }
            .wl-brand img { height: 42px; width: 42px; object-fit: contain; }
            .wl-brand-text { display: flex; flex-direction: column; line-height: 1.25; }
            .wl-brand-name { font-size: 12px; font-weight: 700; letter-spacing: 3px; color: #FFFFFF; }
            .wl-brand-sub  { font-size: 10px; font-weight: 600; letter-spacing: 3px; color: rgba(255,255,255,0.55); }
            .wl-eyebrow {
                display: inline-block; font-size: 11px; font-weight: 700; letter-spacing: 1.6px; text-transform: uppercase;
                color: #FF8C85; background: rgba(225,38,28,0.16); border: 1px solid rgba(255,140,133,0.3);
                padding: 5px 11px; border-radius: 20px; margin-bottom: 18px;
            }
            .wl-title {
                font-size: 48px; font-weight: 800; line-height: 1.04; letter-spacing: -1px;
                color: #FFFFFF; margin: 0 0 14px;
            }
            .wl-title span { color: #FF5A4F; }
            .wl-lede { font-size: 15px; line-height: 1.65; color: rgba(244,241,234,0.72); margin: 0 0 30px; max-width: 340px; }
            .wl-points { list-style: none !important; margin: 0 0 34px !important; padding: 0 !important; }
            .wl-points li {
                display: flex; align-items: center; gap: 14px; margin: 0 !important; padding: 7px 0 !important;
                font-size: 15px; font-weight: 500; color: #F4F1EA;
            }
            .wl-points .n {
                flex: 0 0 30px; height: 30px; border-radius: 9px;
                display: inline-flex; align-items: center; justify-content: center;
                font-size: 13px; font-weight: 700; color: #FFFFFF;
                background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.16);
            }
            /* Equaliser motif */
            .wl-eq { display: flex; align-items: flex-end; justify-content: space-between; gap: 5px; height: 54px; opacity: 0.95; }
            .wl-eq i { display: block; flex: 1 1 0; max-width: 7px; border-radius: 3px; background: linear-gradient(180deg, #FF5A4F, #E1261C); animation: wl-eq 1.6s ease-in-out infinite; }
            .wl-eq i:nth-child(4n) { background: linear-gradient(180deg, #FFFFFF, #9A9A9A); }
            @keyframes wl-eq { 0%,100% { transform: scaleY(0.35); } 50% { transform: scaleY(1); } }
            .wl-eq i { transform-origin: bottom; }
            .wl-eq i:nth-child(12n+1){height:60%;animation-delay:-.1s} .wl-eq i:nth-child(12n+2){height:90%;animation-delay:-.5s}
            .wl-eq i:nth-child(12n+3){height:45%;animation-delay:-.9s} .wl-eq i:nth-child(12n+4){height:100%;animation-delay:-.3s}
            .wl-eq i:nth-child(12n+5){height:70%;animation-delay:-1.2s} .wl-eq i:nth-child(12n+6){height:50%;animation-delay:-.7s}
            .wl-eq i:nth-child(12n+7){height:85%;animation-delay:-1.4s} .wl-eq i:nth-child(12n+8){height:40%;animation-delay:-.2s}
            .wl-eq i:nth-child(12n+9){height:75%;animation-delay:-1s} .wl-eq i:nth-child(12n+10){height:55%;animation-delay:-.6s}
            .wl-eq i:nth-child(12n+11){height:95%;animation-delay:-1.3s} .wl-eq i:nth-child(12n+12){height:45%;animation-delay:-.4s}

            /* Right: sign-in */
            COL_FORM { padding: 112px 52px 56px !important; }
            COL_FORM [data-testid="stVerticalBlock"] { gap: 0 !important; height: 100%; justify-content: center; }
            .wl-form-title { font-size: 26px; font-weight: 800; letter-spacing: -0.4px; color: var(--wb-text); margin: 0 0 6px; }
            .wl-form-sub { font-size: 14.5px; color: var(--wb-text-mute); margin: 0 0 28px; }

            /* Form: sits inside the card, full width. */
            [data-testid="stForm"] { border: 0 !important; padding: 0 !important; width: 100% !important; }
            [data-testid="stTextInput"] { width: 100% !important; }
            [data-testid="stTextInput"] label p {
                color: var(--wb-text) !important; font-size: 13px !important; font-weight: 600 !important;
            }
            /* The root element carries the field's border so the input never double-draws it. */
            [data-testid="stTextInputRootElement"] {
                border: 1px solid var(--wb-input-border) !important;
                border-radius: 10px !important;
                background: var(--wb-input-bg) !important;
                box-shadow: none !important;
                overflow: hidden;
                transition: border-color .15s, box-shadow .15s;
            }
            [data-testid="stTextInputRootElement"]:focus-within {
                border-color: #E1261C !important;
                box-shadow: 0 0 0 4px rgba(225,38,28,0.14) !important;
            }
            [data-testid="stTextInput"] input {
                display: block !important;
                box-sizing: border-box !important;
                width: 100% !important;
                height: 48px !important;
                min-height: 48px !important;
                appearance: none !important;
                color-scheme: var(--wb-scheme) !important;
                color: var(--wb-text) !important;
                background: var(--wb-input-bg) !important;
                border: 0 !important;
                border-radius: 0 !important;
                padding: 10px 14px !important;
                font: 400 16px/1.4 Inter, Arial, sans-serif !important;
                outline: none !important;
                box-shadow: none !important;
                transition: border-color .15s, box-shadow .15s;
            }
            [data-testid="stTextInput"] input:autofill,
            [data-testid="stTextInput"] input:-webkit-autofill,
            [data-testid="stTextInput"] input:-webkit-autofill:hover,
            [data-testid="stTextInput"] input:-webkit-autofill:focus,
            [data-testid="stTextInput"] input:-webkit-autofill:active {
                -webkit-text-fill-color: var(--wb-text) !important;
                -webkit-box-shadow: 0 0 0 1000px var(--wb-input-bg) inset !important;
                box-shadow: 0 0 0 1000px var(--wb-input-bg) inset !important;
            }
            [data-testid="stTextInput"] input::placeholder { color: #9ca3af !important; font-size: 16px !important; }

            [data-testid="stFormSubmitButton"] { width: 100% !important; margin-top: 18px !important; }
            [data-testid="stFormSubmitButton"] button {
                width: 100% !important;
                min-height: 48px !important;
                border-radius: 10px !important;
                font-size: 15px !important;
                font-weight: 700 !important;
                letter-spacing: 0.2px;
                background: #E1261C !important;
                border-color: #E1261C !important;
                color: #FFFFFF !important;
                box-shadow: 0 8px 18px -8px rgba(225,38,28,0.7);
                transition: background .15s, transform .15s;
            }
            [data-testid="stFormSubmitButton"] button:hover {
                background: #C51616 !important;
                border-color: #C51616 !important;
                transform: translateY(-1px);
            }

            /* Plain text and the secondary buttons in the sign-in column. Streamlit paints these for the
               browser's own light/dark setting, which left them white-on-white on a dark-mode browser. */
            .wl-code-note { font-size: 14.5px; line-height: 1.5; color: var(--wb-text) !important; margin: 0 0 14px; }
            .wl-code-note strong { color: var(--wb-text) !important; font-weight: 700; word-break: break-all; }
            [data-testid="stColumn"]:has(.wl-formcol) [data-testid="stButton"] button,
            [data-testid="column"]:has(.wl-formcol) [data-testid="stButton"] button {
                background: var(--wb-surface) !important;
                border: 1px solid var(--wb-input-border) !important;
                color: var(--wb-text) !important;
                border-radius: 10px !important;
                min-height: 42px !important;
                box-shadow: none !important;
                transition: border-color .15s, color .15s;
            }
            [data-testid="stColumn"]:has(.wl-formcol) [data-testid="stButton"] button *,
            [data-testid="column"]:has(.wl-formcol) [data-testid="stButton"] button * {
                color: inherit !important; font-size: 13.5px !important; font-weight: 600 !important;
            }
            [data-testid="stColumn"]:has(.wl-formcol) [data-testid="stButton"] button:hover,
            [data-testid="column"]:has(.wl-formcol) [data-testid="stButton"] button:hover {
                border-color: #E1261C !important; color: #E1261C !important;
            }

            /* Spinner shown in the form area while a code is sent or checked. */
            .wl-loading { display: flex; flex-direction: column; align-items: center; gap: 14px; padding: 36px 0;
                          font-size: 14.5px; font-weight: 600; color: var(--wb-text); }
            .wl-spin { width: 34px; height: 34px; border: 4px solid #E5E1D8; border-top-color: #E1261C;
                       border-radius: 50%; animation: wl-spin .8s linear infinite; }
            @keyframes wl-spin { to { transform: rotate(360deg); } }

            /* Validation messages use a distinct, readable error treatment. */
            [data-testid="stAlert"] {
                width: 100% !important;
                margin-top: 14px !important;
                background: var(--wb-alert-bg) !important;
                border: 1px solid var(--wb-alert-border) !important;
                border-radius: 10px !important;
                color: var(--wb-alert-text) !important;
                padding: 12px 14px !important;
            }
            [data-testid="stAlert"] [data-testid="stAlertContainer"] {
                background: transparent !important; padding: 0 !important;
            }
            [data-testid="stAlert"] *,
            [data-testid="stAlert"] p,
            [data-testid="stAlert"] [data-testid="stMarkdownContainer"] {
                color: var(--wb-alert-text) !important;
                opacity: 1 !important;
            }
            @media (max-width: 760px) {
                COL_HERO { padding: 32px 26px 28px !important; min-width: 0; }
                COL_FORM { padding: 32px 26px 34px !important; }
                .wl-title { font-size: 36px; }
                .wl-brand { margin-bottom: 26px; }
                COL_HERO::after { display: none; }
                .wl-eq { display: none; }
            }
        </style>
        """
    # Style the card by the block that directly holds the marker, so it does not depend on
    # the version-specific test ids of bordered containers.
    _card = [
        '[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .wl-marker)',
        '[data-testid="stVerticalBlock"]:has(> [data-testid="element-container"] .wl-marker)',
    ]
    welcome_styles = welcome_styles.replace("CARD", ",".join(_card))
    _hero = ['[data-testid="stColumn"]:has(.wl-hero)', '[data-testid="column"]:has(.wl-hero)']
    welcome_styles = welcome_styles.replace("COL_HERO::after", ",".join(h + "::after" for h in _hero))
    welcome_styles = welcome_styles.replace(
        "COL_HERO", '[data-testid="stColumn"]:has(.wl-hero),[data-testid="column"]:has(.wl-hero)'
    ).replace(
        "COL_FORM", '[data-testid="stColumn"]:has(.wl-formcol),[data-testid="column"]:has(.wl-formcol)'
    )
    if backdrop:
        # While the loader is up, Streamlit keeps the previous run's card on screen (marked stale)
        # until the run ends, which shows a second card under this backdrop copy. Hide it.
        welcome_styles = welcome_styles.replace(
            "</style>",
            ",".join(
                f'[data-testid="stVerticalBlock"]:has(> [data-testid="{c}"][data-stale="true"] .wl-marker)'
                for c in ("stElementContainer", "element-container")
            ) + " { display: none !important; }</style>",
        )
    if hasattr(st, "html") and not backdrop:
        st.html(welcome_styles)
    else:
        st.markdown(welcome_styles, unsafe_allow_html=True)

    logo_b64 = _logo_b64()
    logo_img = f'<img src="data:image/png;base64,{logo_b64}" alt="Sony Music"/>' if logo_b64 else ""
    with st.container():
        st.markdown('<span class="wl-marker" style="display:none"></span>', unsafe_allow_html=True)
        hero_col, form_col = st.columns([1.15, 1], gap="small")

        with hero_col:
            st.markdown(
                '<span class="wl-hero" style="display:none"></span>'
                f'<div class="wl-brand">{logo_img}<div class="wl-brand-text">'
                '<span class="wl-brand-name">SONY MUSIC</span><span class="wl-brand-sub">LATIN</span></div></div>'
                '<div><span class="wl-eyebrow">M&amp;A Catalogue Valuation Platform</span></div>'
                '<div class="wl-title">Welcome<span>.</span></div>'
                '<p class="wl-lede">Explore catalogue data, run valuation scenarios and analyse growth trends across the portfolio.</p>'
                '<ul class="wl-points">'
                '<li><span class="n">1</span>Explore catalogue data</li>'
                '<li><span class="n">2</span>Run valuation scenarios</li>'
                '<li><span class="n">3</span>Analyse growth trends</li>'
                '</ul>'
                '<div class="wl-eq">' + "<i></i>" * 36 + '</div>',
                unsafe_allow_html=True,
            )

        with form_col:
            st.markdown(
                '<span class="wl-formcol" style="display:none"></span>'
                '<div class="wl-form-title">Get started</div>'
                '<div class="wl-form-sub">'
                + {
                    "dev": "Enter your work email to continue.",
                    "otp": "Enter your work email and we'll send you a sign-in code.",
                }.get(auth.mode(), "Sign in with your company account to continue.")
                + '</div>',
                unsafe_allow_html=True,
            )
            if auth.is_dev():
                with st.form("welcome_login_form", border=False):
                    st.text_input(
                        "Email",
                        placeholder="you@sonymusic.com",
                        key="welcome_email",
                    )
                    st.form_submit_button(
                        "Get Started",
                        type="primary",
                        use_container_width=True,
                        on_click=_handle_login_submit,
                    )
            elif auth.verified_email():
                # Already signed in: this is the welcome screen kept behind the "Signing in..." loader.
                st.caption("Signing you in…")
            elif auth.is_otp():
                _render_otp_form()
            elif auth.is_signed_in():
                # Signed in with the provider, but it gave no verified email address to key the user's data on.
                st.error("Your account did not provide a verified email address, so you can't be signed in.")
                st.button("Sign out", key=f"signout_btn{'_bd' if backdrop else ''}", on_click=st.logout)
            elif not auth.oidc_configured():
                st.error(
                    "Sign-in is not configured. Add an [auth] section to .streamlit/secrets.toml "
                    "(see .streamlit/secrets.toml.example)."
                )
            else:
                st.button(
                    "Sign in",
                    key=f"signin_btn{'_bd' if backdrop else ''}",
                    type="primary",
                    use_container_width=True,
                    on_click=st.login,
                )

            welcome_error = st.session_state.get("_welcome_error")
            if welcome_error:
                if "valid email" in welcome_error:
                    st.error(welcome_error)
                else:
                    st.warning(welcome_error)


def _inline_loader_html(text: str) -> str:
    """A spinner for the sign-in card's form area (styles in render_welcome_screen)."""
    return (
        '<div class="wl-loading" role="status" aria-live="polite"><div class="wl-spin" aria-hidden="true"></div>'
        f'<div>{html.escape(text)}</div></div>'
    )


def _run_otp_action(action: dict):
    """Do the slow part of the sign-in (database + email) while the card shows a spinner, then redraw.

    The buttons' callbacks run before the page is redrawn and only record what was asked, so the card
    is already back on screen (with this spinner in place of the form) while the work happens.
    """
    import otp

    kind, email = action["kind"], action["email"]
    slot = st.empty()
    slot.markdown(_inline_loader_html("Checking code…" if kind == "verify" else "Sending code…"), unsafe_allow_html=True)
    if kind == "verify":
        token = otp.verify_code(email, action["code"])
        if token:
            slot.markdown(_inline_loader_html("Signing you in…"), unsafe_allow_html=True)
            auth.set_session_cookie(token, otp.session_seconds())   # stores the cookie, then reloads the page
            st.stop()
        st.session_state["_otp_error"] = "That code is not right or has expired. Check it, or ask for a new one."
    else:
        ok, message = otp.request_code(email)
        if ok:
            st.session_state["_otp_email"] = email.strip().lower()
            st.session_state.pop("_otp_error", None)
        else:
            st.session_state["_otp_error"] = message
    st.rerun()


def _render_otp_form():
    """Sign in by emailed code: ask for the email, then for the 6-digit code that was sent to it."""
    import otp

    def _send_code():
        st.session_state["_otp_action"] = {"kind": "send", "email": st.session_state.get("otp_email_input", "")}

    def _check_code():
        st.session_state["_otp_action"] = {
            "kind": "verify",
            "email": st.session_state.get("_otp_email", ""),
            "code": st.session_state.get("otp_code_input", ""),
        }

    def _resend_code():
        st.session_state["_otp_action"] = {"kind": "resend", "email": st.session_state.get("_otp_email", "")}

    def _use_other_email():
        for key in ("_otp_email", "_otp_error"):
            st.session_state.pop(key, None)

    action = st.session_state.pop("_otp_action", None)
    if action:
        _run_otp_action(action)    # always ends in st.rerun() or st.stop()

    pending_email = st.session_state.get("_otp_email")
    if not pending_email:
        with st.form("otp_email_form", border=False):
            st.text_input("Email", placeholder="you@sonymusic.com", key="otp_email_input")
            st.form_submit_button("Send code", type="primary", use_container_width=True, on_click=_send_code)
    else:
        st.markdown(
            f'<div class="wl-code-note">Enter the {otp.CODE_DIGITS}-digit code sent to <strong>{html.escape(pending_email)}</strong>.</div>',
            unsafe_allow_html=True,
        )
        with st.form("otp_code_form", border=False):
            st.text_input("Sign-in code", max_chars=otp.CODE_DIGITS, key="otp_code_input")
            st.form_submit_button("Sign in", type="primary", use_container_width=True, on_click=_check_code)
        col_resend, col_other = st.columns(2)
        col_resend.button("Send a new code", key="otp_resend", on_click=_resend_code)
        col_other.button("Use a different email", key="otp_other", on_click=_use_other_email)
    error = st.session_state.get("_otp_error")
    if error:
        st.error(error)


def _logo_b64():
    """Sony Music logo as base64 for inline display ('' if the file is missing)."""
    path = Path(__file__).parent.parent / "sonymusic.png"
    return base64.b64encode(path.read_bytes()).decode() if path.exists() else ""


def render_resume_screen(session, backdrop=False):
    """Render the 'Welcome back' resume screen matching the Next.js reference design.

    backdrop=True redraws the last rendered list of catalogues (non-interactive, separate
    widget keys) so it can stay visible behind the loader while Streamlit processes a click.
    """

    def _mark_ui_transition():
        st.session_state["_ui_transition"] = True

    def _logout():
        for key in list(st.session_state.keys()):
            if key != "_session_tables_checked":
                del st.session_state[key]
        for key in list(st.query_params.keys()):
            if key.startswith("wb_"):
                del st.query_params[key]
        if auth.is_oidc():
            st.logout()   # drops the identity cookie; without it the next run would sign straight back in
        elif auth.is_otp():
            st.session_state["_otp_clear_cookie"] = True   # app.py removes the browser cookie on the next run

    def _start_new_session():
        st.session_state["_pending_resume_action"] = {"action": "start_new"}
        _mark_ui_transition()

    def _continue_session(pending):
        st.session_state["welcomed"] = True
        st.session_state["session_id"] = pending["session_id"]
        st.session_state["current_step"] = pending["current_step"]
        st.session_state["step_data"] = pending["step_data"]
        st.session_state["_login_transition"] = True
        st.session_state.pop("_pending_resume", None)
        st.session_state.pop("_pending_resume_list", None)
        st.session_state.pop("_force_resume", None)
        _mark_ui_transition()

    def _restart_session(session_id, step_data):
        st.session_state["_pending_resume_action"] = {
            "action": "restart",
            "session_id": session_id,
            "step_data": step_data,
        }
        _mark_ui_transition()

    def _remove_session(session_id, pending_sessions):
        st.session_state["_pending_resume_action"] = {
            "action": "remove",
            "session_id": session_id,
            "pending_sessions": pending_sessions,
        }
        st.session_state.pop("_force_resume", None)
        _mark_ui_transition()

    if backdrop:
        sessions_list = st.session_state.get("_resume_backdrop") or []
    else:
        sessions_list = st.session_state.get("_pending_resume_list")
        if not sessions_list:
            single = st.session_state.get("_pending_resume")
            sessions_list = [single] if single else []
        st.session_state["_resume_backdrop"] = sessions_list
    key_suffix = "_bd" if backdrop else ""

    # Keep the login and this screen in the URL: a browser refresh starts a fresh Streamlit session
    # (session_state is lost), and app.py uses these two params to restore this same screen.
    if not backdrop and st.session_state.get("user_email"):
        st.query_params["wb_email"] = st.session_state["user_email"]
        st.query_params["wb_view"] = "resume"

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
            """ + THEME_CSS + """
            [data-testid="stVerticalBlock"] {gap: 0.8rem !important;}
            [data-testid="stAppViewContainer"] {
                background: var(--wb-bg) !important;
            }
            div.block-container {
                padding: 0px 200px !important; max-width: 100% !important;
                display: flex; align-items: flex-start; justify-content: center;
                min-height: 100vh; max-height: none !important;
                overflow: visible !important;
            }
            .stApp {overflow: visible !important; background: var(--wb-bg);}

            /* Top bar */
            .resume-topbar {
                width: 100%;
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding: 18px 0;
                border-bottom: 1.5px solid var(--wb-line);
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
                color: var(--wb-text);
                padding-bottom: 4px;
                border-bottom: 1px solid var(--wb-line-soft);
                margin-bottom: 3px;
            }
            .resume-brand-sub {
                font-size: 10px;
                font-weight: 600;
                letter-spacing: 2.8px;
                color: var(--wb-text);
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
                color: var(--wb-title);
            }
            .resume-topbar-desc {
                color: var(--wb-text-dim);
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
                color: var(--wb-heading-green);
                font-size: 32px;
                font-weight: 800;
                margin: 0 0 -17px 0;
                text-align: center;
            }
            .resume-heading .subtitle {
                color: var(--wb-text-mute);
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
                border: 5px solid var(--wb-card-border) !important;
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
                color: var(--wb-text);
                font-weight: 600;
                font-size: 18px;
            }
            .resume-session-info .desc {
                color: var(--wb-text-mute);
                font-size: 14px;
                margin-top: 3px;
            }
            .resume-session-info .updated {
                color: var(--wb-text-faint);
                font-size: 12px;
                margin-top: 4px;
            }
            .resume-progress-summary {
                display: flex;
                justify-content: space-between;
                margin: 0 0 10px 0;
                color: var(--wb-text-mute);
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
            .step-pill.future { background: var(--wb-pill-future-bg); color: var(--wb-pill-future-fg); }

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
        pills = ""
        for i, label in enumerate(STEP_LABELS):
            step_num = i + 1
            if step_num < current_step:
                pills += (
                    f'<span class="step-pill completed">'
                    f'&#10003; {step_num} &middot; {label}'
                    f'</span>'
                )
            elif step_num == current_step:
                pills += f'<span class="step-pill current">{step_num} &middot; {label}</span>'
            else:
                pills += f'<span class="step-pill future">{step_num} &middot; {label}</span>'
        return pills

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
        toggle_col, logout_col = st.columns([1, 1], gap="small", vertical_alignment="center")
        with toggle_col:
            if not backdrop:
                render_theme_toggle()
        with logout_col:
            _marker("logout")
            st.button("Logout", key=f"logout_btn{key_suffix}", on_click=_logout)

    st.markdown("<hr style='border:none;border-top:1.5px solid var(--wb-line);margin:0 0 20px 0;'>", unsafe_allow_html=True)

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
        st.button(
            "Start new",
            use_container_width=True,
            key=f"start_new_btn{key_suffix}",
            on_click=_start_new_session,
        )

    for pending in sessions_list:
        if not pending:
            continue
        current_step = pending["current_step"]
        step_data_resume = pending.get("step_data", {}) or {}
        artist_name = (
            step_data_resume.get("searchTerm", "") if isinstance(step_data_resume, dict) else ""
        ) or _fallback_term or "Catalogue"
        search_mode = step_data_resume.get("searchMode") if isinstance(step_data_resume, dict) else None
        is_isrc = search_mode in ("ISRC", "ISRC List") or artist_name.lower().startswith("isrc upload")
        if is_isrc:
            # "ISRC upload: file.xlsx" -> "file.xlsx (ISRC)"
            file_name = artist_name.split(":", 1)[1].strip() if ":" in artist_name else artist_name
            display_name = f"{file_name} (ISRC)" if file_name else "ISRC upload (ISRC)"
            initials = "IS"
        else:
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
        # The search term was typed in the browser and is stored with the session: never trust it as markup.
        display_name = html.escape(display_name)
        initials = html.escape(initials)
        updated_label = html.escape(updated_label)
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
            st.button(
                "Continue",
                use_container_width=True,
                key=f"resume_continue_{sid}{key_suffix}",
                on_click=_continue_session,
                args=(pending,),
            )
        with btn_b:
            _marker("restart")
            st.button(
                "Restart",
                use_container_width=True,
                key=f"resume_restart_{sid}{key_suffix}",
                on_click=_restart_session,
                args=(sid, step_data_resume),
            )
        with btn_c:
            _marker("remove")
            st.button(
                "Remove",
                use_container_width=True,
                key=f"resume_remove_{sid}{key_suffix}",
                on_click=_remove_session,
                args=(sid, sessions_list),
            )

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



