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
