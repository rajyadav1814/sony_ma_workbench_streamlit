# Catalog table builder — creates tables in PostgreSQL for the M&A valuation platform.
# Co-authored with CoCo
"""Catalog table builder — creates tables in PostgreSQL.

Naming convention: STEP{N}_{searchterm}_{username}_{sessionid}
"""

import re
from datetime import datetime
from config import DB, LUMINATE_DATABASE, LUMINATE_SCHEMA


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


def _make_table_name(step: int, user_email: str, entity_name: str, session_id: str = "") -> str:
    user_part = _sanitize_identifier(
        user_email.split("@")[0] if "@" in user_email else user_email
    )
    entity_part = _sanitize_identifier(entity_name)
    if session_id:
        sid_part = _sanitize_identifier(session_id.replace("-", ""))
        return f"STEP{step}_{entity_part}_{user_part}_{sid_part}"
    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    return f"STEP{step}_{entity_part}_{user_part}_{ts}"


def create_step1_selection_table(session, entity_name: str, user_email: str, selected_entities: list, search_mode: str = "Artist", session_id: str = "") -> dict:
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

        # Batch all selected entities into one query to avoid a round-trip per
        # artist or label when a search returns many ambiguity matches.
        entities = [str(entity) for entity in selected_entities if entity]
        if entities and search_mode in ("Artist", "Label"):
            placeholders = ", ".join(f":{index + 1}" for index in range(len(entities)))
            source_column = "DISPLAY_ARTIST" if search_mode == "Artist" else "IMPRINT"
            entity_expr = f"{source_column}"
            params = entities + [entity_name, search_mode, user_email, session_id]
            offset = len(entities)
            session.sql(
                f"""INSERT INTO {fqn}
                    (MRELG_ID, ENTITY_NAME, SEARCH_TERM, SEARCH_MODE, SELECTED_BY, SESSION_ID)
                    SELECT DISTINCT MRELG_ID, {entity_expr}, :{offset + 1},
                        :{offset + 2}, :{offset + 3}, :{offset + 4}
                    FROM {luminate_view}
                    WHERE {source_column} IN ({placeholders})""",
                params=params,
            ).collect()
        elif entities:
            # ISRC List or other modes: preserve the uploaded/selected values.
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
    table_name = _make_table_name(2, user_email, entity_name, session_id=session_id)
    fqn = f"{DB}.{table_name}"

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


def create_step2_table(session, step1_table: str, confirmed_mrelg_ids: list, user_email: str, entity_name: str, session_id: str = "") -> str:
    """Create Step 2 table with release group details from Luminate.

    Uses MRELG_IDs from the STEP1 table to query VW_MUSICAL_RELEASE_GROUP_DS
    for full release metadata.
    Table: STEP2_{user}_{entity}_{sessionid}
    Returns the fully-qualified table name.
    """
    table_name = _make_table_name(2, user_email, entity_name, session_id=session_id)
    fqn = f"{DB}.{table_name}"
    luminate_view = f"{LUMINATE_DATABASE}.{LUMINATE_SCHEMA}.VW_MUSICAL_RELEASE_GROUP_DS"

    # Filter step1 to only confirmed entities (if provided)
    if confirmed_mrelg_ids:
        placeholders = ", ".join([f":{i+1}" for i in range(len(confirmed_mrelg_ids))])
        filter_clause = f"WHERE s1.ENTITY_NAME IN ({placeholders})"
        params = confirmed_mrelg_ids
    else:
        filter_clause = ""
        params = []

    sql = f"""CREATE OR REPLACE TABLE {fqn} AS
            SELECT
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
            JOIN {step1_table} s1 ON v.MRELG_ID = s1.MRELG_ID
            {filter_clause}"""

    if params:
        session.sql(sql, params=params).collect()
    else:
        session.sql(sql).collect()

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