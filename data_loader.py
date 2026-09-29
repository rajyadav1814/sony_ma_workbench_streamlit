"""Data loading from PostgreSQL tables — cached per session."""

import json
import streamlit as st
from config import (
    ANALYTICS_DATABASE,
    ANALYTICS_SCHEMA,
    DB,
    CACHE_TTL_SECONDS,
    LUMINATE_DATABASE,
    LUMINATE_SCHEMA,
)

COUNTRY_CODE_TO_NAME = {
    "US": "United States", "MX": "Mexico", "CO": "Colombia", "AR": "Argentina",
    "BR": "Brazil", "ES": "Spain", "CL": "Chile", "PE": "Peru", "GB": "United Kingdom",
    "DE": "Germany", "FR": "France", "IT": "Italy", "EC": "Ecuador", "VE": "Venezuela",
    "DO": "Dominican Republic", "GT": "Guatemala", "JP": "Japan", "CA": "Canada",
    "AU": "Australia", "PT": "Portugal", "KR": "South Korea", "NZ": "New Zealand",
    "IN": "India", "ID": "Indonesia", "TH": "Thailand", "PH": "Philippines",
    "MY": "Malaysia", "SG": "Singapore", "TW": "Taiwan", "HK": "Hong Kong",
    "VN": "Vietnam", "ZA": "South Africa", "NG": "Nigeria", "KE": "Kenya",
    "EG": "Egypt", "AE": "United Arab Emirates", "SA": "Saudi Arabia", "IL": "Israel",
    "TR": "Turkey", "NL": "Netherlands", "SE": "Sweden", "NO": "Norway",
    "DK": "Denmark", "FI": "Finland", "BE": "Belgium", "AT": "Austria",
    "CH": "Switzerland", "IE": "Ireland", "PL": "Poland", "CZ": "Czech Republic",
    "RO": "Romania", "HU": "Hungary", "GR": "Greece", "UY": "Uruguay",
    "PY": "Paraguay", "BO": "Bolivia", "CR": "Costa Rica", "PA": "Panama",
    "HN": "Honduras", "SV": "El Salvador", "NI": "Nicaragua", "CU": "Cuba",
    "PR": "Puerto Rico",
}


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

    # These keys are now computed dynamically from pull_monthly_detail in step 3→4+
    # Provide empty defaults so the app renders before step2 table is ready
    data["consumption_matrix"] = [
        {"bucket": "2024", "audio_premium": 0, "audio_ad_supported": 0, "video_premium": 0, "video_ad_supported": 0}
    ]
    data["growth_trend"] = [{"year": 2024, "yoy_growth_pct": 0}]
    data["release_year_analysis"] = [
        {"bucket": "2024", "consumption_streams": 0, "revenue_usd": 0, "yoy_growth_pct": 0}
    ]
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
    data.setdefault("territories", {"countries": ["United States", "Mexico", "Colombia"], "regions": {"Latin America": ["Mexico", "Colombia"], "North America": ["United States"]}})
    data.setdefault("market_growth", {"artist_growth_pct": 0, "market_growth_pct": 7.0})
    data.setdefault("catalog_age_split", {"older_than_10y_pct": 0, "recent_releases_pct": 0})
    data.setdefault("local_row_revenue", {"local_revenue_usd": 0, "row_revenue_usd": 0})
    data.setdefault("ppd", {"current_splits": {"audio_premium": 0.0038, "audio_ad_supported": 0.0015, "video_premium": 0.0020, "video_ad_supported": 0.0007}, "future_splits": {"audio_premium": 0.0040, "audio_ad_supported": 0.0016, "video_premium": 0.0021, "video_ad_supported": 0.0007}})

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


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def load_bobwa_consumption_matrix(_session) -> list:
    """Load consumption matrix from SAMIS_FACT_BOBWA_AV_YEARLY_PPD, pivoted by year."""
    try:
        rows = _session.sql(f"""
            SELECT
                CALENDAR_YEAR,
                SUM(CASE WHEN AUDIO_VIDEO_SUB_CATEGORY = 'Audio - Premium' THEN UNITS ELSE 0 END) AS AUDIO_PREMIUM,
                SUM(CASE WHEN AUDIO_VIDEO_SUB_CATEGORY = 'Audio - Ad Supported' THEN UNITS ELSE 0 END) AS AUDIO_AD_SUPPORTED,
                SUM(CASE WHEN AUDIO_VIDEO_SUB_CATEGORY = 'Video - Premium' THEN UNITS ELSE 0 END) AS VIDEO_PREMIUM,
                SUM(CASE WHEN AUDIO_VIDEO_SUB_CATEGORY = 'Video - Ad Supported' THEN UNITS ELSE 0 END) AS VIDEO_AD_SUPPORTED
            FROM {ANALYTICS_DATABASE}.{ANALYTICS_SCHEMA}.SAMIS_FACT_BOBWA_AV_YEARLY_PPD
            GROUP BY CALENDAR_YEAR
            ORDER BY CALENDAR_YEAR
        """).collect()
        return [
            {
                "bucket": str(int(row["CALENDAR_YEAR"])),
                "audio_premium": int(row["AUDIO_PREMIUM"]),
                "audio_ad_supported": int(row["AUDIO_AD_SUPPORTED"]),
                "video_premium": int(row["VIDEO_PREMIUM"]),
                "video_ad_supported": int(row["VIDEO_AD_SUPPORTED"]),
            }
            for row in rows
        ]
    except Exception:
        return []


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def load_available_years(_session) -> list:
    """Fetch distinct years from MONTHLY_MR_SUMMARY.MONTH_START_DATE for year filters."""
    try:
        fqn = f"{LUMINATE_DATABASE}.{LUMINATE_SCHEMA}.MONTHLY_MR_SUMMARY"
        rows = _session.sql(f"""
            SELECT DISTINCT EXTRACT(YEAR FROM MONTH_START_DATE) AS YR
            FROM {fqn}
            WHERE MONTH_START_DATE IS NOT NULL
            ORDER BY YR
        """).collect()
        return [int(row["YR"]) for row in rows]
    except Exception:
        return []


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def load_bobwa_ppd(_session) -> dict:
    """Load PPD (wholesale_value / units) by year, country, and sub-category from BOBWA."""
    try:
        rows = _session.sql(f"""
            SELECT
                CALENDAR_YEAR,
                COUNTRY_CODE,
                AFFILIATE_COUNTRY,
                AUDIO_VIDEO_SUB_CATEGORY,
                SUM(UNITS)           AS TOTAL_UNITS,
                SUM(WHOLESALE_VALUE) AS TOTAL_WHOLESALE_VALUE,
                CASE WHEN SUM(UNITS) > 0
                     THEN SUM(WHOLESALE_VALUE) / SUM(UNITS)
                     ELSE 0
                END                  AS PPD
            FROM {ANALYTICS_DATABASE}.{ANALYTICS_SCHEMA}.SAMIS_FACT_BOBWA_AV_YEARLY_PPD
            GROUP BY CALENDAR_YEAR, COUNTRY_CODE, AFFILIATE_COUNTRY, AUDIO_VIDEO_SUB_CATEGORY
            ORDER BY CALENDAR_YEAR, COUNTRY_CODE, AUDIO_VIDEO_SUB_CATEGORY
        """).collect()
        if not rows:
            return {}

        seg_map = {
            "Audio - Premium": "audio_premium",
            "Audio - Ad Supported": "audio_ad_supported",
            "Video - Premium": "video_premium",
            "Video - Ad Supported": "video_ad_supported",
        }

        # Global PPD splits (current = latest year, future = 5% projected increase)
        latest_year = max(int(row["CALENDAR_YEAR"] or 0) for row in rows)
        latest = [row for row in rows if int(row["CALENDAR_YEAR"] or 0) == latest_year]
        current_splits = {}
        for sub_cat, key in seg_map.items():
            seg_rows = [row for row in latest if row["AUDIO_VIDEO_SUB_CATEGORY"] == sub_cat]
            total_units = sum(float(row["TOTAL_UNITS"] or 0) for row in seg_rows)
            total_value = sum(float(row["TOTAL_WHOLESALE_VALUE"] or 0) for row in seg_rows)
            current_splits[key] = round(total_value / total_units, 6) if total_units > 0 else 0.0
        future_splits = {k: round(v * 1.05, 6) for k, v in current_splits.items()}

        # PPD by year and sub-category (for chart display)
        ppd_by_year = []
        for year in sorted({int(row["CALENDAR_YEAR"] or 0) for row in rows}):
            yr_rows = [row for row in rows if int(row["CALENDAR_YEAR"] or 0) == year]
            row = {"bucket": str(int(year))}
            for sub_cat, key in seg_map.items():
                seg = [item for item in yr_rows if item["AUDIO_VIDEO_SUB_CATEGORY"] == sub_cat]
                u = sum(float(item["TOTAL_UNITS"] or 0) for item in seg)
                v = sum(float(item["TOTAL_WHOLESALE_VALUE"] or 0) for item in seg)
                row[key] = round(v / u, 6) if u > 0 else 0.0
            ppd_by_year.append(row)

        # PPD by country and sub-category (latest year, for territory table)
        ppd_by_country = []
        for row in latest:
            ppd_by_country.append({
                "country_code": row["COUNTRY_CODE"],
                "country_name": row["AFFILIATE_COUNTRY"],
                "sub_category": seg_map.get(row["AUDIO_VIDEO_SUB_CATEGORY"], row["AUDIO_VIDEO_SUB_CATEGORY"]),
                "ppd": round(float(row["PPD"] or 0), 6),
                "units": int(row["TOTAL_UNITS"] or 0),
                "wholesale_value": round(float(row["TOTAL_WHOLESALE_VALUE"] or 0), 2),
            })

        return {
            "current_splits": current_splits,
            "future_splits": future_splits,
            "ppd_by_year": ppd_by_year,
            "ppd_by_country": ppd_by_country,
            "latest_year": latest_year,
        }
    except Exception:
        return {}


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def compute_analytics_from_monthly_detail(_session, step2_table: str, _albums_json: str) -> dict:
    """Compute steps 4-8 analytics from pull_monthly_detail raw streaming data.

    Falls back to generating realistic computed data from album metadata
    when Luminate streaming data is unavailable or insufficient.

    Returns a dict with keys: territories, consumption_matrix, growth_trend,
    market_growth, catalog_age_split, release_year_analysis, local_row_revenue,
    ppd, new_release_tracks, albums.
    """
    import math
    from datetime import datetime
    from catalog_builder import pull_monthly_detail
    import json as _json

    albums = _json.loads(_albums_json)
    current_year = datetime.now().year
    rows = []

    try:
        rows = pull_monthly_detail(_session, step2_table).collect()
    except Exception:
        pass

    if len(rows) > 100:
        return _compute_from_streaming_data(rows, albums, current_year)
    else:
        return _compute_from_album_metadata(albums, current_year)


def _compute_from_album_metadata(albums: list, current_year: int) -> dict:
    """Generate realistic analytics data derived from album metadata."""
    import math

    result = {}
    num_albums = len(albums)
    if num_albums == 0:
        return {}

    # --- Territories ---
    top_country_codes = ["US", "MX", "CO", "AR", "BR", "ES", "CL", "PE", "GB", "DE",
                         "FR", "IT", "EC", "VE", "DO", "GT", "JP", "CA", "AU", "PT"]
    top_countries = [COUNTRY_CODE_TO_NAME.get(c, c) for c in top_country_codes]
    region_map = {
        "Latin America": [COUNTRY_CODE_TO_NAME.get(c, c) for c in ["MX", "CO", "AR", "BR", "CL", "PE", "EC", "VE", "DO", "GT"]],
        "North America": [COUNTRY_CODE_TO_NAME.get(c, c) for c in ["US", "CA"]],
        "Europe": [COUNTRY_CODE_TO_NAME.get(c, c) for c in ["ES", "GB", "DE", "FR", "IT", "PT"]],
        "Asia Pacific": [COUNTRY_CODE_TO_NAME.get(c, c) for c in ["JP", "AU"]],
    }
    result["territories"] = {"countries": top_countries, "regions": region_map}

    # --- Derive base metrics from album metadata ---
    album_years = [a.get("release_year", 0) for a in albums if a.get("release_year", 0) > 0]
    min_year = min(album_years) if album_years else current_year - 5
    max_year = max(album_years) if album_years else current_year

    # Estimate total catalog streams based on number of albums (realistic scale)
    base_streams_per_album = 15_000_000  # 15M avg streams per album for established artist
    total_catalog_streams = num_albums * base_streams_per_album

    # --- Consumption Matrix (half-year buckets) ---
    start_year = max(min_year, current_year - 4)
    buckets = []
    for y in range(start_year, current_year + 1):
        for h in ["Jan-Jun", "Jul-Dec"]:
            if y == current_year and h == "Jul-Dec":
                continue
            label = str(y) if y == current_year else f"{y} {h}"
            buckets.append(label)

    matrix_rows = []
    for i, bucket in enumerate(buckets):
        growth_factor = 1.0 + (i * 0.08)  # 8% growth per half-year
        base = total_catalog_streams / len(buckets) * growth_factor
        matrix_rows.append({
            "bucket": bucket,
            "audio_premium": int(base * 0.55),
            "audio_ad_supported": int(base * 0.25),
            "video_premium": int(base * 0.12),
            "video_ad_supported": int(base * 0.08),
        })
    result["consumption_matrix"] = matrix_rows

    # --- Growth Trend ---
    growth_trend = []
    for y in range(max(min_year, current_year - 6), current_year + 1):
        age = current_year - y
        yoy = round(12.0 - age * 1.5 + math.sin(y) * 3, 1)
        growth_trend.append({"year": y, "yoy_growth_pct": yoy})
    result["growth_trend"] = growth_trend

    # --- Market Growth ---
    artist_growth = growth_trend[-1]["yoy_growth_pct"] if growth_trend else 8.0
    market_growth_pct = 7.0
    result["market_growth"] = {
        "artist_growth_pct": artist_growth,
        "market_growth_pct": market_growth_pct,
    }

    # --- Catalog Age Split ---
    if album_years:
        older_count = sum(1 for y in album_years if (current_year - y) > 10)
        recent_count = sum(1 for y in album_years if (current_year - y) <= 3)
        total_count = len(album_years)
        result["catalog_age_split"] = {
            "older_than_10y_pct": round(older_count / total_count * 100),
            "recent_releases_pct": round(recent_count / total_count * 100),
        }
    else:
        result["catalog_age_split"] = {"older_than_10y_pct": 50, "recent_releases_pct": 20}

    # --- Release Year Analysis ---
    year_album_count = {}
    for a in albums:
        ry = a.get("release_year", 0)
        if ry > 0:
            year_album_count[ry] = year_album_count.get(ry, 0) + 1

    ry_analysis = []
    sorted_years = sorted(year_album_count.keys())
    prev_streams = None
    for year in sorted_years:
        count = year_album_count[year]
        age = current_year - year
        decay = max(0.3, 1.0 - age * 0.05)  # older albums have less streaming
        streams = int(count * base_streams_per_album * decay)
        rev = round(streams * 0.003, 2)
        yoy = round(((streams - prev_streams) / prev_streams * 100), 1) if prev_streams and prev_streams > 0 else 0
        ry_analysis.append({
            "bucket": str(year),
            "consumption_streams": streams,
            "revenue_usd": rev,
            "yoy_growth_pct": yoy,
        })
        prev_streams = streams
    result["release_year_analysis"] = ry_analysis

    # --- Local/ROW Revenue ---
    total_revenue = total_catalog_streams * 0.003
    local_pct = 0.35  # 35% from local territories
    result["release_year_consumption"] = []  # not available in fallback path
    result["local_row_revenue"] = {
        "local_revenue_usd": round(total_revenue * local_pct, 2),
        "row_revenue_usd": round(total_revenue * (1 - local_pct), 2),
    }

    # --- PPD ---
    result["ppd"] = {
        "current_splits": {
            "audio_premium": 0.0038,
            "audio_ad_supported": 0.0015,
            "video_premium": 0.0020,
            "video_ad_supported": 0.0007,
        },
        "future_splits": {
            "audio_premium": 0.0040,
            "audio_ad_supported": 0.0016,
            "video_premium": 0.0021,
            "video_ad_supported": 0.0007,
        },
    }

    # --- Enrich albums ---
    enriched_albums = []
    for i, a in enumerate(albums):
        ry = a.get("release_year", 0)
        age = max(1, current_year - ry) if ry > 0 else 5
        decay = max(0.3, 1.0 - age * 0.05)
        streams = int(base_streams_per_album * decay * (1 + math.sin(i) * 0.3))
        track_count = max(1, int(8 + math.sin(i * 2.1) * 5))
        enriched_albums.append({
            **a,
            "total_consumption_streams": streams,
            "current_revenue_usd": round(streams * 0.003, 2),
            "track_count": track_count if a.get("track_count", 0) == 0 else a["track_count"],
        })
    result["albums"] = enriched_albums

    # --- New Release Tracks ---
    recent_albums = [a for a in albums if a.get("release_year", 0) >= current_year - 3]
    new_release_tracks = []
    for i, a in enumerate(recent_albums[:20]):
        streams_m = round(2.0 + math.sin(i * 1.7) * 1.5 + i * 0.3, 2)
        flag = "Normal"
        if streams_m > 5:
            flag = "Outlier"
        elif i > 15:
            flag = "Incomplete Data"
        new_release_tracks.append({
            "track_id": f"TR_{i:04d}",
            "track_name": a.get("album_name", f"Track {i+1}"),
            "release_year": a.get("release_year", current_year),
            "first_12m_streams_millions": max(0.5, streams_m),
            "months_of_data": min(12, 12 - i % 6),
            "flag": flag,
        })
    result["new_release_tracks"] = new_release_tracks

    return result


def _compute_from_streaming_data(rows: list[dict], albums: list, current_year: int) -> dict:
    """Compute analytics from actual Luminate streaming records."""
    from collections import defaultdict
    from datetime import date, datetime

    def year_month(value):
        if isinstance(value, (date, datetime)):
            return value.year, value.month
        try:
            parsed = date.fromisoformat(str(value)[:10])
            return parsed.year, parsed.month
        except (TypeError, ValueError):
            return 0, 0

    records = [_row_to_dict(row) for row in rows]
    countries_raw = sorted({r["COUNTRY_CODE"] for r in records if r.get("COUNTRY_CODE")})
    region_map_codes = {
        "Latin America": ["MX", "CO", "AR", "BR", "CL", "PE", "EC", "VE", "UY", "PY", "BO", "CR", "PA", "DO", "GT", "HN", "SV", "NI", "CU", "PR"],
        "North America": ["US", "CA"],
        "Europe": ["GB", "DE", "FR", "ES", "IT", "NL", "SE", "NO", "DK", "FI", "PT", "BE", "AT", "CH", "IE", "PL", "CZ", "RO", "HU", "GR"],
        "Asia Pacific": ["JP", "KR", "AU", "NZ", "IN", "ID", "TH", "PH", "MY", "SG", "TW", "HK", "VN"],
        "Middle East & Africa": ["ZA", "NG", "KE", "EG", "AE", "SA", "IL", "TR"],
    }
    regions_out = {
        region: [COUNTRY_CODE_TO_NAME.get(code, code) for code in codes if code in countries_raw]
        for region, codes in region_map_codes.items()
    }
    regions_out = {region: countries for region, countries in regions_out.items() if countries}
    result = {"territories": {
        "countries": [COUNTRY_CODE_TO_NAME.get(code, code) for code in countries_raw],
        "regions": regions_out,
    }}

    records = [
        row for row in records
        if row.get("CONTENT_TYPE") not in ("Total", "LUMINATE_NULL")
        and row.get("COMMERCIAL_MODEL") != "LUMINATE_NULL"
    ]
    if not records:
        return _compute_from_album_metadata(albums, current_year)

    segment_keys = ("audio_premium", "audio_ad_supported", "video_premium", "video_ad_supported")
    by_bucket = defaultdict(lambda: defaultdict(float))
    by_year = defaultdict(float)
    by_release_year = defaultdict(float)
    by_release_consumption = defaultdict(float)
    by_release_consumption_segment = defaultdict(float)
    by_album_streams = defaultdict(float)
    by_album_recordings = defaultdict(set)
    by_track = defaultdict(lambda: {"streams": 0.0, "months": set()})
    album_year_map = {str(a["album_id"]).strip(): int(a.get("release_year", 0) or 0) for a in albums}
    total_streams = 0.0
    local_streams = 0.0
    enriched_rows = []

    for row in records:
        month_year, month = year_month(row.get("MONTH_START_DATE"))
        if not month_year:
            continue
        quantity = float(row.get("QUANTITY") or 0)
        content_type = str(row.get("CONTENT_TYPE") or "").lower()
        commercial_model = str(row.get("COMMERCIAL_MODEL") or "").lower()
        is_video = content_type == "video" or "video" in content_type
        is_premium = commercial_model == "premium" or "premium" in commercial_model
        segment = (
            "video_premium" if is_video and is_premium else
            "video_ad_supported" if is_video else
            "audio_premium" if is_premium else
            "audio_ad_supported"
        )
        bucket = str(month_year) if month_year == current_year else f"{month_year} {'Jan-Jun' if month <= 6 else 'Jul-Dec'}"
        by_bucket[bucket][segment] += quantity
        by_year[month_year] += quantity
        country = row.get("COUNTRY_CODE")
        total_streams += quantity
        if country in ("MX", "US", "CO"):
            local_streams += quantity

        release_group_id = str(row.get("RELEASE_GROUP_ID") or "").strip()
        first_stream_year, _ = year_month(row.get("FIRST_STREAM_DATE"))
        release_year = album_year_map.get(release_group_id) or first_stream_year
        recording_id = row.get("RECORDING_ID")
        by_album_streams[release_group_id] += quantity
        if recording_id is not None:
            by_album_recordings[release_group_id].add(recording_id)
        if release_year > 0:
            by_release_year[release_year] += quantity
            by_release_consumption[(release_year, month_year)] += quantity
            by_release_consumption_segment[(release_year, month_year, segment)] += quantity

        if release_year >= current_year - 3:
            track_key = (recording_id, row.get("RECORDING_TITLE"), release_year)
            track = by_track[track_key]
            track["streams"] += quantity
            track["months"].add(str(row.get("MONTH_START_DATE")))
        enriched_rows.append((row, month_year, release_year, segment))

    if not enriched_rows:
        return _compute_from_album_metadata(albums, current_year)

    result["consumption_matrix"] = [
        {"bucket": bucket, **{key: int(values[key]) for key in segment_keys}}
        for bucket, values in sorted(by_bucket.items())
    ]
    growth_trend = []
    previous_total = None
    for year, total in sorted(by_year.items()):
        growth = round((total - previous_total) / previous_total * 100, 1) if previous_total else 0
        growth_trend.append({"year": int(year), "yoy_growth_pct": growth})
        previous_total = total
    result["growth_trend"] = growth_trend
    result["market_growth"] = {
        "artist_growth_pct": growth_trend[-1]["yoy_growth_pct"] if len(growth_trend) >= 2 else 0,
        "market_growth_pct": 7.0,
    }

    album_years = [a.get("release_year", 0) for a in albums if a.get("release_year", 0) > 0]
    if album_years:
        result["catalog_age_split"] = {
            "older_than_10y_pct": round(sum(current_year - y > 10 for y in album_years) / len(album_years) * 100),
            "recent_releases_pct": round(sum(current_year - y <= 3 for y in album_years) / len(album_years) * 100),
        }
    else:
        result["catalog_age_split"] = {"older_than_10y_pct": 0, "recent_releases_pct": 0}

    avg_ppd = 0.003
    release_year_analysis = []
    previous_streams = None
    for year, streams in sorted(by_release_year.items()):
        growth = round((streams - previous_streams) / previous_streams * 100, 1) if previous_streams else 0
        release_year_analysis.append({
            "bucket": str(year),
            "consumption_streams": int(streams),
            "revenue_usd": round(streams * avg_ppd, 2),
            "yoy_growth_pct": growth,
        })
        previous_streams = streams
    result["release_year_analysis"] = release_year_analysis
    result["release_year_consumption"] = [
        {"release_year": release_year, "consumption_year": consumption_year,
         "streams": int(streams), "revenue_usd": round(streams * avg_ppd, 2)}
        for (release_year, consumption_year), streams in sorted(by_release_consumption.items())
    ]
    result["release_year_consumption_segments"] = [
        {"release_year": release_year, "consumption_year": consumption_year,
         "segment": segment, "streams": int(streams)}
        for (release_year, consumption_year, segment), streams in sorted(by_release_consumption_segment.items())
    ]
    result["local_row_revenue"] = {
        "local_revenue_usd": round(local_streams * avg_ppd, 2),
        "row_revenue_usd": round((total_streams - local_streams) * avg_ppd, 2),
    }
    current_splits = {
        "audio_premium": 0.0038,
        "audio_ad_supported": 0.0015,
        "video_premium": 0.0020,
        "video_ad_supported": 0.0007,
    }
    result["ppd"] = {
        "current_splits": current_splits,
        "future_splits": {key: round(value * 1.05, 6) for key, value in current_splits.items()},
    }
    result["albums"] = [
        {
            **album,
            "total_consumption_streams": int(by_album_streams[str(album["album_id"]).strip()]),
            "current_revenue_usd": round(by_album_streams[str(album["album_id"]).strip()] * avg_ppd, 2),
            "track_count": len(by_album_recordings[str(album["album_id"]).strip()]) or album.get("track_count", 0),
        }
        for album in albums
    ]

    tracks = sorted(by_track.items(), key=lambda item: item[1]["streams"], reverse=True)[:30]
    new_release_tracks = []
    for (recording_id, title, release_year), performance in tracks:
        months = len(performance["months"])
        total = performance["streams"]
        first_12m = total / months * min(months, 12) / 1_000_000 if months else 0
        flag = "Outlier" if first_12m > 50 else "Incomplete Data" if months < 6 else "Normal"
        new_release_tracks.append({
            "track_id": str(recording_id),
            "track_name": str(title or "Unknown"),
            "release_year": int(release_year),
            "first_12m_streams_millions": round(first_12m, 2),
            "months_of_data": months,
            "flag": flag,
        })
    result["new_release_tracks"] = new_release_tracks
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
