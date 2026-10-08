"""Who is using the workbench.

``APP_AUTH_MODE`` picks how the user proves who they are:

* ``oidc`` (default): the company's OpenID Connect provider through ``st.login()``. The email is read
  from the signed identity cookie (``st.user``). Setup: ``.streamlit/secrets.toml.example``.
* ``otp``: a code emailed to an allow-listed address (see otp.py). A signed token in a cookie keeps the
  user signed in across the page reloads this app does on every step.
* ``dev``: the old "type any email" form, for local development only.

In ``oidc`` and ``otp`` the email can't be typed in or edited into the URL to become someone else.
"""

import json
import os

import streamlit as st
import streamlit.components.v1 as components

from session_manager import is_valid_email

COOKIE_NAME = "wb_auth"


def mode() -> str:
    """"dev" or "otp" only when set explicitly; anything else (including a typo) means "oidc"."""
    value = os.getenv("APP_AUTH_MODE", "oidc").strip().lower()
    return value if value in ("dev", "otp") else "oidc"


def is_dev() -> bool:
    return mode() == "dev"


def is_otp() -> bool:
    return mode() == "otp"


def is_oidc() -> bool:
    return mode() == "oidc"


def oidc_configured() -> bool:
    """Whether ``[auth]`` is present in the Streamlit secrets (``st.login()`` fails without it)."""
    try:
        return "auth" in st.secrets
    except Exception:
        return False


def is_signed_in() -> bool:
    """Signed in with the OIDC provider (whether or not it supplied a usable email)."""
    try:
        return bool(st.user.is_logged_in)
    except Exception:
        return False


def verified_email() -> str:
    """The signed-in user's lower-cased email, or "" when nobody is signed in or it can't be trusted."""
    if is_otp():
        import otp

        try:
            email = otp.read_token(st.context.cookies.get(COOKIE_NAME, ""))
        except Exception:
            return ""
        return email if otp.is_allowed(email) else ""      # taking someone off the allow-list ends their session
    if not is_signed_in():
        return ""
    try:
        email = str(getattr(st.user, "email", "") or "").strip().lower()
        if st.user.get("email_verified") is False:
            return ""
    except Exception:
        return ""
    return email if is_valid_email(email) else ""


def _run_in_parent(script: str) -> None:
    """Run ``script`` against the top page (the components iframe is same-origin with it).

    The iframe is sandboxed without allow-top-navigation, so it can't send the page to a new URL
    (location.replace/assign are blocked). Strip the URL with history.replaceState and reload() instead.
    """
    components.html(f"<script>{script}</script>", height=0)


def set_session_cookie(token: str, max_age: int) -> None:
    """Store the signed token in the browser, then reload the app without any URL parameters."""
    _run_in_parent(
        "var p = window.parent;"
        f"p.document.cookie = {json.dumps(COOKIE_NAME)} + '=' + {json.dumps(token)} + '; Path=/; Max-Age={int(max_age)}; SameSite=Lax'"
        " + (p.location.protocol === 'https:' ? '; Secure' : '');"
        "p.history.replaceState(null, '', p.location.pathname); p.location.reload();"
    )


def clear_session_cookie() -> None:
    """Remove the token from the browser and go back to the sign-in screen."""
    _run_in_parent(
        "var p = window.parent;"
        f"p.document.cookie = {json.dumps(COOKIE_NAME)} + '=; Path=/; Max-Age=0; SameSite=Lax';"
        "p.history.replaceState(null, '', p.location.pathname); p.location.reload();"
    )
