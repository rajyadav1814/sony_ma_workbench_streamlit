# Catalog table builder — creates tables in PostgreSQL for the M&A valuation platform.
"""Catalog table builder — creates tables in PostgreSQL.

Naming convention: STEP{N}_{searchterm}_{username}_{sessionid}
"""

import hashlib
import re
from datetime import datetime, timezone
from build_progress import NULL_PROGRESS
from config import DB, LUMINATE_DATABASE, LUMINATE_SCHEMA

MAX_PROGRESS_TICKS = 8   # each batch scans the Luminate view once, so keep this small
MIN_BATCH_SIZE = 3


def _batches(items: list, max_ticks: int = MAX_PROGRESS_TICKS, max_size: int = 50) -> list[list]:
    """Split ``items`` into at most ``max_ticks`` batches so progress can be reported per batch."""
    if not items:
        return []
    size = min(max_size, max(MIN_BATCH_SIZE, -(-len(items) // max_ticks)))
    return [items[i:i + size] for i in range(0, len(items), size)]


def _upper_keys(row) -> dict:
    """Normalize result-row column casing to uppercase keys."""
    if hasattr(row, "as_dict"):
        values = row.as_dict()
    elif hasattr(row, "asDict"):
        values = row.asDict()
    else:
        values = dict(row)
    return {str(key).upper(): value for key, value in values.items()}


def _sanitize_identifier(name: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9_]", "_", name.strip())
    sanitized = re.sub(r"_+", "_", sanitized).strip("_").upper()
    return sanitized[:60] if sanitized else "UNKNOWN"


PG_IDENTIFIER_LIMIT = 63   # PostgreSQL silently truncates longer names


def _make_table_name(step: int, user_email: str, entity_name: str, session_id: str = "") -> str:
    """STEP{n}_{entity}_{user}_{session}, never longer than PostgreSQL's identifier limit.

    The session id (or timestamp) is the unique part and sits at the end, so a long search term must
    not push it past the limit: PostgreSQL would truncate it away and two catalogues could end up
    sharing one table. Only the entity and user parts are shortened, and a short hash of the full
    values keeps shortened names distinct.
    """
    user_part = _sanitize_identifier(
        user_email.split("@")[0] if "@" in user_email else user_email
    )
    entity_part = _sanitize_identifier(entity_name)
    if session_id:
        unique = _sanitize_identifier(session_id.replace("-", ""))
    else:
        unique = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    prefix = f"STEP{step}"
    budget = PG_IDENTIFIER_LIMIT - len(prefix) - len(unique) - 3     # three separating underscores
    if len(entity_part) + len(user_part) > budget:
        digest = hashlib.sha1(f"{entity_name}|{user_email}".encode("utf-8")).hexdigest()[:6].upper()
        budget -= len(digest) + 1
        user_part = user_part[: max(4, budget // 3)]
        entity_part = f"{entity_part[: max(1, budget - len(user_part))]}_{digest}"
    return f"{prefix}_{entity_part}_{user_part}_{unique}"[:PG_IDENTIFIER_LIMIT]


def drop_session_tables(session, session_id: str) -> list[str]:
    """Drop the STEP1_/STEP2_ tables built for one catalogue session; returns the names dropped.

    Tables are named STEP{n}_{entity}_{user}_{session}, with the session part always last (see
    _make_table_name), so they are found by that suffix. Only tables in the app schema whose name is
    exactly STEP1_/STEP2_ ... _{session} are touched.
    """
    unique = _sanitize_identifier(session_id.replace("-", "")) if session_id else ""
    if session_id == "local" or len(unique) < 8 or unique == "UNKNOWN":
        return []    # no real session id: never match anything
    pattern = re.compile(rf"^step[12]_.+_{re.escape(unique.lower())}$")
    rows = session.sql(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = :1 AND table_type = 'BASE TABLE' AND table_name LIKE 'step%'",
        params=[DB.lower()],
    ).collect()
    dropped = []
    for row in rows:
        name = _upper_keys(row)["TABLE_NAME"]
        if pattern.match(name) and re.fullmatch(r"[a-z0-9_]+", name):
            session.sql(f'DROP TABLE IF EXISTS {DB}."{name}"').collect()
            dropped.append(f"{DB}.{name.upper()}")
    return dropped


def create_step1_selection_table(session, entity_name: str, user_email: str, selected_entities: list, search_mode: str = "Artist", session_id: str = "", progress=NULL_PROGRESS, isrc_table: str | None = None) -> dict:
    """Store the user's selected ambiguity entities into STEP1_{searchterm}_{username}_{sessionid}.

    Queries the configured Luminate source schema for release groups.
    to fetch MRELG_IDs for each selected entity and stores them.
    Called when the user confirms their selection on screen 2.
    Returns a dict with status and table_name.
    """
    table_name = _make_table_name(1, user_email, entity_name, session_id=session_id)
    fqn = f"{DB}.{table_name}"
    luminate_view = f"{LUMINATE_DATABASE}.{LUMINATE_SCHEMA}.VW_MUSICAL_RELEASE_GROUP_DS"

    try:
        progress.stage("prepare", "Creating the selection table")
        session.sql(
            f"""CREATE OR REPLACE TABLE {fqn} (
                MRELG_ID VARCHAR,
                ENTITY_NAME VARCHAR,
                SEARCH_TERM VARCHAR,
                SEARCH_MODE VARCHAR,
                SELECTED_BY VARCHAR,
                SESSION_ID VARCHAR,
                CREATED_AT TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
            )"""
        ).collect()

        # Selected entities are matched in batches (not one query per artist or label) so the
        # progress card can report real progress while keeping round-trips low.
        entities = [str(entity) for entity in selected_entities if entity]
        if entities and search_mode in ("Artist", "Label"):
            source_column = "DISPLAY_ARTIST" if search_mode == "Artist" else "IMPRINT"
            noun = "artists" if search_mode == "Artist" else "labels"
            progress.stage("match", f"Matching {len(entities):,} selected {noun}")
            matched = 0
            for batch in _batches(entities):
                placeholders = ", ".join(f":{index + 1}" for index in range(len(batch)))
                lowered = ", ".join(f"LOWER(:{index + 1})" for index in range(len(batch)))
                offset = len(batch)
                # LOWER(col) IN (...) lets PostgreSQL use the lower(display_artist) / lower(imprint)
                # indexes (a bare "col IN (...)" cannot, and scans the whole view); the exact
                # comparison keeps "Shakira" and "SHAKIRA" as the separate entities the user picked.
                session.sql(
                    f"""INSERT INTO {fqn}
                        (MRELG_ID, ENTITY_NAME, SEARCH_TERM, SEARCH_MODE, SELECTED_BY, SESSION_ID)
                        SELECT DISTINCT MRELG_ID, {source_column}, :{offset + 1},
                            :{offset + 2}, :{offset + 3}, :{offset + 4}
                        FROM {luminate_view}
                        WHERE LOWER({source_column}) IN ({lowered})
                          AND {source_column} IN ({placeholders})""",
                    params=batch + [entity_name, search_mode, user_email, session_id],
                ).collect()
                matched += len(batch)
                progress.advance(matched / len(entities), f"{matched:,} of {len(entities):,} {noun} matched")
        elif entities and search_mode == "ISRC List" and isrc_table:
            # The picked entities are "TITLE — ARTIST" labels (see data_loader.search_catalog). Resolve them
            # to release groups through the uploaded ISRCs so STEP2 has real MRELG_IDs to join on.
            progress.stage("match", f"Matching release groups for {len(entities):,} selected titles")
            matched = 0
            for batch in _batches(entities):
                placeholders = ", ".join(f":{index + 1}" for index in range(len(batch)))
                offset = len(batch)
                session.sql(
                    f"""INSERT INTO {fqn}
                        (MRELG_ID, ENTITY_NAME, SEARCH_TERM, SEARCH_MODE, SELECTED_BY, SESSION_ID)
                        SELECT DISTINCT v.MRELG_ID, v.TITLE || ' — ' || v.DISPLAY_ARTIST, :{offset + 1},
                            :{offset + 2}, :{offset + 3}, :{offset + 4}
                        FROM {luminate_view} v
                        WHERE v.TITLE || ' — ' || v.DISPLAY_ARTIST IN ({placeholders})
                          AND v.MRELG_ID IN (
                              SELECT relg.MRELG_ID
                              FROM {LUMINATE_DATABASE}.{LUMINATE_SCHEMA}.VW_SONG_MRELG_MAP_DS relg
                              JOIN {LUMINATE_DATABASE}.{LUMINATE_SCHEMA}.VW_SONG_DS sng ON relg.SONG_ID = sng.SONG_ID
                              WHERE sng.ISRC IN (SELECT ISRC FROM {isrc_table})
                          )""",
                    params=batch + [entity_name, search_mode, user_email, session_id],
                ).collect()
                matched += len(batch)
                progress.advance(matched / len(entities), f"{matched:,} of {len(entities):,} titles matched")
        elif entities:
            # Other modes: preserve the selected values.
            values_sql = ", ".join(
                f"(NULL, :{index + 1}, :{len(entities) + 1}, :{len(entities) + 2}, "
                f":{len(entities) + 3}, :{len(entities) + 4})"
                for index in range(len(entities))
            )
            session.sql(
                f"""INSERT INTO {fqn}
                    (MRELG_ID, ENTITY_NAME, SEARCH_TERM, SEARCH_MODE, SELECTED_BY, SESSION_ID)
                    VALUES {values_sql}""",
                params=entities + [entity_name, search_mode, user_email, session_id],
            ).collect()

        row_count = _upper_keys(session.sql(f"SELECT COUNT(*) AS CNT FROM {fqn}").collect()[0])["CNT"]
        progress.note(f"{int(row_count):,} release groups matched")
        return {"status": "success", "table_name": fqn, "row_count": int(row_count)}
    except Exception as e:
        return {"status": "error", "table_name": fqn, "error": str(e)}


def create_step2_table(session, step1_table: str, confirmed_mrelg_ids: list, user_email: str, entity_name: str, session_id: str = "", progress=NULL_PROGRESS) -> str:
    """Create Step 2 table with release group details from Luminate.

    Uses MRELG_IDs from the STEP1 table to query VW_MUSICAL_RELEASE_GROUP_DS
    for full release metadata, loading one batch of entities at a time so progress is real.
    Table: STEP2_{user}_{entity}_{sessionid}
    Returns the fully-qualified table name.
    """
    table_name = _make_table_name(2, user_email, entity_name, session_id=session_id)
    fqn = f"{DB}.{table_name}"
    luminate_view = f"{LUMINATE_DATABASE}.{LUMINATE_SCHEMA}.VW_MUSICAL_RELEASE_GROUP_DS"

    select_sql = f"""SELECT
                v.MRELG_ID,
                v.TITLE,
                v.DISPLAY_ARTIST,
                v.IMPRINT,
                v.RELEASE_DATE,
                v.RELEASE_YEAR,
                v.PRODUCT_FORMAT,
                v.RELEASE_TYPE,
                v.GENRES,
                v.COMPILATION_TYPE,
                v.DURATION,
                s1.ENTITY_NAME,
                s1.SEARCH_TERM,
                s1.SEARCH_MODE,
                s1.SELECTED_BY,
                s1.SESSION_ID
            FROM {luminate_view} v
            JOIN {step1_table} s1 ON v.MRELG_ID = s1.MRELG_ID"""

    progress.stage("details", "Creating the release table")
    session.sql(f"CREATE OR REPLACE TABLE {fqn} AS {select_sql} WHERE 1 = 0").collect()

    # Entities to load: the confirmed ones, else every entity recorded in the STEP1 table.
    entities = [str(e) for e in confirmed_mrelg_ids if e] or [
        _upper_keys(r)["ENTITY_NAME"]
        for r in session.sql(f"SELECT DISTINCT ENTITY_NAME FROM {step1_table} WHERE ENTITY_NAME IS NOT NULL").collect()
    ]
    loaded = 0
    for batch in _batches(entities):
        placeholders = ", ".join(f":{i + 1}" for i in range(len(batch)))
        session.sql(f"INSERT INTO {fqn} {select_sql} WHERE s1.ENTITY_NAME IN ({placeholders})", params=batch).collect()
        loaded += len(batch)
        progress.advance(loaded / len(entities), f"{loaded:,} of {len(entities):,} selections loaded")
    count = _upper_keys(session.sql(f"SELECT COUNT(*) AS CNT FROM {fqn}").collect()[0])["CNT"]
    progress.note(f"{int(count):,} releases loaded")
    return fqn
