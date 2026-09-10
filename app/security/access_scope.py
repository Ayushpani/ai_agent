"""Access-scope resolution — doc §9.2.

Row-level filter substitution happens here, AFTER SQL generation, using
values the LLM never sees. Column-level access (which columns the SQL
generator is even told exist) is enforced separately in
app/tools/data.py:get_schema_card, driven by the same policy file.
"""
from __future__ import annotations

from pathlib import Path
from functools import lru_cache

import yaml

from app.models.schemas import AccessScope
from app.security.sql_validator import ACCESS_SCOPE_PLACEHOLDER

CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "access_policies.yaml"


@lru_cache(maxsize=1)
def _load_policies() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def resolve_row_filter(scope: AccessScope) -> str:
    policies = _load_policies()
    role_policy = policies["roles"].get(scope.role, policies["default_deny"])
    template = role_policy["row_filter"]
    return template.format(
        employee_region=_sql_quote(scope.employee_region),
        employee_branch=_sql_quote(scope.employee_branch),
    )


def resolve_denied_columns(role: str) -> list[str]:
    policies = _load_policies()
    role_policy = policies["roles"].get(role, policies["default_deny"])
    return list(role_policy.get("denied_columns", []))


def substitute_access_scope(sql: str, scope: AccessScope) -> str:
    """The one place {ACCESS_SCOPE_FILTER} is ever replaced. The employee's
    role determines the filter regardless of what the LLM produced — the
    LLM cannot control this because it never sees these values.
    """
    row_filter = resolve_row_filter(scope)
    if ACCESS_SCOPE_PLACEHOLDER not in sql:
        raise ValueError("Cannot substitute access scope: placeholder missing from SQL.")
    return sql.replace(ACCESS_SCOPE_PLACEHOLDER, row_filter)


def _sql_quote(value: str | None) -> str:
    if value is None:
        return "NULL"
    escaped = value.replace("'", "''")
    return f"'{escaped}'"
