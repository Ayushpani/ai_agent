"""Deterministic probe SQL construction (deep-research layer).

The research planner is an LLM: it chooses WHICH follow-up investigation
is worth running and against which metric/dimension. This module decides
HOW that becomes SQL, from a fixed template per probe type.

Two reasons it works this way rather than asking the model for more SQL:

  1. Reliability. Free-tier models are already unreliable at writing one
     correct query; four more free-form statements multiply that.
  2. Safety. The only LLM-chosen values that reach SQL here are a metric
     and a dimension column name, and both are allow-listed against the
     caller's role-filtered schema card before substitution. A column the
     planner invented, or one its role may not see, is rejected outright
     rather than interpolated.

Every template still carries {ACCESS_SCOPE_FILTER} and still goes through
run_sql, so the row-level scope and the SQL validator apply exactly as
they do to the primary query.
"""
from __future__ import annotations

import re

from app.models.schemas import ChartSpec, ChartType, ProbeSpec, ProbeType
from app.tools.data import get_schema_card

BASE_TABLE = "main"
TIME_COLUMN = "snapshot_month"

# Belt-and-braces on top of the allow-list: even an allow-listed name has
# to look like a plain SQL identifier before it is interpolated.
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class ProbeBuildError(ValueError):
    """The probe cannot be built — unknown/denied column, or a probe type
    that needs a dimension and wasn't given one."""


def queryable_columns(role: str | None) -> set[str]:
    """Every column name the given role is allowed to see on `main`,
    taken from the same role-filtered schema card the SQL Generator is
    grounded on. This is the allow-list probe columns are checked against.
    """
    card = get_schema_card(role=role)
    names: set[str] = set()
    for domain in card.get("domains", {}).values():
        if domain.get("table") != BASE_TABLE:
            continue
        for col in domain.get("columns", []):
            names.add(col["name"])
    return names


def _check_column(name: str, allowed: set[str], kind: str) -> str:
    if name not in allowed:
        raise ProbeBuildError(
            f"{kind} column '{name}' is not in the caller's schema card "
            f"— refusing to interpolate an unknown or role-denied column."
        )
    if not _IDENTIFIER_RE.match(name):
        raise ProbeBuildError(f"{kind} column '{name}' is not a plain identifier.")
    return name


def build_probe_sql(spec: ProbeSpec, role: str | None) -> tuple[str, ChartSpec]:
    """Returns (sql, chart_spec) for a probe. Raises ProbeBuildError if the
    planner's column choices don't pass the allow-list.
    """
    allowed = queryable_columns(role)
    metric = _check_column(spec.metric, allowed, "metric")

    needs_dimension = spec.probe_type in {
        ProbeType.decompose_by,
        ProbeType.trend_by_segment,
        ProbeType.period_comparison,
        ProbeType.concentration,
    }
    dimension: str | None = None
    if needs_dimension:
        if not spec.dimension:
            raise ProbeBuildError(f"probe type '{spec.probe_type.value}' requires a dimension.")
        dimension = _check_column(spec.dimension, allowed, "dimension")

    top_n = int(spec.top_n)

    if spec.probe_type is ProbeType.decompose_by:
        sql = f"""
            SELECT {dimension} AS segment, SUM({metric}) AS value
            FROM {BASE_TABLE}
            WHERE {TIME_COLUMN} = (SELECT MAX({TIME_COLUMN}) FROM {BASE_TABLE})
              AND {{ACCESS_SCOPE_FILTER}}
            GROUP BY {dimension}
            ORDER BY value DESC
            LIMIT {top_n}
        """
        chart = ChartSpec(chart_type=ChartType.bar, x_field="segment", y_field="value")

    elif spec.probe_type is ProbeType.concentration:
        # Same shape as decompose_by; the difference is downstream — the
        # concentration index is computed on the result and surfaced as
        # the panel headline.
        sql = f"""
            SELECT {dimension} AS segment, SUM({metric}) AS value
            FROM {BASE_TABLE}
            WHERE {TIME_COLUMN} = (SELECT MAX({TIME_COLUMN}) FROM {BASE_TABLE})
              AND {{ACCESS_SCOPE_FILTER}}
            GROUP BY {dimension}
            ORDER BY value DESC
            LIMIT {top_n}
        """
        chart = ChartSpec(chart_type=ChartType.bar, x_field="segment", y_field="value")

    elif spec.probe_type is ProbeType.trend_by_segment:
        sql = f"""
            WITH top_segments AS (
                SELECT {dimension} AS segment
                FROM {BASE_TABLE}
                WHERE {{ACCESS_SCOPE_FILTER}}
                GROUP BY {dimension}
                ORDER BY SUM({metric}) DESC
                LIMIT {top_n}
            )
            SELECT {TIME_COLUMN} AS period, {dimension} AS segment, SUM({metric}) AS value
            FROM {BASE_TABLE}
            WHERE {dimension} IN (SELECT segment FROM top_segments)
              AND {{ACCESS_SCOPE_FILTER}}
            GROUP BY {TIME_COLUMN}, {dimension}
            ORDER BY {TIME_COLUMN} ASC
        """
        chart = ChartSpec(
            chart_type=ChartType.multi_line, x_field="period", y_field="value", series_field="segment"
        )

    elif spec.probe_type is ProbeType.period_comparison:
        sql = f"""
            SELECT
                {dimension} AS segment,
                SUM(CASE WHEN {TIME_COLUMN} = (SELECT MIN({TIME_COLUMN}) FROM {BASE_TABLE})
                    THEN {metric} ELSE 0 END) AS first_period,
                SUM(CASE WHEN {TIME_COLUMN} = (SELECT MAX({TIME_COLUMN}) FROM {BASE_TABLE})
                    THEN {metric} ELSE 0 END) AS latest_period
            FROM {BASE_TABLE}
            WHERE {{ACCESS_SCOPE_FILTER}}
            GROUP BY {dimension}
            ORDER BY latest_period DESC
            LIMIT {top_n}
        """
        chart = ChartSpec(
            chart_type=ChartType.grouped_bar,
            x_field="segment",
            value_fields=["first_period", "latest_period"],
        )

    elif spec.probe_type is ProbeType.distribution:
        sql = f"""
            SELECT
                bucket,
                COUNT(*) AS loan_count,
                SUM(metric_value) AS value
            FROM (
                SELECT NTILE(10) OVER (ORDER BY {metric}) AS bucket, {metric} AS metric_value
                FROM {BASE_TABLE}
                WHERE {metric} IS NOT NULL AND {metric} > 0
                  AND {{ACCESS_SCOPE_FILTER}}
            )
            GROUP BY bucket
            ORDER BY bucket
        """
        chart = ChartSpec(chart_type=ChartType.bar, x_field="bucket", y_field="loan_count")

    elif spec.probe_type is ProbeType.related_metric:
        sql = f"""
            SELECT {TIME_COLUMN} AS period, SUM({metric}) AS value
            FROM {BASE_TABLE}
            WHERE {{ACCESS_SCOPE_FILTER}}
            GROUP BY {TIME_COLUMN}
            ORDER BY {TIME_COLUMN} ASC
        """
        chart = ChartSpec(chart_type=ChartType.line, x_field="period", y_field="value")

    else:  # pragma: no cover — ProbeType is a closed enum
        raise ProbeBuildError(f"unsupported probe type: {spec.probe_type}")

    return _tidy(sql), chart


def _tidy(sql: str) -> str:
    """Strips the template's leading indentation but KEEPS line breaks —
    this SQL is shown to the employee in the panel's SQL view and written
    into the workbook, and a single 400-character line is unreadable in
    both.
    """
    lines = [line.rstrip() for line in sql.strip("\n").splitlines()]
    lines = [line for line in lines if line.strip()]
    if not lines:
        return ""
    indent = min(len(line) - len(line.lstrip()) for line in lines)
    return "\n".join(line[indent:] for line in lines)
