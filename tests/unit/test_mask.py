import pandas as pd

from ingestion.mask import deterministic_hash, mask_pii


def test_mask_pii_nulls_direct_identity_fields():
    df = pd.DataFrame({"CUSTOMERNAME": ["Alice"], "UDYOG_AADHAR_NO": ["1234"]})
    masked = mask_pii(df)
    assert masked["CUSTOMERNAME"].isna().all()
    assert masked["UDYOG_AADHAR_NO"].isna().all()


def test_mask_pii_hashes_identifiers_deterministically():
    df = pd.DataFrame({"CUSTOMER_ID": ["CUST1", "CUST1", "CUST2"]})
    masked = mask_pii(df)
    assert masked["CUSTOMER_ID"].iloc[0] == masked["CUSTOMER_ID"].iloc[1]
    assert masked["CUSTOMER_ID"].iloc[0] != masked["CUSTOMER_ID"].iloc[2]
    assert masked["CUSTOMER_ID"].iloc[0] != "CUST1"  # not recoverable in plaintext


def test_mask_pii_reduces_dob_to_birth_year():
    df = pd.DataFrame({"DOB": pd.to_datetime(["1990-05-01"])})
    masked = mask_pii(df)
    assert "DOB" not in masked.columns
    assert masked["BIRTH_YEAR"].iloc[0] == 1990


def test_deterministic_hash_stable_across_calls():
    assert deterministic_hash("CUST1") == deterministic_hash("CUST1")


def test_deterministic_hash_none_for_null():
    assert deterministic_hash(None) is None
