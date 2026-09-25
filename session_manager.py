"""Session progress management backed by PostgreSQL."""

import json
import streamlit as st
from config import DB, MIN_STEP, MAX_STEP, EMAIL_REGEX


def is_valid_email(email: str) -> bool:
    return bool(EMAIL_REGEX.match(email))


def clamp_step(step: int) -> int:
    return max(MIN_STEP, min(MAX_STEP, step))


def _row_to_dict(row) -> dict:
    """Normalize Snowflake and PostgreSQL result rows to uppercase keys."""
    if hasattr(row, "as_dict"):
        raw = row.as_dict()
    elif hasattr(row, "asDict"):
        raw = row.asDict()
    elif isinstance(row, dict):
        raw = row
    else:
        raw = dict(row)
    return {str(key).upper(): value for key, value in raw.items()}


def ensure_session_tables(session):
    """Create SESSION_PROGRESS and USER_PROGRESS tables if they don't exist."""
    try:
        session.sql(
            f"""CREATE TABLE IF NOT EXISTS {DB}.SESSION_PROGRESS (
                SESSION_ID VARCHAR DEFAULT UUID_STRING(),
                USER_EMAIL VARCHAR NOT NULL,
                STATUS VARCHAR DEFAULT 'IN_PROGRESS',
                CURRENT_STEP NUMBER DEFAULT 1,
                STEP_DATA VARIANT DEFAULT PARSE_JSON('{{}}'),
                CREATED_AT TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
                UPDATED_AT TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
            )"""
        ).collect()
        session.sql(
            f"""CREATE TABLE IF NOT EXISTS {DB}.USER_PROGRESS (
                USER_EMAIL VARCHAR(320) NOT NULL PRIMARY KEY,
                CURRENT_STEP NUMBER DEFAULT 1,
                VISITED_STEPS VARCHAR(200) DEFAULT '[]',
                LAST_UPDATED TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
            )"""
        ).collect()
    except Exception:
        pass


def get_open_session(session, email: str) -> dict | None:
    """Check for an IN_PROGRESS session for this user."""
    try:
        # Use literal substitution as Snowpark session.sql() param binding
        # varies across versions (some need :1, some need ?, some need f-string).
        safe_email = email.replace("'", "''")
        rows = session.sql(
            f"""SELECT SESSION_ID, CURRENT_STEP,
                       TO_VARCHAR(STEP_DATA) AS STEP_DATA_STR, UPDATED_AT
                FROM {DB}.SESSION_PROGRESS
                WHERE USER_EMAIL = '{safe_email}' AND STATUS = 'IN_PROGRESS'
                ORDER BY UPDATED_AT DESC
                LIMIT 1"""
        ).collect()
        if rows:
            row_dict = _row_to_dict(rows[0])
            step_data_raw = row_dict.get("STEP_DATA_STR") or row_dict.get("STEP_DATA")
            step_data = {}
            if step_data_raw:
                try:
                    step_data = json.loads(str(step_data_raw))
                except (json.JSONDecodeError, TypeError):
                    step_data = {}
            return {
                "session_id": str(row_dict["SESSION_ID"]),
                "current_step": clamp_step(int(row_dict["CURRENT_STEP"])),
                "step_data": step_data if isinstance(step_data, dict) else {},
                "updated_at": str(row_dict["UPDATED_AT"]),
            }
    except Exception as e:
        st.warning(f"Session lookup failed: {e}")
    return None


def get_open_sessions(session, email: str, limit: int = 20) -> list[dict]:
    """Return ALL IN_PROGRESS sessions for this user (most recently updated first).

    This is the multi-catalogue counterpart to get_open_session(): a user can have
    several catalogue valuations in progress at once (e.g. one per artist), and the
    resume screen should let them pick which one to continue, restart, or remove.
    """
    try:
        safe_email = email.replace("'", "''")
        rows = session.sql(
            f"""SELECT SESSION_ID, CURRENT_STEP,
                       TO_VARCHAR(STEP_DATA) AS STEP_DATA_STR, UPDATED_AT
                FROM {DB}.SESSION_PROGRESS
                WHERE USER_EMAIL = '{safe_email}' AND STATUS = 'IN_PROGRESS'
                ORDER BY UPDATED_AT DESC
                LIMIT {int(limit)}"""
        ).collect()
        sessions = []
        for row in rows:
            row_dict = _row_to_dict(row)
            step_data_raw = row_dict.get("STEP_DATA_STR") or row_dict.get("STEP_DATA")
            step_data = {}
            if step_data_raw:
                try:
                    step_data = json.loads(str(step_data_raw))
                except (json.JSONDecodeError, TypeError):
                    step_data = {}
            sessions.append({
                "session_id": str(row_dict["SESSION_ID"]),
                "current_step": clamp_step(int(row_dict["CURRENT_STEP"])),
                "step_data": step_data if isinstance(step_data, dict) else {},
                "updated_at": str(row_dict["UPDATED_AT"]),
            })
        return sessions
    except Exception as e:
        st.warning(f"Session lookup failed: {e}")
        return []


def create_new_session(session, email: str) -> dict:
    """Create a fresh IN_PROGRESS session row."""
    try:
        safe_email = email.replace("'", "''")
        session.sql(
            f"""INSERT INTO {DB}.SESSION_PROGRESS (USER_EMAIL, STATUS, CURRENT_STEP, STEP_DATA)
                SELECT '{safe_email}', 'IN_PROGRESS', {MIN_STEP}, PARSE_JSON('{{}}')"""
        ).collect()
        result = session.sql(
            f"""SELECT SESSION_ID, CURRENT_STEP
                FROM {DB}.SESSION_PROGRESS
                WHERE USER_EMAIL = '{safe_email}' AND STATUS = 'IN_PROGRESS'
                ORDER BY CREATED_AT DESC LIMIT 1"""
        ).collect()
        if result:
            row = result[0]
            row_dict = _row_to_dict(row)
            return {
                "session_id": str(row_dict["SESSION_ID"]),
                "current_step": MIN_STEP,
                "step_data": {},
            }
    except Exception as e:
        st.warning(f"Create session failed: {e}")
    return {"session_id": "local", "current_step": MIN_STEP, "step_data": {}}


def save_checkpoint(session, session_id: str, new_step: int, step_data: dict) -> bool:
    """MERGE current step_data and set CURRENT_STEP."""
    if not session_id or session_id == "local":
        return False
    new_step = clamp_step(new_step)
    step_data_json = json.dumps(step_data)
    safe_sid = session_id.replace("'", "''")
    try:
        # Use $$ dollar-quoting to avoid JSON escaping issues with single quotes
        session.sql(
            f"""UPDATE {DB}.SESSION_PROGRESS
                SET CURRENT_STEP = {new_step},
                    STEP_DATA = PARSE_JSON($${step_data_json}$$),
                    UPDATED_AT = CURRENT_TIMESTAMP()
                WHERE SESSION_ID = '{safe_sid}' AND STATUS = 'IN_PROGRESS'"""
        ).collect()
        email = st.session_state.get("user_email", "")
        if email:
            safe_email = email.replace("'", "''")
            visited_json = json.dumps(list(range(1, new_step + 1)))
            session.sql(
                f"""MERGE INTO {DB}.USER_PROGRESS t
                    USING (SELECT '{safe_email}' AS USER_EMAIL) s ON t.USER_EMAIL = s.USER_EMAIL
                    WHEN MATCHED THEN UPDATE SET
                        CURRENT_STEP = {new_step},
                        VISITED_STEPS = $${visited_json}$$,
                        LAST_UPDATED = CURRENT_TIMESTAMP()
                    WHEN NOT MATCHED THEN INSERT (USER_EMAIL, CURRENT_STEP, VISITED_STEPS)
                        VALUES ('{safe_email}', {new_step}, $${visited_json}$$)"""
            ).collect()
        return True
    except Exception as e:
        st.warning(f"Save checkpoint failed: {e}")
        return False


def complete_session(session, session_id: str) -> bool:
    """Mark a session as COMPLETED."""
    try:
        safe_sid = session_id.replace("'", "''")
        session.sql(
            f"""UPDATE {DB}.SESSION_PROGRESS
                SET STATUS = 'COMPLETED', UPDATED_AT = CURRENT_TIMESTAMP()
                WHERE SESSION_ID = '{safe_sid}'"""
        ).collect()
        return True
    except Exception:
        return False


def abandon_open_sessions(session, email: str) -> None:
    """Mark all prior IN_PROGRESS sessions as COMPLETED."""
    try:
        safe_email = email.replace("'", "''")
        session.sql(
            f"""UPDATE {DB}.SESSION_PROGRESS
                SET STATUS = 'COMPLETED', UPDATED_AT = CURRENT_TIMESTAMP()
                WHERE USER_EMAIL = '{safe_email}' AND STATUS = 'IN_PROGRESS'"""
        ).collect()
    except Exception:
        pass
