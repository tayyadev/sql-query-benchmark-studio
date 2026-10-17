"""Defensive offline analysis of SQL Server ShowPlan XML.

Cost values are SQL Server optimizer *estimates*, not measured milliseconds.
No network requests, database connections or user SQL execution occur here.
"""

from __future__ import annotations

import hashlib
import math
import xml.etree.ElementTree as ET
from collections import Counter
from typing import Any

MAX_PLAN_BYTES = 2 * 1024 * 1024
MAX_XML_NODES = 20_000
MAX_OPERATORS = 300


class PlanError(ValueError):
    """Invalid or unsupported ShowPlan document."""


def _name(node: ET.Element) -> str:
    return node.tag.rpartition("}")[2] if "}" in node.tag else node.tag


def _number(value: Any) -> float | None:
    try:
        number = float(value)
        return round(number, 6) if math.isfinite(number) else None
    except (TypeError, ValueError, OverflowError):
        return None


def analyze_plan(xml: str | bytes) -> dict[str, Any]:
    if not isinstance(xml, (str, bytes)):
        raise PlanError("Supply a ShowPlan XML string.")
    encoded = xml.encode("utf-8") if isinstance(xml, str) else xml
    if len(encoded) > MAX_PLAN_BYTES:
        raise PlanError("The plan exceeds the 2 MiB size limit.")
    if b"<!doctype" in encoded.lower() or b"<!entity" in encoded.lower():
        raise PlanError("DTD and entity definitions are not accepted.")
    try:
        root = ET.fromstring(encoded)
    except ET.ParseError as exc:
        raise PlanError("The file is not valid XML.") from exc
    if _name(root) != "ShowPlanXML":
        raise PlanError("Expected a SQL Server ShowPlanXML root element.")

    nodes = []
    for node in root.iter():
        nodes.append(node)
        if len(nodes) > MAX_XML_NODES:
            raise PlanError("Too many XML nodes in this document.")
    statements = [node for node in nodes if _name(node).startswith("Stmt")
                  and ("StatementSubTreeCost" in node.attrib or "StatementText" in node.attrib)]
    operators = [node for node in nodes if _name(node) == "RelOp"]
    if not statements and not operators:
        raise PlanError("No query statements or relational operators were found.")

    statement_data = []
    for i, stmt in enumerate(statements, 1):
        statement_text = stmt.get("StatementText", "")
        statement_data.append({
            "number": i,
            "type": stmt.get("StatementType", "Unknown"),
            "estimated_subtree_cost": _number(stmt.get("StatementSubTreeCost")),
            # Never return statement text or query literals in diagnostic JSON.
            "query_sha256": hashlib.sha256(statement_text.encode("utf-8")).hexdigest()
            if statement_text else None,
        })

    operator_data = []
    operator_counts: Counter[str] = Counter()
    scans = 0
    spills = 0
    missing_index_groups: list[dict[str, Any]] = []
    for op in operators:
        physical = op.get("PhysicalOp", "Unknown")
        operator_counts[physical] += 1
        if "Scan" in physical:
            scans += 1
        warning_types = sorted({
            _name(item) for item in op.iter()
            if _name(item) in {"SpillToTempDb", "SortSpillDetails", "HashSpillDetails", "NoJoinPredicate"}
        })
        if any("Spill" in key for key in warning_types):
            spills += 1
        actual_rows = 0.0
        has_actual = False
        for child in op.iter():
            if _name(child) == "RunTimeCountersPerThread":
                n = _number(child.get("ActualRows"))
                if n is not None:
                    has_actual = True
                    actual_rows += n
        operator_data.append({
            "node_id": op.get("NodeId"),
            "physical_op": physical,
            "logical_op": op.get("LogicalOp", "Unknown"),
            "estimated_rows": _number(op.get("EstimateRows")),
            "actual_rows": round(actual_rows, 3) if has_actual else None,
            "estimated_subtree_cost": _number(op.get("EstimatedTotalSubtreeCost")),
            "warnings": warning_types,
        })

    for node in nodes:
        if _name(node) != "MissingIndexGroup":
            continue
        impact = _number(node.get("Impact"))
        indexes = [child for child in node.iter() if _name(child) == "MissingIndex"]
        for idx in indexes:
            # Table identifiers are reportable metadata, not automatically trusted DDL.
            columns: dict[str, list[str]] = {}
            for group in idx:
                if _name(group) != "ColumnGroup":
                    continue
                usage = group.get("Usage", "OTHER")
                columns[usage] = [c.get("Name", "")[:128] for c in group
                                  if _name(c) == "Column"][:30]
            missing_index_groups.append({
                "impact_estimate_percent": impact,
                "table": (idx.get("Table") or "")[:128],
                "columns": columns,
            })

    # A relational operator subtree estimate is inclusive of its descendants.
    # Never sum these values to estimate full query cost.
    ordered = sorted(operator_data, key=lambda op: op["estimated_subtree_cost"] or 0, reverse=True)
    estimated_total = round(sum(s["estimated_subtree_cost"] for s in statement_data
                                if s["estimated_subtree_cost"] is not None), 6)
    findings: list[dict[str, str]] = []
    if scans:
        findings.append({"level": "info", "code": "scans", "message":
                         f"{scans} scan operator(s) detected. Scans can be optimal for small tables."})
    if spills:
        findings.append({"level": "warning", "code": "spills", "message":
                         f"{spills} operator(s) report potential tempdb spills; inspect memory grants."})
    if missing_index_groups:
        findings.append({"level": "info", "code": "index_hints", "message":
                         "Optimizer-reported missing-index candidates require workload validation."})
    if not findings:
        findings.append({"level": "info", "code": "review", "message":
                         "No scan, spill or missing-index indicators detected in the provided plan."})
    return {
        "format": "sqlserver-showplan", "statements": statement_data,
        "statement_count": len(statement_data), "operator_count": len(operators),
        "estimated_statement_cost_total": estimated_total,
        "operator_counts": dict(sorted(operator_counts.items())),
        "top_operators": ordered[:MAX_OPERATORS],
        "missing_indexes": missing_index_groups[:50],
        "findings": findings,
        "disclaimer": "Estimated optimizer costs are dimensionless and not execution durations. "
                      "Missing-index hints are suggestions, not instructions to create indexes.",
        "truncated_operators": len(operators) > MAX_OPERATORS,
    }


def compare_plans(before: str | bytes, after: str | bytes) -> dict[str, Any]:
    left, right = analyze_plan(before), analyze_plan(after)
    a, b = left["estimated_statement_cost_total"], right["estimated_statement_cost_total"]
    delta = round(((b - a) / a * 100), 2) if a else None
    return {
        "before": left, "after": right,
        "comparison": {
            "estimated_cost_delta_percent": delta,
            "operator_count_delta": right["operator_count"] - left["operator_count"],
            "same_statement_hashes": [s["query_sha256"] for s in left["statements"]] ==
                                     [s["query_sha256"] for s in right["statements"]],
            "caveat": "Compare optimizer costs only for equivalent queries in comparable environments. "
                      "This does not demonstrate real-world execution speed.",
        },
    }
