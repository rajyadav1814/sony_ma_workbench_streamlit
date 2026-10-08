"""Dynamic analytics for workbench steps 4-8 (territory, analytics, revenue, albums, export).

Every figure shown in those steps is derived from database tables:

* consumption  -> ``MONTHLY_MR_SUMMARY`` joined to the recordings of the confirmed catalog
* release year -> the confirmed release groups (STEP2 table), falling back to recording dates
* revenue      -> consumption x PPD, where PPD comes from ``SAMIS_FACT_BOBWA_AV_YEARLY_PPD``
* assumptions  -> ``{APP_SCHEMA}.config`` rows (JSON values) over defaults in ``config.py``

Nothing is fabricated: when a table is empty or missing, the matching output is empty (or
flagged as an assumption in ``data_status``) and the UI says so.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import date

from build_progress import NULL_PROGRESS
from config import (
    ANALYTICS_SCHEMA,
    COUNTRY_CODE_TO_NAME,
    DB,
    DEFAULT_ASSUMPTIONS,
    EXCLUDED_COMMERCIAL_MODELS,
    EXCLUDED_CONTENT_TYPES,
    MONTHLY_SUMMARY_TABLE,
    PPD_TABLE_NAME,
    PRODUCT_CATALOG_TABLE,
    RECORDING_TABLE,
    REGION_CODES,
    UNALLOCATED_COUNTRY_CODE,
)

SEGMENTS = ("audio_premium", "audio_ad_supported", "video_premium", "video_ad_supported")
_BOBWA_SEGMENTS = {
    "Audio - Premium": "audio_premium",
    "Audio - Ad Supported": "audio_ad_supported",
    "Video - Premium": "video_premium",
    "Video - Ad Supported": "video_ad_supported",
}
_TABLE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?$")


# ─── helpers ──────────────────────────────────────────────────────────────────
def _num(value) -> float:
    return float(value) if value is not None else 0.0


def _sql_list(values) -> str:
    return ", ".join("'" + str(v).replace("'", "''") + "'" for v in values)


def _month_key(value) -> str:
    """'2024-03' for a date/datetime/ISO string."""
    return str(value)[:7]


def _country_name(code: str) -> str:
    return COUNTRY_CODE_TO_NAME.get(code, code)


def _segment_family(segment: str) -> str:
    return "video" if segment.startswith("video") else "audio"


def _percentile(sorted_values: list, fraction: float) -> float:
    if not sorted_values:
        return 0.0
    position = (len(sorted_values) - 1) * fraction
    lower, upper = int(position), min(int(position) + 1, len(sorted_values) - 1)
    return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * (position - lower)


# ─── assumptions & PPD ────────────────────────────────────────────────────────
def load_assumptions(session) -> dict:
    """Defaults from config.py, overridden by JSON rows in the app's CONFIG table."""
    values = json.loads(json.dumps(DEFAULT_ASSUMPTIONS))
    sources = {key: "default" for key in values}
    try:
        rows = session.sql(f"SELECT CONFIG_KEY, CONFIG_VALUE FROM {DB}.CONFIG").collect()
    except Exception:
        rows = []
    for row in rows:
        key = row.get("CONFIG_KEY")
        if key not in values:
            continue
        raw = row.get("CONFIG_VALUE")
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
        except (TypeError, ValueError):
            continue
        if isinstance(values[key], dict) and isinstance(parsed, dict):
            values[key].update({k: float(v) for k, v in parsed.items() if k in values[key]})
        elif isinstance(values[key], list) and isinstance(parsed, list):
            values[key] = parsed
        elif isinstance(values[key], (int, float)) and isinstance(parsed, (int, float)):
            values[key] = parsed
        else:
            continue
        sources[key] = "config"
    values["sources"] = sources
    return values


def load_ppd(session, assumptions: dict) -> dict:
    """PPD (wholesale value / units) from the BOBWA table, else the assumed splits.

    Returns ``{"source", "note", "latest_year", "current_splits", "future_splits",
    "by_year", "by_country", "lookup"}``; ``lookup(country_code, segment)`` gives the PPD.
    """
    assumed = assumptions["ppd_current_splits"]
    uplift = 1 + float(assumptions["ppd_future_uplift_pct"]) / 100.0

    def finish(source, note, current, by_year=(), by_country=(), per_country=None, latest_year=None):
        per_country = per_country or {}

        def lookup(country_code, segment):
            return per_country.get((country_code, segment)) or current.get(segment) or assumed.get(segment, 0.0)

        return {
            "source": source,
            "note": note,
            "latest_year": latest_year,
            "current_splits": {k: round(current.get(k) or assumed.get(k, 0.0), 6) for k in SEGMENTS},
            "future_splits": {k: round((current.get(k) or assumed.get(k, 0.0)) * uplift, 6) for k in SEGMENTS},
            "by_year": list(by_year),
            "by_country": list(by_country),
            "lookup": lookup,
        }

    try:
        exists = session.sql(
            "SELECT 1 AS FOUND FROM information_schema.tables "
            "WHERE LOWER(table_schema) = :1 AND LOWER(table_name) = :2",
            params=[ANALYTICS_SCHEMA.lower(), PPD_TABLE_NAME.lower()],
        ).collect()
    except Exception:
        exists = []
    if not exists:
        return finish("assumed", f"PPD table {PPD_TABLE_NAME} not found; using assumed PPD per segment.", {})

    try:
        rows = session.sql(
            f"""SELECT CALENDAR_YEAR, COUNTRY_CODE, AFFILIATE_COUNTRY, AUDIO_VIDEO_SUB_CATEGORY,
                       SUM(UNITS) AS UNITS, SUM(WHOLESALE_VALUE) AS VALUE
                FROM {ANALYTICS_SCHEMA}.{PPD_TABLE_NAME}
                GROUP BY CALENDAR_YEAR, COUNTRY_CODE, AFFILIATE_COUNTRY, AUDIO_VIDEO_SUB_CATEGORY
                ORDER BY CALENDAR_YEAR, COUNTRY_CODE"""
        ).collect()
    except Exception as error:
        return finish("assumed", f"PPD table {PPD_TABLE_NAME} could not be read ({error}); using assumed PPD.", {})
    rows = [r for r in rows if _BOBWA_SEGMENTS.get(r.get("AUDIO_VIDEO_SUB_CATEGORY")) and r.get("CALENDAR_YEAR") is not None]
    if not rows:
        return finish("assumed", f"PPD table {PPD_TABLE_NAME} is empty; using assumed PPD.", {})

    years = sorted({int(r["CALENDAR_YEAR"]) for r in rows})
    latest_year = years[-1]
    year_seg = defaultdict(lambda: [0.0, 0.0])      # (year, segment) -> [units, value]
    country_seg = {}                                # (country, segment) -> (year, units, value), latest year wins
    for r in rows:
        seg = _BOBWA_SEGMENTS[r["AUDIO_VIDEO_SUB_CATEGORY"]]
        year, units, value = int(r["CALENDAR_YEAR"]), _num(r["UNITS"]), _num(r["VALUE"])
        year_seg[(year, seg)][0] += units
        year_seg[(year, seg)][1] += value
        key = (r.get("COUNTRY_CODE"), seg)
        if units > 0 and (key not in country_seg or year >= country_seg[key][0]):
            country_seg[key] = (year, units, value)

    def ratio(pair):
        return pair[1] / pair[0] if pair[0] > 0 else 0.0

    current = {seg: ratio(year_seg[(latest_year, seg)]) for seg in SEGMENTS if (latest_year, seg) in year_seg}
    by_year = [
        {"bucket": str(year), **{seg: round(ratio(year_seg[(year, seg)]), 6) for seg in SEGMENTS}}
        for year in years
    ]
    per_country = {key: value / units for key, (_, units, value) in country_seg.items()}
    by_country = [
        {"country_code": cc, "country_name": _country_name(cc), "sub_category": seg,
         "ppd": round(ppd, 6), "units": int(country_seg[(cc, seg)][1])}
        for (cc, seg), ppd in sorted(per_country.items(), key=lambda item: (str(item[0][0]), item[0][1]))
    ]
    missing = [seg for seg in SEGMENTS if seg not in current]
    note = f"PPD from {PPD_TABLE_NAME} ({latest_year})."
    if missing:
        note += " Segments without data use assumed PPD: " + ", ".join(missing) + "."
    return finish("table", note, current, by_year, by_country, per_country, latest_year)


# ─── SQL ──────────────────────────────────────────────────────────────────────
# Working tables, built once per catalog by _materialize() and read by every query below.
# They are TEMP (private to the user's connection) and must be dropped before being rebuilt.
_WORK_TABLES = ("wb_fact", "wb_rec_year", "wb_catalog_recs", "wb_rec_map")


def _materialize(session, step2_table: str, progress=NULL_PROGRESS) -> None:
    """Build the catalog's working tables: its recordings and their monthly consumption.

    Previously these were CTEs repeated inside each of the six analytics queries, so the monthly
    summary was joined and aggregated six times per catalog. Doing it once keeps each result
    identical while the heavy work happens a single time.

    ``wb_rec_map`` is de-duplicated (PRODUCT_CATALOG has one row per product, so joining it
    directly would multiply consumption). ``wb_fact`` is recording-level and never fanned out
    by release group, so catalog totals are exact; album totals join ``wb_rec_map`` explicitly.
    """
    segment = (
        # STRPOS rather than LIKE: the adapter runs queries through psycopg, where a literal '%' is a placeholder.
        "CASE WHEN STRPOS(LOWER(COALESCE(mr.CONTENT_TYPE, '')), 'video') > 0 THEN 'video' ELSE 'audio' END "
        "|| '_' || "
        "CASE WHEN STRPOS(LOWER(COALESCE(mr.COMMERCIAL_MODEL, '')), 'premium') > 0 THEN 'premium' ELSE 'ad_supported' END"
    )
    groups = f"""WITH catalog_groups AS (
            SELECT DISTINCT MRELG_ID, DISPLAY_ARTIST,
                   CAST(COALESCE(RELEASE_YEAR, EXTRACT(YEAR FROM RELEASE_DATE)) AS INT) AS RELEASE_YEAR
            FROM {step2_table}
        )"""
    session.sql("DROP TABLE IF EXISTS " + ", ".join(f"pg_temp.{t}" for t in _WORK_TABLES)).collect()
    progress.advance(0.05, "Linking recordings to their releases")
    session.sql(f"""
        CREATE TEMP TABLE wb_rec_map AS {groups}
        SELECT DISTINCT pc.RECORDING_ID AS MR_ID, pc.RELEASE_GROUP_ID AS MRELG_ID
        FROM {PRODUCT_CATALOG_TABLE} pc
        JOIN catalog_groups g ON g.MRELG_ID = pc.RELEASE_GROUP_ID
        WHERE pc.RECORDING_ID IS NOT NULL""").collect()
    progress.advance(0.2, "Finding the artists' other recordings")
    session.sql(f"""
        CREATE TEMP TABLE wb_catalog_recs AS {groups}
        SELECT MR_ID FROM wb_rec_map
        UNION
        SELECT rec.MR_ID
        FROM {RECORDING_TABLE} rec
        JOIN (SELECT DISTINCT LOWER(DISPLAY_ARTIST) AS ARTIST_KEY FROM catalog_groups) a
          ON LOWER(rec.DISPLAY_ARTIST) = a.ARTIST_KEY""").collect()
    progress.advance(0.4, "Dating each recording")
    session.sql(f"""
        CREATE TEMP TABLE wb_rec_year AS {groups}
        SELECT cr.MR_ID,
               CAST(COALESCE(
                   MIN(g.RELEASE_YEAR),
                   MAX(EXTRACT(YEAR FROM r.FIRST_STREAM_DATE)),
                   MAX(EXTRACT(YEAR FROM r.RECORDING_DATE)),
                   MAX(r.RELEASE_YEAR)
               ) AS INT) AS RELEASE_YEAR
        FROM wb_catalog_recs cr
        LEFT JOIN wb_rec_map rm ON rm.MR_ID = cr.MR_ID
        LEFT JOIN catalog_groups g ON g.MRELG_ID = rm.MRELG_ID
        LEFT JOIN {RECORDING_TABLE} r ON r.MR_ID = cr.MR_ID
        GROUP BY cr.MR_ID""").collect()
    progress.advance(0.55, "Reading monthly consumption (the longest step)")
    session.sql(f"""
        CREATE TEMP TABLE wb_fact AS
        SELECT mr.MR_ID, mr.MONTH_START_DATE, mr.COUNTRY_CODE, {segment} AS SEGMENT,
               SUM(mr.QUANTITY) AS QTY
        FROM {MONTHLY_SUMMARY_TABLE} mr
        JOIN wb_catalog_recs cr ON cr.MR_ID = mr.MR_ID
        WHERE mr.MONTH_START_DATE IS NOT NULL
          AND mr.COUNTRY_CODE IS NOT NULL
          AND COALESCE(mr.METRIC_CATEGORY, 'Streams') = 'Streams'
          AND COALESCE(mr.CONTENT_TYPE, '') NOT IN ({_sql_list(EXCLUDED_CONTENT_TYPES)})
          AND COALESCE(mr.COMMERCIAL_MODEL, '') NOT IN ({_sql_list(EXCLUDED_COMMERCIAL_MODELS)})
        GROUP BY 1, 2, 3, 4""").collect()
    progress.advance(0.95, "Preparing the analysis")
    # TEMP tables are never auto-analyzed; without statistics the planner guesses badly on the joins below.
    session.sql("ANALYZE " + ", ".join(_WORK_TABLES)).collect()


def _query(session, select_sql: str) -> list[dict]:
    """Run ``select_sql`` against the working tables (``latest`` = the newest month with consumption)."""
    return session.sql(
        f"WITH latest AS (SELECT MAX(MONTH_START_DATE) AS LATEST_MONTH FROM wb_fact) {select_sql}"
    ).collect()


_IS_LTM = "(f.MONTH_START_DATE > l.LATEST_MONTH - INTERVAL '12 months')"


# ─── pure computations ───────────────────────────────────────────────────────
def growth_trend(monthly_totals: dict) -> list[dict]:
    """Like-for-like YoY growth per calendar year from ``{"YYYY-MM": streams}``.

    A year is compared with the previous year over the months that both years have data
    for, so a partial first/last year never distorts the percentage.
    """
    if not monthly_totals:
        return []
    months = sorted(monthly_totals)
    first_year, last_year = int(months[0][:4]), int(months[-1][:4])
    first_month, last_month = int(months[0][5:7]), int(months[-1][5:7])

    def covered(year):
        start = first_month if year == first_year else 1
        end = last_month if year == last_year else 12
        return set(range(start, end + 1))

    trend = []
    for year in range(first_year + 1, last_year + 1):
        shared = sorted(covered(year) & covered(year - 1))
        if not shared:
            continue
        current = sum(monthly_totals.get(f"{year}-{m:02d}", 0.0) for m in shared)
        previous = sum(monthly_totals.get(f"{year - 1}-{m:02d}", 0.0) for m in shared)
        growth = round((current - previous) / previous * 100, 1) if previous > 0 else None
        trend.append({"year": year, "yoy_growth_pct": growth, "months_compared": len(shared), "partial": len(shared) < 12})
    return trend


def flag_new_release_tracks(tracks: list[dict], latest_month: str) -> list[dict]:
    """Add Normal / Duplicate / Outlier / Incomplete Data flags to new-release tracks."""
    latest_index = int(latest_month[:4]) * 12 + int(latest_month[5:7])
    seen_titles = set()
    for track in sorted(tracks, key=lambda t: t["first_12m_streams"], reverse=True):
        first_index = int(track["first_month"][:4]) * 12 + int(track["first_month"][5:7])
        title_key = (re.sub(r"\W+", " ", track["track_name"].lower()).strip(), track["release_year"])
        if title_key in seen_titles and title_key[0]:
            track["flag"] = "Duplicate"
        elif latest_index - first_index + 1 < 12:
            track["flag"] = "Incomplete Data"
        else:
            track["flag"] = "Normal"
        seen_titles.add(title_key)
    normal = sorted(t["first_12m_streams"] for t in tracks if t["flag"] == "Normal")
    if len(normal) >= 4:
        q1, q3 = _percentile(normal, 0.25), _percentile(normal, 0.75)
        ceiling = q3 + 1.5 * (q3 - q1)
        for track in tracks:
            if track["flag"] == "Normal" and track["first_12m_streams"] > ceiling:
                track["flag"] = "Outlier"
    return tracks


def _region_map(codes: list[str]) -> dict:
    present = set(codes)
    regions = {
        region: [_country_name(code) for code in members if code in present]
        for region, members in REGION_CODES.items()
    }
    regions = {region: names for region, names in regions.items() if names}
    placed = {code for members in REGION_CODES.values() for code in members}
    other = [_country_name(code) for code in codes if code not in placed]
    if other:
        regions["Other / Unallocated"] = other
    return regions


def _default_local(assumptions: dict, ranked_codes: list[str]) -> list[str]:
    """Configured default local territories, else the top-N countries by consumption."""
    by_lower = {_country_name(c).lower(): _country_name(c) for c in ranked_codes}
    by_lower.update({c.lower(): _country_name(c) for c in ranked_codes})
    configured = [by_lower[str(v).lower()] for v in assumptions["default_local_territories"] if str(v).lower() in by_lower]
    if configured:
        return configured
    real = [c for c in ranked_codes if c != UNALLOCATED_COUNTRY_CODE]
    return [_country_name(c) for c in real[: int(assumptions["default_local_territory_count"])]]


def _empty_result(albums: list, assumptions: dict, ppd: dict, reason: str, coverage: dict | None = None) -> dict:
    """What the steps show when no consumption is available: empty, never invented."""
    return {
        "data_status": {
            "has_streaming_data": False, "reason": reason, "ppd_source": ppd["source"], "ppd_note": ppd["note"],
            "coverage": coverage or {}, "assumption_sources": assumptions["sources"],
        },
        "assumptions": {k: v for k, v in assumptions.items() if k != "sources"},
        "territories": {"countries": [], "codes": {}, "regions": {}, "default_local": []},
        "country_stats": [], "consumption_monthly": [], "consumption_matrix": [], "growth_trend": [],
        "market_growth": {"artist_growth_pct": 0, "market_growth_pct": assumptions["market_growth_pct"],
                          "growth_year": None, "growth_basis": "", "market_source": assumptions["sources"]["market_growth_pct"]},
        "catalog_age_split": _age_split_from_albums(albums, None, assumptions),
        "release_year_analysis": [], "release_year_consumption": [],
        "ppd": {"current_splits": ppd["current_splits"], "future_splits": ppd["future_splits"],
                "source": ppd["source"], "latest_year": ppd["latest_year"]},
        "ppd_by_year": ppd["by_year"], "ppd_by_country": ppd["by_country"],
        "album_country_revenue": {}, "new_release_tracks": [],
        "albums": [{**a, "has_streaming_data": False} for a in albums],
    }


def _age_split_from_albums(albums: list, reference_year: int | None, assumptions: dict) -> dict:
    years = [a.get("release_year", 0) for a in albums if a.get("release_year", 0) > 0]
    if not years:
        return {"older_than_10y_pct": 0, "recent_releases_pct": 0, "basis": "none"}
    reference_year = reference_year or date.today().year
    older, recent = int(assumptions["older_catalog_years"]), int(assumptions["recent_catalog_years"])
    return {
        "older_than_10y_pct": round(sum(reference_year - y > older for y in years) / len(years) * 100),
        "recent_releases_pct": round(sum(reference_year - y < recent for y in years) / len(years) * 100),
        "basis": "albums",
    }


# ─── entry point ──────────────────────────────────────────────────────────────
def compute_analytics(session, step2_table: str, albums: list, progress=NULL_PROGRESS) -> dict:
    """Compute everything steps 4-8 render, from the database. See module docstring.

    ``progress`` (see build_progress) is told which query is running, for the live progress card."""
    if not _TABLE_NAME.fullmatch(step2_table or ""):
        raise ValueError(f"Invalid catalog table name: {step2_table!r}")

    progress.stage("an_ppd", "Reading PPD rates and assumptions")
    assumptions = load_assumptions(session)
    ppd = load_ppd(session, assumptions)
    ppd_for = ppd["lookup"]
    progress.note("PPD from table" if ppd["source"] == "table" else "No PPD table found, using standard rates")

    progress.stage("an_coverage", "Collecting the catalog's recordings")
    _materialize(session, step2_table, progress)
    coverage_row = (_query(session, """
        SELECT (SELECT COUNT(*) FROM wb_catalog_recs) AS CATALOG_RECORDINGS,
               (SELECT COUNT(DISTINCT MR_ID) FROM wb_rec_map) AS MAPPED_RECORDINGS,
               (SELECT COUNT(DISTINCT MR_ID) FROM wb_fact) AS RECORDINGS_WITH_STREAMS,
               (SELECT COALESCE(SUM(QTY), 0) FROM wb_fact) AS TOTAL_STREAMS,
               (SELECT COALESCE(SUM(f.QTY), 0) FROM wb_fact f
                 WHERE NOT EXISTS (SELECT 1 FROM wb_rec_map rm WHERE rm.MR_ID = f.MR_ID)) AS UNATTRIBUTED_STREAMS
    """) or [{}])[0]
    coverage = {
        "catalog_recordings": int(_num(coverage_row.get("CATALOG_RECORDINGS"))),
        "mapped_recordings": int(_num(coverage_row.get("MAPPED_RECORDINGS"))),
        "recordings_with_streams": int(_num(coverage_row.get("RECORDINGS_WITH_STREAMS"))),
        "total_streams": int(_num(coverage_row.get("TOTAL_STREAMS"))),
        "unattributed_streams": int(_num(coverage_row.get("UNATTRIBUTED_STREAMS"))),
    }
    progress.note(f"{coverage['catalog_recordings']:,} recordings, {coverage['recordings_with_streams']:,} with consumption")
    if coverage["total_streams"] <= 0:
        return _empty_result(albums, assumptions, ppd, "No consumption rows were found for the recordings in this catalog.", coverage)

    # Monthly consumption (catalog level) -> Step 5 charts, growth, filters.
    progress.stage("an_monthly", "Reading monthly consumption")
    monthly = defaultdict(lambda: dict.fromkeys(SEGMENTS, 0))
    for row in _query(session, """
        SELECT f.MONTH_START_DATE AS MONTH, f.SEGMENT, SUM(f.QTY) AS QTY
        FROM wb_fact f GROUP BY 1, 2 ORDER BY 1"""):
        monthly[_month_key(row["MONTH"])][row["SEGMENT"]] += int(_num(row["QTY"]))
    months = sorted(monthly)
    first_month, latest_month = months[0], months[-1]
    latest_year = int(latest_month[:4])
    monthly_totals = {m: float(sum(v.values())) for m, v in monthly.items()}
    consumption_monthly = [{"ym": m, **monthly[m]} for m in months]
    progress.note(f"{len(months)} months of consumption ({first_month} to {latest_month})")

    # Release-year x consumption-year x country x segment cube -> Steps 4, 5, 6.
    progress.stage("an_cube", "Splitting consumption by territory and release year")
    cube = _query(session, f"""
        SELECT ry.RELEASE_YEAR AS RELEASE_YEAR,
               CAST(EXTRACT(YEAR FROM f.MONTH_START_DATE) AS INT) AS CONSUMPTION_YEAR,
               f.COUNTRY_CODE AS COUNTRY_CODE, f.SEGMENT AS SEGMENT,
               {_IS_LTM} AS IS_LTM, SUM(f.QTY) AS QTY
        FROM wb_fact f CROSS JOIN latest l
        LEFT JOIN wb_rec_year ry ON ry.MR_ID = f.MR_ID
        GROUP BY 1, 2, 3, 4, 5""")

    progress.note(f"{len(cube):,} territory / release-year combinations")
    country = defaultdict(lambda: defaultdict(float))
    by_release_year = defaultdict(lambda: [0.0, 0.0])           # streams, revenue
    by_release_x_consumption = defaultdict(lambda: [0.0, 0.0])
    for row in cube:
        code, seg, qty = row["COUNTRY_CODE"], row["SEGMENT"], _num(row["QTY"])
        revenue = qty * ppd_for(code, seg)
        stats = country[code]
        family = _segment_family(seg)
        stats[f"{family}_streams"] += qty
        stats[f"{family}_revenue"] += revenue
        if row["IS_LTM"]:
            stats["ltm_streams"] += qty
            stats["ltm_revenue"] += revenue
        if row["RELEASE_YEAR"] is not None:
            by_release_year[int(row["RELEASE_YEAR"])][0] += qty
            by_release_year[int(row["RELEASE_YEAR"])][1] += revenue
            key = (int(row["RELEASE_YEAR"]), int(row["CONSUMPTION_YEAR"]))
            by_release_x_consumption[key][0] += qty
            by_release_x_consumption[key][1] += revenue

    ranked_codes = sorted(country, key=lambda c: country[c]["audio_streams"] + country[c]["video_streams"], reverse=True)
    country_stats = [
        {"code": code, "country": _country_name(code),
         **{k: round(country[code][k], 4 if k.endswith("revenue") else 0) for k in
            ("audio_streams", "video_streams", "audio_revenue", "video_revenue", "ltm_streams", "ltm_revenue")}}
        for code in ranked_codes
    ]
    territories = {
        "countries": [_country_name(c) for c in ranked_codes],
        "codes": {_country_name(c): c for c in ranked_codes},
        "regions": _region_map(ranked_codes),
        "default_local": _default_local(assumptions, ranked_codes),
    }

    release_year_analysis, previous = [], None
    for year in sorted(by_release_year):
        streams, revenue = by_release_year[year]
        growth = round((streams - previous) / previous * 100, 1) if previous else 0
        release_year_analysis.append({"bucket": str(year), "consumption_streams": int(streams),
                                      "revenue_usd": round(revenue, 2), "yoy_growth_pct": growth})
        previous = streams
    release_year_consumption = [
        {"release_year": ry, "consumption_year": cy, "streams": int(streams), "revenue_usd": round(revenue, 2)}
        for (ry, cy), (streams, revenue) in sorted(by_release_x_consumption.items())
    ]

    # Albums: tracks per release group, and consumption/revenue attributed through rec_map.
    progress.stage("an_albums", "Counting tracks per album")
    track_counts = {
        str(r["MRELG_ID"]): int(r["TRACKS"])
        for r in _query(session, "SELECT MRELG_ID, COUNT(DISTINCT MR_ID) AS TRACKS FROM wb_rec_map GROUP BY 1")
    }
    progress.advance(0.4, "Attributing consumption to albums")
    album_total = defaultdict(float)
    album_revenue = defaultdict(float)
    album_ltm_revenue = defaultdict(float)
    album_country_revenue = defaultdict(lambda: defaultdict(float))
    for row in _query(session, f"""
        SELECT rm.MRELG_ID AS MRELG_ID, f.COUNTRY_CODE AS COUNTRY_CODE, f.SEGMENT AS SEGMENT,
               {_IS_LTM} AS IS_LTM, SUM(f.QTY) AS QTY
        FROM wb_fact f CROSS JOIN latest l
        JOIN wb_rec_map rm ON rm.MR_ID = f.MR_ID
        GROUP BY 1, 2, 3, 4"""):
        album_id, qty = str(row["MRELG_ID"]), _num(row["QTY"])
        revenue = qty * ppd_for(row["COUNTRY_CODE"], row["SEGMENT"])
        album_total[album_id] += qty
        album_revenue[album_id] += revenue
        if row["IS_LTM"]:
            album_ltm_revenue[album_id] += revenue
            album_country_revenue[album_id][row["COUNTRY_CODE"]] += revenue

    progress.note(f"{len(album_total):,} of {len(albums):,} albums have consumption")
    enriched = []
    for album in albums:
        album_id = str(album["album_id"]).strip()
        enriched.append({
            **album,
            "track_count": track_counts.get(album_id, album.get("track_count", 0)),
            "total_consumption_streams": int(album_total.get(album_id, 0)),
            # 4 dp (same as album_country_revenue) so album sums reconcile with Local + ROW.
            "lifetime_revenue_usd": round(album_revenue.get(album_id, 0.0), 4),
            "current_revenue_usd": round(album_ltm_revenue.get(album_id, 0.0), 4),
            "has_streaming_data": album_id in album_total,
        })
    compact_album_revenue = {
        album_id: {cc: rounded for cc, v in per_country.items() if (rounded := round(v, 4)) > 0}
        for album_id, per_country in album_country_revenue.items()
    }

    # New-release tracks: first-12-month consumption of recent recordings.
    progress.stage("an_tracks", "Analysing first-year performance of new releases")
    window_start = latest_year - int(assumptions["new_release_window_years"])
    tracks = _new_release_tracks(session, window_start)
    flag_new_release_tracks(tracks, latest_month)
    for track in tracks:
        track["first_12m_streams_millions"] = round(track["first_12m_streams"] / 1_000_000, 4)

    trend = growth_trend(monthly_totals)
    complete_years = [t for t in trend if not t["partial"] and t["yoy_growth_pct"] is not None]
    headline = (complete_years or [t for t in trend if t["yoy_growth_pct"] is not None] or [None])[-1]
    market_growth = {
        "artist_growth_pct": headline["yoy_growth_pct"] if headline else 0,
        "market_growth_pct": assumptions["market_growth_pct"],
        "growth_year": headline["year"] if headline else None,
        "growth_basis": ("like-for-like, %d months" % headline["months_compared"]) if headline and headline["partial"] else "full year",
        "market_source": assumptions["sources"]["market_growth_pct"],
    }

    older_years, recent_years = int(assumptions["older_catalog_years"]), int(assumptions["recent_catalog_years"])
    known_streams = sum(s for s, _ in by_release_year.values())
    if known_streams > 0:
        age_split = {
            "older_than_10y_pct": round(sum(s for y, (s, _) in by_release_year.items() if latest_year - y > older_years) / known_streams * 100),
            "recent_releases_pct": round(sum(s for y, (s, _) in by_release_year.items() if latest_year - y < recent_years) / known_streams * 100),
            "basis": "streams",
        }
    else:
        age_split = _age_split_from_albums(albums, latest_year, assumptions)
    age_split.update({"older_years": older_years, "recent_years": recent_years})

    ltm_start_index = int(latest_month[:4]) * 12 + int(latest_month[5:7]) - 11
    ltm_start = f"{(ltm_start_index - 1) // 12}-{(ltm_start_index - 1) % 12 + 1:02d}"
    return {
        "data_status": {
            "has_streaming_data": True, "first_month": first_month, "latest_month": latest_month,
            "ltm_window": f"{ltm_start} to {latest_month}", "ppd_source": ppd["source"], "ppd_note": ppd["note"],
            "coverage": coverage, "assumption_sources": assumptions["sources"],
        },
        "assumptions": {k: v for k, v in assumptions.items() if k != "sources"},
        "territories": territories,
        "country_stats": country_stats,
        "consumption_monthly": consumption_monthly,
        "consumption_matrix": half_year_matrix(consumption_monthly),
        "growth_trend": trend,
        "market_growth": market_growth,
        "catalog_age_split": age_split,
        "release_year_analysis": release_year_analysis,
        "release_year_consumption": release_year_consumption,
        "ppd": {"current_splits": ppd["current_splits"], "future_splits": ppd["future_splits"],
                "source": ppd["source"], "latest_year": ppd["latest_year"],
                "uplift_pct": assumptions["ppd_future_uplift_pct"]},
        "ppd_by_year": ppd["by_year"],
        "ppd_by_country": ppd["by_country"],
        "album_country_revenue": compact_album_revenue,
        "new_release_tracks": tracks,
        "albums": enriched,
    }


def half_year_matrix(consumption_monthly: list[dict]) -> list[dict]:
    """Roll monthly rows up to 'YYYY Jan-Jun' / 'YYYY Jul-Dec' buckets."""
    buckets = defaultdict(lambda: dict.fromkeys(SEGMENTS, 0))
    for row in consumption_monthly:
        year, month = row["ym"][:4], int(row["ym"][5:7])
        label = f"{year} {'Jan-Jun' if month <= 6 else 'Jul-Dec'}"
        for seg in SEGMENTS:
            buckets[label][seg] += row[seg]
    return [{"bucket": label, **values} for label, values in sorted(buckets.items())]


def _new_release_tracks(session, window_start_year: int) -> list[dict]:
    rows = session.sql(f"""
        WITH rec_month AS (SELECT MR_ID, MONTH_START_DATE, SUM(QTY) AS QTY FROM wb_fact GROUP BY 1, 2),
        rec_first AS (SELECT MR_ID, MIN(MONTH_START_DATE) AS FIRST_MONTH FROM rec_month GROUP BY 1),
        rec_info AS (SELECT MR_ID, MAX(TITLE) AS TITLE, MAX(ISRC) AS ISRC FROM {RECORDING_TABLE} GROUP BY 1)
        SELECT m.MR_ID AS MR_ID, i.TITLE AS TITLE, i.ISRC AS ISRC, ry.RELEASE_YEAR AS RELEASE_YEAR,
               rf.FIRST_MONTH AS FIRST_MONTH,
               SUM(CASE WHEN m.MONTH_START_DATE < rf.FIRST_MONTH + INTERVAL '12 months' THEN m.QTY ELSE 0 END) AS FIRST12,
               COUNT(DISTINCT CASE WHEN m.MONTH_START_DATE < rf.FIRST_MONTH + INTERVAL '12 months'
                                   THEN m.MONTH_START_DATE END) AS MONTHS12
        FROM rec_month m
        JOIN rec_first rf ON rf.MR_ID = m.MR_ID
        JOIN wb_rec_year ry ON ry.MR_ID = m.MR_ID
        LEFT JOIN rec_info i ON i.MR_ID = m.MR_ID
        WHERE ry.RELEASE_YEAR >= {int(window_start_year)}
        GROUP BY 1, 2, 3, 4, 5
        ORDER BY FIRST12 DESC
        LIMIT 100
    """).collect()
    return [
        {
            "track_id": str(r["MR_ID"]),
            "track_name": str(r["TITLE"] or "Unknown"),
            "isrc": str(r["ISRC"] or ""),
            "release_year": int(r["RELEASE_YEAR"]),
            "first_month": _month_key(r["FIRST_MONTH"]),
            "first_12m_streams": int(_num(r["FIRST12"])),
            "months_of_data": int(_num(r["MONTHS12"])),
        }
        for r in rows
    ]
