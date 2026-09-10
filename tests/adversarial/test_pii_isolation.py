"""PII-leak audit (doc §9.1, §9.4): direct PII must never survive
ingestion, and the schema card handed to the SQL Generator must never
expose pending-SME or role-denied columns.
"""
import pandas as pd

from app.tools.data import get_schema_card
from app.tools.workbook import EXCLUDED_EXPORT_COLUMNS, build_excel_workbook
from app.models.schemas import ChartSpec, ChartType
from ingestion.mask import mask_pii


def _flatten_column_names(schema_card: dict) -> set[str]:
    names = set()
    for domain in schema_card["domains"].values():
        for col in domain["columns"]:
            names.add(col["name"])
    return names


def test_schema_card_never_exposes_pending_sme_columns():
    card = get_schema_card(role="admin")
    names = _flatten_column_names(card)
    assert "AUF_1PLUS_LAN" not in names


def test_schema_card_denies_employee_attribution_columns_for_region_manager():
    card = get_schema_card(role="region_manager")
    names = _flatten_column_names(card)
    assert "DSA" not in names
    assert "CONNECTOR_NAME" not in names


def test_schema_card_grants_sourcing_domain_only_to_allowed_roles():
    admin_card = get_schema_card(role="admin")
    unrelated_card = get_schema_card(role="branch_manager")
    assert "sourcing" not in unrelated_card["domains"]


def test_excel_export_excludes_direct_and_pseudo_pii_by_default():
    df = pd.DataFrame({
        "LOAN_AGREEMENT_NO": ["L1"], "UCID": ["hash1"], "CUSTOMER_ID": ["hash2"],
        "CUSTOMERNAME": [None], "PRINCIPAL_OS": [1000.0],
    })
    spec = ChartSpec(chart_type=ChartType.kpi_callout)
    wb_bytes = build_excel_workbook(df, spec, "q", "SELECT 1", "EMP1", ["2026-08"])
    assert len(wb_bytes) > 0

    # Check the Data sheet specifically — the excluded columns must not
    # appear as actual columns there. (The Cover sheet's disclaimer prose
    # legitimately names them, e.g. "UCID ... are excluded by default",
    # which a whole-workbook substring search would wrongly flag.)
    import io
    data_df = pd.read_excel(io.BytesIO(wb_bytes), sheet_name="Data")
    for col in EXCLUDED_EXPORT_COLUMNS:
        assert col not in data_df.columns


def test_mask_pii_leaves_no_plaintext_customer_name():
    df = pd.DataFrame({"CUSTOMERNAME": ["Real Person Name"]})
    masked = mask_pii(df)
    assert "Real Person Name" not in masked.to_string()
