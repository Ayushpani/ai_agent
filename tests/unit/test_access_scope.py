from app.models.schemas import AccessScope
from app.security.access_scope import resolve_denied_columns, substitute_access_scope


def test_region_manager_scoped_to_their_region():
    scope = AccessScope(employee_id="E1", role="region_manager", employee_region="Maharashtra")
    sql = "SELECT * FROM main WHERE {ACCESS_SCOPE_FILTER}"
    final = substitute_access_scope(sql, scope)
    assert "REGION = 'Maharashtra'" in final


def test_admin_sees_all_rows():
    scope = AccessScope(employee_id="E1", role="admin")
    final = substitute_access_scope("SELECT * FROM main WHERE {ACCESS_SCOPE_FILTER}", scope)
    assert "TRUE" in final


def test_unknown_role_fails_closed():
    scope = AccessScope(employee_id="E1", role="nonexistent_role")
    final = substitute_access_scope("SELECT * FROM main WHERE {ACCESS_SCOPE_FILTER}", scope)
    assert "FALSE" in final


def test_denied_columns_include_employee_attribution_for_region_manager():
    denied = resolve_denied_columns("region_manager")
    assert "DSA" in denied
    assert "CONNECTOR_NAME" in denied


def test_sql_injection_via_region_field_is_escaped():
    scope = AccessScope(employee_id="E1", role="region_manager", employee_region="X' OR '1'='1")
    final = substitute_access_scope("SELECT * FROM main WHERE {ACCESS_SCOPE_FILTER}", scope)
    assert "OR '1'='1'" not in final.replace("''", "")
    assert "REGION = 'X'' OR ''1''=''1'" in final
