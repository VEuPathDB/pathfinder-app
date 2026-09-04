"""Render the PathFinder observability pack into SigNoz-friendly artifacts.

This script keeps the source pack neutral while producing:

- importable SigNoz dashboard JSON files
- an alert catalog for SigNoz UI and shared environment workflows
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
PACK_PATH = ROOT / "pathfinder-observability-pack.json"
DASHBOARDS_DIR = ROOT / "dashboards"
ALERTS_DIR = ROOT / "alerts"
FILTER_GUIDE_PATH = ROOT / "dashboard-filters.md"

GRID_WIDTH = 24
WIDGET_WIDTH = 12
WIDGET_HEIGHT = 8


def _slugify(value: str) -> str:
    return (
        value.lower()
        .replace(" ", "-")
        .replace("/", "-")
        .replace(".", "-")
        .replace("_", "-")
    )


def _load_pack() -> dict[str, Any]:
    return json.loads(PACK_PATH.read_text())


def _widget_layout(panel_count: int) -> list[dict[str, Any]]:
    layout: list[dict[str, Any]] = []
    for index in range(panel_count):
        row = index // 2
        col = index % 2
        layout.append(
            {
                "h": WIDGET_HEIGHT,
                "i": f"widget-{index + 1}",
                "moved": False,
                "static": False,
                "w": WIDGET_WIDTH,
                "x": col * WIDGET_WIDTH,
                "y": row * WIDGET_HEIGHT,
            }
        )
    return layout


_HISTOGRAM_PERCENTILES = {"p50", "p75", "p90", "p95", "p99"}


def _aggregate_attribute(panel: dict[str, Any]) -> dict[str, Any]:
    """Build the canonical SigNoz ``aggregateAttribute`` object for a metric.

    SigNoz v0.118 stores OTel histograms in OpenMetrics-flattened form, so
    percentile queries must reference ``<metric>.bucket`` directly.  The
    ``id`` field follows the SigNoz convention ``<key>--<dataType>--<type>--<isColumn>``
    that the metrics autocomplete API returns.
    """
    metric_type = panel["metricType"]
    is_histogram_percentile = (
        metric_type == "Histogram"
        and panel["aggregateOperator"] in _HISTOGRAM_PERCENTILES
    )
    key = panel["metric"]
    if is_histogram_percentile and not key.endswith(".bucket"):
        key = f"{key}.bucket"
    data_type = "float64"
    is_column = True
    return {
        "dataType": data_type,
        "id": f"{key}--{data_type}--{metric_type}--{str(is_column).lower()}",
        "isColumn": is_column,
        "isJSON": False,
        "key": key,
        "type": metric_type,
    }


def _aggregation_modes(panel: dict[str, Any]) -> tuple[str, str, str]:
    """Return ``(aggregateOperator, spaceAggregation, timeAggregation)``.

    SigNoz v0.118 splits an "operator" into a per-series time aggregation
    (rate / latest / sum / ...) and a cross-series space aggregation
    (sum / avg / pXX / ...).  The PathFinder pack uses high-level operator
    names so this helper expands each one to the full triple.
    """
    op = panel["aggregateOperator"]
    metric_type = panel["metricType"]
    if metric_type == "Histogram" and op in _HISTOGRAM_PERCENTILES:
        return ("count", op, "")
    if op == "rate":
        return ("rate", "sum", "rate")
    if op == "avg":
        return ("avg", "avg", "latest")
    if op == "sum":
        return ("sum", "sum", "rate")
    return (op, op, "")


def _filter_key(name: str) -> dict[str, Any]:
    """Build a filter/groupBy attribute key in SigNoz's canonical shape."""
    return {
        "dataType": "string",
        "id": f"{name}--string--tag--false",
        "isColumn": False,
        "isJSON": False,
        "key": name,
        "type": "tag",
    }


def _query_spec(panel: dict[str, Any]) -> dict[str, Any]:
    aggregate_attribute = _aggregate_attribute(panel)
    aggregate_op, space_agg, time_agg = _aggregation_modes(panel)
    query_data: dict[str, Any] = {
        "queryName": "A",
        "expression": "A",
        "dataSource": "metrics",
        "aggregateAttribute": aggregate_attribute,
        "aggregateOperator": aggregate_op,
        "spaceAggregation": space_agg,
        "timeAggregation": time_agg,
        "reduceTo": "avg",
        "legend": panel.get("legend", panel["title"]),
        "stepInterval": 60,
        "disabled": False,
        "filters": {"items": [], "op": "AND"},
        "functions": [],
        "groupBy": [_filter_key(key) for key in panel.get("groupBy", [])],
        "having": [],
        "limit": None,
        "orderBy": [],
    }

    return {
        "queryType": "builder",
        "builder": {
            "queryData": [query_data]
        },
    }


def _dashboard_payload(spec: dict[str, Any]) -> dict[str, Any]:
    widgets: list[dict[str, Any]] = []
    for index, panel in enumerate(spec["panels"], start=1):
        widgets.append(
            {
                "id": f"widget-{index}",
                "title": panel["title"],
                "description": panel["description"],
                "panelTypes": panel.get("panelType", "graph"),
                "yAxisUnit": panel.get("unit", ""),
                "query": _query_spec(panel),
            }
        )

    return {
        "collapsable_rows_migrated": True,
        "description": spec["description"],
        "name": spec["name"],
        "title": spec["title"],
        "version": "v4",
        "uploaded_grafana": False,
        "tags": spec.get("tags", []),
        "layout": _widget_layout(len(widgets)),
        "variables": {},
        "widgets": widgets,
        "panel_map": {},
        "source": "pathfinder-observability-pack",
    }


def _render_dashboards(pack: dict[str, Any]) -> list[dict[str, str]]:
    DASHBOARDS_DIR.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, str]] = []

    for dashboard in pack["dashboards"]:
        payload = _dashboard_payload(dashboard)
        filename = f"{dashboard['slug']}.json"
        (DASHBOARDS_DIR / filename).write_text(json.dumps(payload, indent=2) + "\n")
        manifest.append(
            {
                "slug": dashboard["slug"],
                "title": dashboard["title"],
                "file": f"dashboards/{filename}",
                "description": dashboard["description"],
                "recommendedFilters": dashboard.get("recommendedFilters", []),
            }
        )

    (DASHBOARDS_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def _render_filter_guide(pack: dict[str, Any]) -> None:
    lines = [
        "# PathFinder Dashboard Filters",
        "",
        "SigNoz supports dashboard variables and dynamic filters in the UI. This guide names the most useful PathFinder dimensions so dashboards, alerts, and investigations all use the same vocabulary.",
        "",
        "## Filter Glossary",
        "",
    ]

    for item in pack.get("filterGlossary", []):
        applies_to = ", ".join(item.get("appliesTo", []))
        lines.extend(
            [
                f"### `{item['name']}`",
                "",
                item["description"],
                "",
                f"- Applies to: {applies_to}",
                "",
            ]
        )

    lines.extend(["## Dashboard Recommendations", ""])
    for dashboard in pack["dashboards"]:
        lines.append(f"### {dashboard['title']}")
        lines.append("")
        lines.append(dashboard["description"])
        lines.append("")
        if dashboard.get("recommendedFilters"):
            lines.append(
                "- Recommended filters: "
                + ", ".join(f"`{name}`" for name in dashboard["recommendedFilters"])
            )
        else:
            lines.append("- Recommended filters: none")
        lines.append("")

    FILTER_GUIDE_PATH.write_text("\n".join(lines) + "\n")


def _render_alerts(pack: dict[str, Any]) -> None:
    ALERTS_DIR.mkdir(parents=True, exist_ok=True)
    catalog_path = ALERTS_DIR / "pathfinder-alert-catalog.json"
    catalog_path.write_text(json.dumps(pack["alerts"], indent=2) + "\n")

    lines = [
        "# PathFinder Alert Catalog",
        "",
        "This catalog is the reviewed source of truth for alert intent, thresholds, labels, and runbooks.",
        "",
        "Today:",
        "- Use these definitions to create SigNoz alerts in the UI.",
        "- Keep routing/channel details environment-specific.",
        "- Reuse the same metadata across local, staging, production, and Cedar-hosted workflows.",
        "",
    ]

    for index, alert in enumerate(pack["alerts"], start=1):
        lines.extend(
            [
                f"## {index}. {alert['title']}",
                "",
                f"- `slug`: `{alert['slug']}`",
                f"- `severity`: `{alert['severity']}`",
                f"- `signal`: `{alert['signal']}`",
                f"- `metric`: `{alert['metric']}`",
                f"- `operator`: `{alert['aggregateOperator']} {alert['comparison']} {alert['threshold']} {alert['thresholdUnit']}`",
                f"- `for`: `{alert['for']}`",
                f"- `evaluateEvery`: `{alert['evaluateEvery']}`",
                f"- `labels`: `{json.dumps(alert['labels'], sort_keys=True)}`",
                f"- `summary`: {alert['summary']}",
                f"- `description`: {alert['description']}",
                f"- `runbook`: {alert['runbook']}",
                "",
            ]
        )

    (ALERTS_DIR / "pathfinder-alert-catalog.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    pack = _load_pack()
    _render_dashboards(pack)
    _render_filter_guide(pack)
    _render_alerts(pack)


if __name__ == "__main__":
    main()
