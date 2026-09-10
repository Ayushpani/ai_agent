"""PII masking — stage [3] of the ingestion pipeline (doc §5.1).

Enforced here, not by prompt discipline: this module runs before any
DataFrame is registered with DuckDB or written to Parquet, so no
downstream consumer (LLM, tool, export) ever sees a raw PII value.
"""
from __future__ import annotations

import hashlib
import hmac
import os

import pandas as pd

# Deterministic hash secret. In production this comes from AWS SSM;
# for the POC it comes from the environment so re-running ingestion on
# the same month yields stable join keys without persisting a mapping table.
_HASH_SECRET = os.environ.get("PII_HASH_SECRET", "poc-local-secret-do-not-use-in-prod").encode()

DIRECT_PII_NULL_COLUMNS = [
    "CUSTOMERNAME",
    "UDYOG_AADHAR_NO",
]

DIRECT_PII_HASH_COLUMNS = [
    "CUSTOMER_ID",
    "UCID",
]

DOB_COLUMN = "DOB"


def deterministic_hash(value: object) -> str | None:
    """HMAC-SHA256 of the value, hex-truncated. Stable across ingestion runs
    (same secret, same input -> same output) so joins on the masked key
    still work, but the original value is not recoverable from the hash.
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    digest = hmac.new(_HASH_SECRET, str(value).encode(), hashlib.sha256).hexdigest()
    return digest[:24]


def mask_pii(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of df with direct-PII columns masked or nulled.

    - Free-text identity (name, Aadhaar) -> null.
    - Stable identifiers (customer/UCID) -> deterministic hash, preserving
      join stability across snapshot months.
    - DOB -> retained as birth year only, for age-bracket analysis.
    """
    out = df.copy()

    for col in DIRECT_PII_NULL_COLUMNS:
        if col in out.columns:
            out[col] = None

    for col in DIRECT_PII_HASH_COLUMNS:
        if col in out.columns:
            out[col] = out[col].map(deterministic_hash)

    if DOB_COLUMN in out.columns:
        parsed = pd.to_datetime(out[DOB_COLUMN], errors="coerce")
        out[DOB_COLUMN] = parsed.dt.year
        out = out.rename(columns={DOB_COLUMN: "BIRTH_YEAR"})

    return out
