"""Data loading from PostgreSQL tables — cached per session."""

import json
import threading
import time
import streamlit as st
from config import (
    DB,
    CACHE_TTL_SECONDS,
    LUMINATE_DATABASE,
    LUMINATE_SCHEMA,
)


def _row_to_dict(row) -> dict:
    if hasattr(row, "as_dict"):
        values = row.as_dict()
    elif hasattr(row, "asDict"):
        values = row.asDict()
    else:
        values = dict(row)
    return {str(key).upper(): value for key, value in values.items()}


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def detect_luminate_share(_conn):
    """Check if the configured PostgreSQL Luminate schema is accessible."""
    try:
        _conn.query(
            f"SELECT 1 FROM {LUMINATE_SCHEMA}.vw_musical_release_group_ds LIMIT 1"
        )
        return {"available": True, "database": LUMINATE_DATABASE}
    except Exception:
        pass
    return {"available": False, "database": None}


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def load_data_from_postgres(_conn):
    """Load all workbench data from PostgreSQL tables/views."""
    data = {}

    luminate_status = detect_luminate_share(_conn)
    data["_data_source"] = {
        "type": "luminate_share" if luminate_status["available"] else "demo",
        "database": luminate_status["database"],
    }

    # albums is populated dynamically from step2 table data (not hardcoded)
    data["albums"] = []

    # Steps 4-8 data is computed per catalog by analytics.compute_analytics once the STEP2
    # table exists. Until then these are empty (never placeholder numbers).
    data["consumption_matrix"] = []
    data["consumption_monthly"] = []
    data["growth_trend"] = []
    data["release_year_analysis"] = []
    data["new_release_tracks"] = []

    # ambiguity_matches is populated dynamically from live search queries only
    data["ambiguity_matches"] = {}

    try:
        rows = _conn.query(f"SELECT CONFIG_KEY, CONFIG_VALUE FROM {DB}.CONFIG")
        for r in rows:
            val = r["CONFIG_VALUE"]
            if isinstance(val, str):
                try:
                    val = json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    pass
            data[r["CONFIG_KEY"]] = val
    except Exception:
        pass

    # Ensure required keys have defaults so JS never crashes
    data.setdefault("territories", {"countries": [], "codes": {}, "regions": {}, "default_local": []})
    data.setdefault("country_stats", [])
    data.setdefault("market_growth", {"artist_growth_pct": 0, "market_growth_pct": None})
    data.setdefault("catalog_age_split", {"older_than_10y_pct": 0, "recent_releases_pct": 0, "basis": "none"})
    data.setdefault("ppd", {"current_splits": {}, "future_splits": {}, "source": "none"})
    data.setdefault("album_country_revenue", {})
    data.setdefault("data_status", {"has_streaming_data": False, "reason": "The catalog has not been built yet."})

    return data


# ─── Live Luminate catalog search ─────────────────────────────────────────────
LUMINATE_VIEW = f"{LUMINATE_DATABASE}.{LUMINATE_SCHEMA}.vw_musical_release_group_ds"
LUMINATE_SONG_MAP = f"{LUMINATE_DATABASE}.{LUMINATE_SCHEMA}.vw_song_mrelg_map_ds"
LUMINATE_SONG = f"{LUMINATE_DATABASE}.{LUMINATE_SCHEMA}.vw_song_ds"

def _build_like_pattern(term: str) -> str:
    """Build a LIKE pattern from a search term: 'bad bunny' → '%bad%bunny%'."""
    return "%" + "%".join(term.strip().lower().split()) + "%"


def _rank_results(records: list[dict]) -> list[dict]:
    """Convert raw query records into confidence-ranked ambiguity-style dicts."""
    if not records:
        return []
    normalized = [_row_to_dict(record) for record in records]
    max_count = int(normalized[0]["ALBUM_COUNT"])
    results = []
    for i, r in enumerate(normalized):
        count = int(r["ALBUM_COUNT"])
        if i == 0:
            confidence = "High"
        elif count >= max_count * 0.5:
            confidence = "Medium"
        else:
            confidence = "Low"
        results.append({
            "id": i + 1,
            "name": str(r["NAME"]),
            "confidence": confidence,
            "track_count": count,
            "recommended": i == 0,
        })
    return results


def search_catalog(_conn, search_mode: str, search_term: str) -> list[dict]:
    """Run a live Luminate query based on search mode and return ambiguity-style matches.

    Uses parameterized queries to prevent SQL injection.
    Returns a list of dicts: {name, confidence, track_count, recommended}.
    Raises if the query fails (an empty list always means "nothing matched").
    """
    if not search_term or not search_term.strip():
        return []

    like_pattern = _build_like_pattern(search_term)

    try:
        session = _conn.session()

        if search_mode == "Artist":
            rows = session.sql(
                f"""SELECT DISTINCT DISPLAY_ARTIST AS NAME,
                           COUNT(DISTINCT mrelg_id) AS ALBUM_COUNT
                    FROM {LUMINATE_VIEW}
                    WHERE LOWER(DISPLAY_ARTIST) LIKE :1
                    GROUP BY DISPLAY_ARTIST
                    ORDER BY ALBUM_COUNT DESC
                    --LIMIT 20
                    """,
                params=[like_pattern],
            ).collect()
        elif search_mode == "Label":
            rows = session.sql(
                f"""SELECT DISTINCT IMPRINT AS NAME,
                           COUNT(DISTINCT mrelg_id) AS ALBUM_COUNT
                    FROM {LUMINATE_VIEW}
                    WHERE LOWER(IMPRINT) LIKE :1
                    GROUP BY IMPRINT
                    ORDER BY ALBUM_COUNT DESC
                    --LIMIT 20
                    """,
                params=[like_pattern],
            ).collect()
        elif search_mode == "ISRC List":
            isrc_table = _conn.state.get("isrc_table")
            if not isrc_table:
                return []
            rows = session.sql(
                f"""SELECT DISTINCT TITLE || ' — ' || DISPLAY_ARTIST AS NAME,
                           COUNT(DISTINCT v.mrelg_id) AS ALBUM_COUNT
                    FROM {LUMINATE_VIEW} v
                    WHERE v.mrelg_id IN (
                        SELECT relg.mrelg_id
                        FROM {LUMINATE_SONG_MAP} relg
                        JOIN {LUMINATE_SONG} sng
                            ON relg.song_id = sng.song_id
                        WHERE sng.isrc IN (SELECT isrc FROM {isrc_table})
                    )
                    GROUP BY TITLE, DISPLAY_ARTIST
                    ORDER BY ALBUM_COUNT DESC
                    --LIMIT 20
                    """
            ).collect()
        else:
            return []

        if not rows:
            return []

        return _rank_results(rows)
    except Exception:
        # Not swallowed: a failed query is not the same as "no matches", and the caller must not cache it.
        raise


@st.cache_resource
def _analytics_store() -> dict:
    """Process-wide analytics results keyed by catalog table: {table: (computed_at, result)}."""
    return {"lock": threading.Lock(), "entries": {}}


MAX_CACHED_CATALOGS = 16


def invalidate_analytics(step2_table: str) -> None:
    """Forget cached analytics for a catalog table (call when the table is rebuilt)."""
    store = _analytics_store()
    with store["lock"]:
        store["entries"].pop(step2_table, None)


def compute_analytics_from_monthly_detail(_session, step2_table: str, _albums_json: str, progress=None) -> dict:
    """Steps 4-8 analytics for a catalog, derived entirely from database tables.

    Wraps ``analytics.compute_analytics`` with a process-wide cache keyed by the catalog table.
    Every step click reloads the page into a new Streamlit session, so a per-session cache never hit and
    the whole analysis was recomputed on each click. ``st.cache_data`` is deliberately not used: it would
    replay the progress card's UI calls on a cache hit. Errors propagate and are never cached, so the
    caller can show them instead of invented data.
    """
    from analytics import compute_analytics
    from build_progress import NULL_PROGRESS

    store = _analytics_store()
    with store["lock"]:
        hit = store["entries"].get(step2_table)
    if hit and time.time() - hit[0] < CACHE_TTL_SECONDS:
        if progress:
            progress.note("Using the saved analysis")
        return hit[1]
    result = compute_analytics(_session, step2_table, json.loads(_albums_json), progress or NULL_PROGRESS)
    with store["lock"]:
        store["entries"][step2_table] = (time.time(), result)
        while len(store["entries"]) > MAX_CACHED_CATALOGS:
            del store["entries"][min(store["entries"], key=lambda t: store["entries"][t][0])]
    return result


def _parse_isrcs(csv_data: bytes) -> list[str]:
    """ISRCs from an uploaded CSV/TXT: header optional, first 'isrc' column (else column 1), de-duplicated.

    Dashes are dropped (US-ABC-12-34567 -> USABC1234567) and values are upper-cased.
    """
    import csv as csv_mod
    import io

    if csv_data[:4] == b"PK\x03\x04":
        # .xlsx is a zip archive; the upload box accepts it, so read the first worksheet instead of decoding as text.
        from openpyxl import load_workbook

        workbook = load_workbook(io.BytesIO(csv_data), read_only=True, data_only=True)
        try:
            raw_rows = [["" if cell is None else str(cell) for cell in row] for row in workbook.worksheets[0].iter_rows(values_only=True)]
        finally:
            workbook.close()
    else:
        text = csv_data.decode("utf-8-sig", errors="replace")
        raw_rows = list(csv_mod.reader(io.StringIO(text)))
    rows = [row for row in raw_rows if row and any(cell.strip() for cell in row)]
    if not rows:
        return []
    column = 0
    header = [cell.strip().lower() for cell in rows[0]]
    if any("isrc" in cell for cell in header):
        column = next(i for i, cell in enumerate(header) if "isrc" in cell)
        rows = rows[1:]
    seen, isrcs = set(), []
    for row in rows:
        value = row[column].strip().upper().replace("-", "") if column < len(row) else ""
        if value and value not in seen:
            seen.add(value)
            isrcs.append(value)
    return isrcs


def create_isrc_temp_table(_conn, csv_data: bytes, user_email: str, filename: str) -> str:
    """Upload a CSV of ISRCs into a temp table named step1_{user}_{filename}_{timestamp}.

    The table is connection-local, so it lives as long as the user's session connection.
    Returns the table name.
    """
    import re
    from datetime import datetime

    def _sanitize(name: str) -> str:
        sanitized = re.sub(r"[^A-Za-z0-9_]", "_", name.strip())
        sanitized = re.sub(r"_+", "_", sanitized).strip("_").upper()
        return sanitized[:40] if sanitized else "UNKNOWN"

    user_part = _sanitize(user_email.split("@")[0] if "@" in user_email else user_email)
    file_part = _sanitize(filename.rsplit(".", 1)[0] if "." in filename else filename)
    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    table_name = f"STEP1_{user_part}_{file_part}_{ts}"[:63]

    session = _conn.session()
    session.sql(f"CREATE TEMP TABLE {table_name} (ISRC VARCHAR)").collect()
    # COPY: one round-trip for the whole file, and CSV values never become part of the SQL text.
    session.bulk_insert(table_name, ["ISRC"], [(isrc,) for isrc in _parse_isrcs(csv_data)])
    return table_name


def ensure_isrc_temp_table(_conn, csv_data: bytes, user_email: str, filename: str) -> str:
    """Build the ISRC temp table once per distinct upload.

    The upload travels in the URL, so it is present on every page load; without this the table would be
    rebuilt each time. The same file reuses the existing table while the connection (and so the
    table) is alive; a new connection starts with no table and rebuilds it.
    """
    import hashlib

    digest = hashlib.sha1(csv_data).hexdigest()
    if _conn.state.get("isrc_table") and _conn.state.get("isrc_hash") == digest:
        return _conn.state["isrc_table"]
    table = create_isrc_temp_table(_conn, csv_data, user_email, filename)
    _conn.state.update(isrc_table=table, isrc_hash=digest)
    return table
