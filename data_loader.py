"""Data loading from PostgreSQL tables — cached per session."""

import json
import streamlit as st
from config import (
    ANALYTICS_DATABASE,
    ANALYTICS_SCHEMA,
    COUNTRY_CODE_TO_NAME,
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

    try:
        rows = _conn.query(f"SELECT * FROM {DB}.TRACKS ORDER BY TRACK_ID")
        data["tracks"] = [
            {
                "track_id": r["TRACK_ID"],
                "track_name": r["TRACK_NAME"],
                "isrc": r["ISRC"],
                "release_year": int(r["RELEASE_YEAR"]),
                "first_stream_date": str(r["FIRST_STREAM_DATE"]),
                "content_type": r["CONTENT_TYPE"],
                "primary_album_id": r["PRIMARY_ALBUM_ID"],
            }
            for r in rows
        ]
    except Exception:
        data["tracks"] = []

    # albums is populated dynamically from step2 table data (not hardcoded)
    data["albums"] = []

    try:
        rows = _conn.query(f"SELECT * FROM {DB}.TRACK_ALBUM_BRIDGE ORDER BY TRACK_ID, ALBUM_ID")
        data["track_album_bridge"] = [
            {
                "track_id": r["TRACK_ID"],
                "album_id": r["ALBUM_ID"],
                "is_primary": bool(r["IS_PRIMARY"]),
            }
            for r in rows
        ]
    except Exception:
        data["track_album_bridge"] = []

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

    try:
        rows = _conn.query(f"SELECT NAME FROM {DB}.ARTISTS ORDER BY NAME")
        artist_names = [r["NAME"] for r in rows]
        if "catalog_options" not in data or not isinstance(data.get("catalog_options"), dict):
            data["catalog_options"] = {}
        data["catalog_options"]["artists"] = artist_names
    except Exception:
        pass

    # Ensure required keys have defaults so JS never crashes
    data.setdefault("catalog_options", {"artists": [], "labels": []})
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

def search_artists_dropdown(_conn, term: str) -> list[str]:
    """Return matching artist names from Luminate for the dropdown (top 10)."""
    if not term or not term.strip():
        return []
    try:
        session = _conn.session()
        like_pattern = f"%{term.strip()}%"
        rows = session.sql(
            f"""SELECT DISTINCT DISPLAY_ARTIST
                FROM {LUMINATE_VIEW}
                WHERE DISPLAY_ARTIST ILIKE :1
                ORDER BY CASE WHEN TRIM(DISPLAY_ARTIST) ILIKE :2 THEN 0 ELSE 1 END,
                         LENGTH(DISPLAY_ARTIST) ASC, DISPLAY_ARTIST DESC
                LIMIT 1""",
            params=[like_pattern, term.strip()],
        ).collect()
        if rows:
            return [_row_to_dict(row).get("DISPLAY_ARTIST") for row in rows]
    except Exception:
        pass
    return []


def search_labels_dropdown(_conn, term: str) -> list[str]:
    """Return matching label/imprint names from Luminate for the dropdown (top 10)."""
    if not term or not term.strip():
        return []
    try:
        session = _conn.session()
        like_pattern = f"%{term.strip()}%"
        rows = session.sql(
            f"""SELECT DISTINCT IMPRINT
                FROM {LUMINATE_VIEW}
                WHERE IMPRINT ILIKE :1
                ORDER BY CASE WHEN TRIM(IMPRINT) ILIKE :2 THEN 0 ELSE 1 END,
                         LENGTH(IMPRINT) ASC, IMPRINT ASC
                LIMIT 1""",
            params=[like_pattern, term.strip()],
        ).collect()
        if rows:
            return [_row_to_dict(row).get("IMPRINT") for row in rows]
    except Exception:
        pass
    return []


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
    Returns a list of dicts: {name, confidence, track_count, recommended}
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
            isrc_table = st.session_state.get("_isrc_temp_table")
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

    except Exception as e:
        return []


def compute_analytics_from_monthly_detail(_session, step2_table: str, _albums_json: str, progress=None) -> dict:
    """Steps 4-8 analytics for a catalog, derived entirely from database tables.

    Wraps ``analytics.compute_analytics`` with a per-session cache keyed by the catalog table
    (``st.cache_data`` is deliberately not used: it would replay the progress card's UI calls on
    a cache hit). Errors propagate and are never cached, so the caller can show them instead of
    invented data.
    """
    import time
    from analytics import compute_analytics
    from build_progress import NULL_PROGRESS

    cache = st.session_state.setdefault("_analytics_cache", {})
    hit = cache.get(step2_table)
    if hit and time.time() - hit[0] < CACHE_TTL_SECONDS:
        return hit[1]
    result = compute_analytics(_session, step2_table, json.loads(_albums_json), progress or NULL_PROGRESS)
    cache.clear()  # one catalog at a time per session keeps memory bounded
    cache[step2_table] = (time.time(), result)
    return result


def create_isrc_temp_table(_conn, csv_data: bytes, user_email: str, filename: str) -> str:
    """Upload a CSV of ISRCs into a temp table named step1_{user}_{filename}_{timestamp}.

    Returns the fully-qualified table name.
    """
    import re
    import io
    import csv as csv_mod
    from datetime import datetime

    def _sanitize(name: str) -> str:
        sanitized = re.sub(r"[^A-Za-z0-9_]", "_", name.strip())
        sanitized = re.sub(r"_+", "_", sanitized).strip("_").upper()
        return sanitized[:40] if sanitized else "UNKNOWN"

    user_part = _sanitize(user_email.split("@")[0] if "@" in user_email else user_email)
    file_part = _sanitize(filename.rsplit(".", 1)[0] if "." in filename else filename)
    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    table_name = f"STEP1_{user_part}_{file_part}_{ts}"
    # Temporary tables belong to the connection-local PostgreSQL temp schema.
    fqn = table_name

    session = _conn.session()
    session.sql(f"CREATE TEMP TABLE {fqn} (ISRC VARCHAR)").collect()

    # Parse CSV and insert ISRCs
    text = csv_data.decode("utf-8", errors="replace")
    reader = csv_mod.reader(io.StringIO(text))
    isrcs = []
    for row in reader:
        if row:
            val = row[0].strip().upper()
            if val and val != "ISRC":  # skip header
                isrcs.append(val)

    # Batch insert in chunks of 500
    for i in range(0, len(isrcs), 500):
        batch = isrcs[i:i + 500]
        values = ", ".join(f"('{v}')" for v in batch)
        session.sql(f"INSERT INTO {fqn} VALUES {values}").collect()

    return fqn
