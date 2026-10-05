# Catalog table builder — creates tables in PostgreSQL for the M&A valuation platform.
# Co-authored with CoCo
"""Catalog table builder — creates tables in PostgreSQL.

Naming convention: STEP{N}_{searchterm}_{username}_{sessionid}
"""

import hashlib
import re
from datetime import datetime
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
    """Normalize PostgreSQL and Snowflake result-row column casing."""
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
        unique = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    prefix = f"STEP{step}"
    budget = PG_IDENTIFIER_LIMIT - len(prefix) - len(unique) - 3     # three separating underscores
    if len(entity_part) + len(user_part) > budget:
        digest = hashlib.sha1(f"{entity_name}|{user_email}".encode("utf-8")).hexdigest()[:6].upper()
        budget -= len(digest) + 1
        user_part = user_part[: max(4, budget // 3)]
        entity_part = f"{entity_part[: max(1, budget - len(user_part))]}_{digest}"
    return f"{prefix}_{entity_part}_{user_part}_{unique}"[:PG_IDENTIFIER_LIMIT]


def get_step2_table_name(user_email: str, entity_name: str, session_id: str = "") -> str:
    """Return the deterministic Step 2 table name for a catalogue session."""
    return f"{DB}.{_make_table_name(2, user_email, entity_name, session_id)}"


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


def create_catalog_table(session, entity_name: str, user_email: str, search_mode: str = "Artist/Band", session_id: str = "") -> dict:
    """Create the Step 2 catalog table with confirmed mrelg_ids.

    Table: STEP2_{searchterm}_{username}_{sessionid}
    Created when user clicks Next from Step 1.
    Logs the activity to CATALOG_ACTIVITY_LOG.
    Returns a dict with status, table_name, and summary stats.
    """
    fqn = get_step2_table_name(user_email, entity_name, session_id)

    entity_type_map = {
        "Artist/Band": "ARTIST",
        "Artist": "ARTIST",
        "Label": "LABEL",
        "ISRC List": "ISRC",
    }
    entity_type = entity_type_map.get(search_mode, "ARTIST")

    try:
        session.sql(
            f"""CREATE OR REPLACE TABLE {fqn} (
                MRELG_ID VARCHAR,
                TRACK_ID VARCHAR,
                TRACK_NAME VARCHAR,
                ISRC VARCHAR,
                RELEASE_YEAR NUMBER,
                FIRST_STREAM_DATE DATE,
                CONTENT_TYPE VARCHAR,
                PRIMARY_ALBUM_ID VARCHAR,
                ALBUM_ID VARCHAR,
                ALBUM_NAME VARCHAR,
                RELEASE_TYPE VARCHAR,
                IS_COMPILATION BOOLEAN,
                ALBUM_RELEASE_YEAR NUMBER,
                TRACK_COUNT NUMBER,
                CURRENT_REVENUE_USD FLOAT,
                TOTAL_CONSUMPTION_STREAMS NUMBER,
                IS_PRIMARY_ALBUM BOOLEAN,
                ENTITY_NAME VARCHAR,
                ENTITY_TYPE VARCHAR,
                SEARCH_MODE VARCHAR,
                CREATED_BY VARCHAR,
                CREATED_AT TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
            )"""
        ).collect()

        session.sql(
            f"""INSERT INTO {fqn}
                (MRELG_ID, TRACK_ID, TRACK_NAME, ISRC, RELEASE_YEAR, FIRST_STREAM_DATE,
                 CONTENT_TYPE, PRIMARY_ALBUM_ID, ALBUM_ID, ALBUM_NAME, RELEASE_TYPE,
                 IS_COMPILATION, ALBUM_RELEASE_YEAR, TRACK_COUNT, CURRENT_REVENUE_USD,
                 TOTAL_CONSUMPTION_STREAMS, IS_PRIMARY_ALBUM, ENTITY_NAME, ENTITY_TYPE,
                 SEARCH_MODE, CREATED_BY)
                SELECT
                    a.ALBUM_ID AS MRELG_ID,
                    t.TRACK_ID, t.TRACK_NAME, t.ISRC, t.RELEASE_YEAR, t.FIRST_STREAM_DATE,
                    t.CONTENT_TYPE, t.PRIMARY_ALBUM_ID,
                    a.ALBUM_ID, a.ALBUM_NAME, a.RELEASE_TYPE,
                    a.IS_COMPILATION, a.RELEASE_YEAR AS ALBUM_RELEASE_YEAR,
                    a.TRACK_COUNT, a.CURRENT_REVENUE_USD, a.TOTAL_CONSUMPTION_STREAMS,
                    b.IS_PRIMARY,
                    :1,
                    :2,
                    :3,
                    :4
                FROM {DB}.TRACKS t
                JOIN {DB}.TRACK_ALBUM_BRIDGE b ON t.TRACK_ID = b.TRACK_ID
                JOIN {DB}.ALBUMS a ON b.ALBUM_ID = a.ALBUM_ID
                WHERE EXISTS (
                    SELECT 1 FROM {DB}.AMBIGUITY_MATCHES am
                    WHERE am.MATCH_NAME = :5
                    AND am.TRACK_COUNT > 0
                )""",
            params=[entity_name, entity_type, search_mode, user_email, entity_name],
        ).collect()

        stats = session.sql(
            f"""SELECT
                    COUNT(DISTINCT TRACK_ID) AS TRACK_COUNT,
                    COUNT(DISTINCT ALBUM_ID) AS ALBUM_COUNT,
                    COALESCE(SUM(TOTAL_CONSUMPTION_STREAMS), 0) AS TOTAL_STREAMS,
                    COALESCE(SUM(CURRENT_REVENUE_USD), 0) AS TOTAL_REVENUE
                FROM {fqn}
                WHERE IS_PRIMARY_ALBUM = TRUE"""
        ).collect()

        stats_row = _upper_keys(stats[0]) if stats else {}
        track_count = int(stats_row.get("TRACK_COUNT", 0))
        album_count = int(stats_row.get("ALBUM_COUNT", 0))
        total_streams = int(stats_row.get("TOTAL_STREAMS", 0))
        total_revenue = float(stats_row.get("TOTAL_REVENUE", 0.0))

        session.sql(
            f"""INSERT INTO {DB}.CATALOG_ACTIVITY_LOG
                (USER_EMAIL, ACTIVITY_TYPE, ENTITY_NAME, ENTITY_TYPE, SEARCH_MODE,
                 CATALOG_TABLE_NAME, TRACK_COUNT, ALBUM_COUNT, TOTAL_STREAMS,
                 TOTAL_REVENUE_USD, STATUS)
                VALUES (:1, 'TABLE_CREATED', :2, :3, :4, :5, :6, :7, :8, :9, 'SUCCESS')""",
            params=[user_email, entity_name, entity_type, search_mode,
                    fqn, track_count, album_count, total_streams, total_revenue],
        ).collect()

        return {
            "status": "success",
            "table_name": fqn,
            "track_count": track_count,
            "album_count": album_count,
            "total_streams": total_streams,
            "total_revenue": total_revenue,
        }
    except Exception as e:
        try:
            session.sql(
                f"""INSERT INTO {DB}.CATALOG_ACTIVITY_LOG
                    (USER_EMAIL, ACTIVITY_TYPE, ENTITY_NAME, ENTITY_TYPE, SEARCH_MODE,
                     CATALOG_TABLE_NAME, STATUS, ERROR_MESSAGE)
                    VALUES (:1, 'TABLE_CREATED', :2, :3, :4, :5, 'FAILED', :6)""",
                params=[user_email, entity_name, entity_type, search_mode, fqn, str(e)[:2000]],
            ).collect()
        except Exception:
            pass
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


def pull_monthly_detail(session, step2_table: str):
    """Step 2 → Step 3: query monthly streaming detail for confirmed releases.

    Uses artist names from the step2 table to find all matching recordings
    in VW_MUSICAL_RECORDING_DS, then pulls their streaming data from
    MONTHLY_MR_SUMMARY. This approach works even when PRODUCT_CATALOG
    has sparse release_group mappings.
    Returns a Snowpark DataFrame (no table is created).
    """
    luminate_fqn = f"{LUMINATE_DATABASE}.{LUMINATE_SCHEMA}"
    models_fqn = f"{LUMINATE_DATABASE}.{LUMINATE_SCHEMA}"

    return session.sql(
        f"""WITH matched_recordings AS (
                SELECT rec.MR_ID, rec.DISPLAY_ARTIST, rec.TITLE, rec.RELEASE_DATE
                FROM {luminate_fqn}.VW_MUSICAL_RECORDING_DS rec
                JOIN (
                    SELECT DISTINCT LOWER(DISPLAY_ARTIST) AS ARTIST_KEY
                    FROM {step2_table}
                ) artists
                    ON LOWER(rec.DISPLAY_ARTIST) = artists.ARTIST_KEY
            ),
            step2_lookup AS (
                SELECT DISTINCT MRELG_ID, DISPLAY_ARTIST
                FROM {step2_table}
            )
            SELECT
                mr.MONTH_START_DATE,
                mr.COUNTRY_CODE,
                mr.COMMERCIAL_MODEL,
                m.DISPLAY_ARTIST AS RELEASE_GROUP_DISPLAY_ARTIST,
                COALESCE(pc.RELEASE_GROUP_ID, s2.MRELG_ID) AS RELEASE_GROUP_ID,
                COALESCE(pc.RELEASE_GROUP_TITLE, m.TITLE) AS RELEASE_GROUP_TITLE,
                m.RELEASE_DATE AS FIRST_STREAM_DATE,
                mr.MR_ID AS RECORDING_ID,
                m.TITLE AS RECORDING_TITLE,
                mr.CONTENT_TYPE,
                SUM(mr.QUANTITY) AS QUANTITY
            FROM {models_fqn}.MONTHLY_MR_SUMMARY mr
            JOIN matched_recordings m
                ON m.MR_ID = mr.MR_ID
            LEFT JOIN {models_fqn}.PRODUCT_CATALOG pc
                ON pc.RECORDING_ID = mr.MR_ID
            CROSS JOIN (
                SELECT DISTINCT MRELG_ID
                FROM step2_lookup
                LIMIT 1
            ) s2
            WHERE mr.MONTH_START_DATE >= '2020-01-01'
            GROUP BY 1, 2, 3, 4, 5, 6, 7, 8, 9, 10"""
    ).collect()