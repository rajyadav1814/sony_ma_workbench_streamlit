"""Email one-time-code sign-in (``APP_AUTH_MODE=otp``).

A code only proves that someone can read an inbox, not that they should be let in. With no allow-list
(``APP_ALLOWED_EMAILS`` / ``APP_ALLOWED_DOMAINS``) any address that can receive the code may sign in;
set one to restrict access. Codes are stored hashed in
``{APP_SCHEMA}.AUTH_OTP``; a successful check returns a signed, expiring token that auth.py keeps in a
browser cookie.

Environment: APP_AUTH_SECRET (32+ characters, signs tokens and hashes codes), APP_ALLOWED_EMAILS,
APP_ALLOWED_DOMAINS, SMTP_HOST, SMTP_PORT (587; 465 uses SSL), SMTP_USER, SMTP_PASSWORD, SMTP_FROM,
APP_OTP_TTL_SECONDS (600), APP_SESSION_HOURS (720, i.e. 30 days).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import secrets
import smtplib
import time
from email.message import EmailMessage

from config import DB
from session_manager import is_valid_email

log = logging.getLogger(__name__)

CODE_DIGITS = 6
MAX_ATTEMPTS = 5
RESEND_SECONDS = 60


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


def code_ttl() -> int:
    return _int_env("APP_OTP_TTL_SECONDS", 600)


def session_seconds() -> int:
    return _int_env("APP_SESSION_HOURS", 720) * 3600


def _secret() -> bytes:
    value = os.getenv("APP_AUTH_SECRET", "").strip()
    return value.encode() if len(value) >= 32 else b""


def _csv(name: str) -> set[str]:
    return {item.strip().lower() for item in os.getenv(name, "").split(",") if item.strip()}


def is_allowed(email: str) -> bool:
    """A valid address that is on the allow-list. With no list configured every valid address is allowed."""
    email = (email or "").strip().lower()
    if not is_valid_email(email):
        return False
    if not (_csv("APP_ALLOWED_EMAILS") or _csv("APP_ALLOWED_DOMAINS")):
        return True
    return email in _csv("APP_ALLOWED_EMAILS") or email.rsplit("@", 1)[1] in {
        d.lstrip("@") for d in _csv("APP_ALLOWED_DOMAINS")
    }


def config_problem() -> str:
    """What is missing from the setup, or "" when sign-in by code can work."""
    if not _secret():
        return "APP_AUTH_SECRET must be set to a random string of at least 32 characters."
    if not os.getenv("SMTP_HOST", "").strip() or not (os.getenv("SMTP_FROM") or os.getenv("SMTP_USER") or "").strip():
        return "SMTP_HOST and SMTP_FROM (or SMTP_USER) must be set so codes can be emailed."
    return ""


# ─── signed session token ────────────────────────────────────────────────────
def _sign(payload: str) -> str:
    return hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()


def make_token(email: str, now: float | None = None) -> str:
    expires = int((now if now is not None else time.time()) + session_seconds())
    payload = base64.urlsafe_b64encode(f"{expires}:{email.strip().lower()}".encode()).decode().rstrip("=")
    return f"{payload}.{_sign(payload)}"


def read_token(token: str, now: float | None = None) -> str:
    """The email in a valid, unexpired token, else ""."""
    if not token or "." not in token or not _secret():
        return ""
    payload, _, signature = token.rpartition(".")
    if not hmac.compare_digest(signature, _sign(payload)):
        return ""
    try:
        expires, _, email = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)).decode().partition(":")
        if int(expires) < (now if now is not None else time.time()):
            return ""
    except (ValueError, UnicodeDecodeError):
        return ""
    return email


# ─── one-time codes ──────────────────────────────────────────────────────────
_table_ready = False


def _db():
    """A shared connection for the sign-in table (the user is not known yet)."""
    global _table_ready
    from postgres_connection import get_connection

    session = get_connection("__auth__").session()
    if not _table_ready:
        session.sql(
            f"""CREATE TABLE IF NOT EXISTS {DB}.AUTH_OTP (
                EMAIL VARCHAR(320) PRIMARY KEY,
                CODE_HASH VARCHAR(64) NOT NULL,
                EXPIRES_AT DOUBLE PRECISION NOT NULL,
                SENT_AT DOUBLE PRECISION NOT NULL,
                ATTEMPTS INTEGER NOT NULL DEFAULT 0
            )"""
        ).collect()
        _table_ready = True
    return session


def _code_hash(email: str, code: str) -> str:
    return _sign(f"{email}:{code}")


def _send_email(to: str, code: str) -> None:
    sender = (os.getenv("SMTP_FROM") or os.getenv("SMTP_USER") or "").strip()
    message = EmailMessage()
    message["Subject"] = f"Your M&A Workbench sign-in code: {code}"
    message["From"] = sender
    message["To"] = to
    message.set_content(
        f"Your sign-in code is {code}\n\n"
        f"It expires in {code_ttl() // 60} minutes. If you did not ask for it, ignore this email."
    )
    host, port = os.getenv("SMTP_HOST", "").strip(), _int_env("SMTP_PORT", 587)
    user, password = os.getenv("SMTP_USER", "").strip(), os.getenv("SMTP_PASSWORD", "")
    if port == 465:
        server = smtplib.SMTP_SSL(host, port, timeout=15)
    else:
        server = smtplib.SMTP(host, port, timeout=15)
    with server:
        if port != 465:
            server.starttls()
        if user:
            server.login(user, password)
        server.send_message(message)


def request_code(email: str) -> tuple[bool, str]:
    """Email a new code if ``email`` is allowed. Returns (ok, message).

    The answer is the same for allowed and not-allowed addresses, so the form can't be used to find
    out who has access. Only a setup or delivery failure is reported as an error (with its message).
    """
    email = (email or "").strip().lower()
    if not is_valid_email(email):
        return False, "Please enter a valid email address."
    problem = config_problem()
    if problem:
        return False, f"Sign-in is not set up: {problem}"
    if not is_allowed(email):
        return True, ""
    try:
        session = _db()
        now = time.time()
        rows = session.sql(f"SELECT SENT_AT FROM {DB}.AUTH_OTP WHERE EMAIL = :1", params=[email]).collect()
        if rows and now - float(rows[0]["SENT_AT"]) < RESEND_SECONDS:
            return True, ""      # a code went out a moment ago; don't let this become a mail cannon
        code = f"{secrets.randbelow(10 ** CODE_DIGITS):0{CODE_DIGITS}d}"
        session.sql(
            f"""INSERT INTO {DB}.AUTH_OTP (EMAIL, CODE_HASH, EXPIRES_AT, SENT_AT, ATTEMPTS)
                VALUES (:1, :2, :3, :4, 0)
                ON CONFLICT (EMAIL) DO UPDATE SET CODE_HASH = EXCLUDED.CODE_HASH,
                    EXPIRES_AT = EXCLUDED.EXPIRES_AT, SENT_AT = EXCLUDED.SENT_AT, ATTEMPTS = 0""",
            params=[email, _code_hash(email, code), now + code_ttl(), now],
        ).collect()
        try:
            _send_email(email, code)
        except Exception:
            session.sql(f"DELETE FROM {DB}.AUTH_OTP WHERE EMAIL = :1", params=[email]).collect()
            raise
    except Exception:
        log.exception("Could not send a sign-in code")
        return False, "The code could not be sent. Please try again, or contact the administrator."
    return True, ""


def verify_code(email: str, code: str) -> str:
    """A session token when ``code`` is the live code for ``email``, else "". Wrong guesses are counted."""
    email = (email or "").strip().lower()
    code = "".join(ch for ch in (code or "") if ch.isdigit())
    if not is_allowed(email) or len(code) != CODE_DIGITS or config_problem():
        return ""
    try:
        session = _db()
        # Counting the attempt and reading the hash are one statement, so parallel guesses can't dodge the limit.
        rows = session.sql(
            f"""UPDATE {DB}.AUTH_OTP SET ATTEMPTS = ATTEMPTS + 1
                WHERE EMAIL = :1 AND ATTEMPTS < :2 AND EXPIRES_AT > :3
                RETURNING CODE_HASH""",
            params=[email, MAX_ATTEMPTS, time.time()],
        ).collect()
        if not rows or not hmac.compare_digest(str(rows[0]["CODE_HASH"]), _code_hash(email, code)):
            return ""
        session.sql(f"DELETE FROM {DB}.AUTH_OTP WHERE EMAIL = :1", params=[email]).collect()
    except Exception:
        log.exception("Could not check a sign-in code")
        return ""
    return make_token(email)
