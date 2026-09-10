"""Synthetic loan-portfolio MIS generator.

Doc §9.3: 'For the POC demo itself, use synthetic or scrambled data unless
[client DPDP/InfoSec sign-off] is already in hand.' This generator produces
a shape-compatible fake extract (including monthly-suffixed bounce/IRAC
column groups) so the ingestion pipeline, tools, and demo can run end to
end before real data or sign-off exists.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

STATES = ["Maharashtra", "Gujarat", "Karnataka", "Tamil Nadu", "Rajasthan"]
PRODUCTS = ["HL", "LAP", "BL-STL", "MSE"]
MONTHS = ["Mar 26", "Apr 26", "May 26", "Jun 26", "Jul 26", "Aug 26"]


def generate_synthetic_mis(n_loans: int = 2000, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)

    df = pd.DataFrame({
        "LOAN_AGREEMENT_NO": [f"LAN{100000 + i}" for i in range(n_loans)],
        "UCID": [f"UCIC{50000 + (i // 2)}" for i in range(n_loans)],
        "CUSTOMER_ID": [f"CUST{50000 + (i // 2)}" for i in range(n_loans)],
        "CUSTOMERNAME": [f"Borrower {i}" for i in range(n_loans)],
        "PRODUCT": rng.choice(PRODUCTS, n_loans),
        "LOAN_STATUS": rng.choice(["Active", "Closed"], n_loans, p=[0.85, 0.15]),
        "BRANCH_NAME": rng.choice([f"Branch-{s[:3].upper()}-{i%5}" for i, s in enumerate(STATES)], n_loans),
        "REGION": rng.choice(["North", "South", "East", "West"], n_loans),
        "STATE": rng.choice(STATES, n_loans),
        "ZONE": rng.choice(["Zone-1", "Zone-2", "Zone-3"], n_loans),
        "SANCTION_AMOUNT": rng.uniform(200000, 5000000, n_loans).round(2),
        "LOAN_AMOUNT": rng.uniform(200000, 5000000, n_loans).round(2),
        "BOOKING_ROI": rng.uniform(8.5, 14.0, n_loans).round(2),
        "ROI": rng.uniform(8.5, 15.0, n_loans).round(2),
        "TENURE": rng.integers(12, 240, n_loans),
        "PRINCIPAL_OS": rng.uniform(50000, 4000000, n_loans).round(2),
        "CIBIL_SCORE": rng.integers(600, 900, n_loans),
        "COLENDING_FLAG": rng.choice([True, False], n_loans, p=[0.3, 0.7]),
        "INVESTOR_SHARING_RATIO": rng.uniform(0.5, 0.8, n_loans).round(2),
        "DSA": rng.choice([f"DSA-{i}" for i in range(20)], n_loans),
        "DME": rng.choice([f"DME-{i}" for i in range(10)], n_loans),
        "CONNECTOR_NAME": rng.choice([f"Connector-{i}" for i in range(15)], n_loans),
        "DOB": pd.to_datetime(rng.integers(-1_600_000_000, -200_000_000, n_loans), unit="s"),
    })
    df["OWN_SHARING_RATIO"] = 1 - df["INVESTOR_SHARING_RATIO"]

    dpd = rng.choice([0, 15, 35, 65, 95, 150], n_loans, p=[0.6, 0.15, 0.1, 0.08, 0.05, 0.02])
    df["AUM_1PLUS_LAN"] = np.where(dpd >= 1, df["PRINCIPAL_OS"], 0)
    df["AUM_30PLUS_LAN"] = np.where(dpd >= 30, df["PRINCIPAL_OS"], 0)
    df["AUM_60PLUS_LAN"] = np.where(dpd >= 60, df["PRINCIPAL_OS"], 0)
    df["AUM_90PLUS_LAN"] = np.where(dpd >= 90, df["PRINCIPAL_OS"], 0)
    df["AUM_90PLUS_UCIC"] = df["AUM_90PLUS_LAN"] * 0.98
    df["AUM_90PLUS_FINANCE_OWNSHARE"] = df["AUM_90PLUS_LAN"] * df["OWN_SHARING_RATIO"]

    # Monthly-suffixed column groups (doc §2.1.1) — exercises the melt module.
    for month in MONTHS:
        base_bounce_rate = rng.uniform(0.03, 0.06)
        df[f"Bounce {month}"] = rng.choice(
            [0, 1], n_loans, p=[1 - base_bounce_rate, base_bounce_rate]
        )
        df[f"IRAC LAN Level {month}"] = rng.choice(
            ["Standard", "SMA-0", "SMA-1", "SMA-2", "NPA"],
            n_loans,
            p=[0.85, 0.06, 0.04, 0.02, 0.03],
        )

    return df


if __name__ == "__main__":
    out = generate_synthetic_mis()
    print(out.shape)
    print(out.columns.tolist())
