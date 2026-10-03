"""Shared constants for the M&A Catalog Valuation Workbench."""

import os
import re

try:
    from dotenv import load_dotenv
    load_dotenv()
except ModuleNotFoundError:
    pass

DATABASE = os.getenv("APP_DATABASE", "catalogue_valuation")
SCHEMA = os.getenv("APP_SCHEMA", "lai_app")
DB = SCHEMA

LUMINATE_DATABASE = os.getenv("LUMINATE_DATABASE", DATABASE)
LUMINATE_SCHEMA = os.getenv("LUMINATE_SCHEMA", "extract_s")

ANALYTICS_DATABASE = os.getenv("ANALYTICS_DATABASE", DATABASE)
ANALYTICS_SCHEMA = os.getenv("ANALYTICS_SCHEMA", SCHEMA)

MAX_STEP = 8
MIN_STEP = 1
CACHE_TTL_SECONDS = int(os.getenv("DATABASE_CACHE_TTL", "600"))
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")

STEP_LABELS = [
    "Catalog select",
    "Resolve ambiguity",
    "Metadata to include",
    "Territory map",
    "Catalog analytics",
    "Revenue & PPD",
    "Album analytics",
    "Corporate export",
]

# ─── Steps 4-8 analytics ─────────────────────────────────────────────────────
# Source tables (all overridable through the environment).
MONTHLY_SUMMARY_TABLE = f"{LUMINATE_SCHEMA}.monthly_mr_summary"
PRODUCT_CATALOG_TABLE = f"{LUMINATE_SCHEMA}.product_catalog"
RECORDING_TABLE = f"{LUMINATE_SCHEMA}.vw_musical_recording_ds"
PPD_TABLE_NAME = os.getenv("PPD_TABLE", "SAMIS_FACT_BOBWA_AV_YEARLY_PPD")

# Rows that must not be counted as consumption (aggregates / unmapped values).
EXCLUDED_CONTENT_TYPES = ("Total", "LUMINATE_NULL")
EXCLUDED_COMMERCIAL_MODELS = ("LUMINATE_NULL",)
# Luminate uses this code for consumption that is not allocated to a country.
UNALLOCATED_COUNTRY_CODE = "AA"

# Values below can only be *assumed* when no table provides them. Each one can be
# overridden without a code change by inserting a row into {APP_SCHEMA}.config
# (CONFIG_KEY / CONFIG_VALUE, JSON values) — see analytics.load_assumptions().
DEFAULT_ASSUMPTIONS = {
    # Wholesale revenue per stream, used only when the PPD table is unavailable.
    "ppd_current_splits": {
        "audio_premium": 0.0038,
        "audio_ad_supported": 0.0015,
        "video_premium": 0.0020,
        "video_ad_supported": 0.0007,
    },
    "ppd_future_uplift_pct": 5.0,
    "market_growth_pct": 7.0,
    "expected_growth": 8.0,
    "expected_decay": -6.0,
    "projected_tracks": 10,
    # Empty -> the top DEFAULT_LOCAL_TERRITORY_COUNT countries by consumption.
    "default_local_territories": [],
    "default_local_territory_count": 3,
    "new_release_window_years": 3,
    "older_catalog_years": 10,
    "recent_catalog_years": 5,
}

# Reference taxonomy (not data): which ISO country codes roll up to which region.
REGION_CODES = {
    "Latin America": ["MX", "CO", "AR", "BR", "CL", "PE", "EC", "VE", "UY", "PY", "BO", "CR", "PA", "DO", "GT", "HN", "SV", "NI", "CU", "PR"],
    "North America": ["US", "CA"],
    "Europe": ["GB", "DE", "FR", "ES", "IT", "NL", "SE", "NO", "DK", "FI", "PT", "BE", "AT", "CH", "IE", "PL", "CZ", "RO", "HU", "GR"],
    "Asia Pacific": ["JP", "KR", "AU", "NZ", "IN", "ID", "TH", "PH", "MY", "SG", "TW", "HK", "VN"],
    "Middle East & Africa": ["ZA", "NG", "KE", "EG", "AE", "SA", "IL", "TR", "GH"],
}

# ISO country code -> display name (reference data).
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
    "PR": "Puerto Rico", "GH": "Ghana",
    "AA": "Unallocated (AA)",
}
