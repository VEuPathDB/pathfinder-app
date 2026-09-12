#!/usr/bin/env python3
"""Run a live local observability smoke test against PathFinder.

This script exercises one real chat turn through the local mock stack, waits
for the final SSE event, then verifies that the resulting trace landed in both
Langfuse and SigNoz storage.  It also fetches every imported SigNoz dashboard
and confirms the panel count matches the source pack JSON in
``ops/observability/signoz/dashboards``.

It is intentionally local-dev oriented:
- requires the local Docker Compose observability stack to be running
- uses the development-only `/api/v1/dev/login` endpoint
- queries ClickHouse via `docker compose exec`
- queries the SigNoz HTTP API via the bootstrapped admin user
"""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import parse, request

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_ARGS = [
    "docker",
    "compose",
    "-f",
    "docker-compose.yml",
    "-f",
    "docker-compose.dev.yml",
    "-f",
    "docker-compose.observability.yml",
    "-f",
    "docker-compose.observability.dev.yml",
]
SIGNOZ_DASHBOARDS_DIR = REPO_ROOT / "ops" / "observability" / "signoz" / "dashboards"
DEFAULT_PIPELINE = {
    phase: {"modelId": "mock/deterministic", "reasoningEffort": "low"}
    for phase in ("scoping", "discovery", "planning", "execution", "verification")
}


@dataclass(frozen=True)
class SmokeConfig:
    """Runtime options for the smoke test."""

    api_base_url: str
    site_id: str
    message: str
    user_id: str
    export_wait_seconds: float
    log_since: str
    signoz_base_url: str
    signoz_email: str
    signoz_password: str
    signoz_data_volume: str


def _http_json(
    opener: request.OpenerDirector,
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body = None
    headers = {"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = request.Request(url, data=body, headers=headers, method=method)
    with opener.open(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _collect_sse_events(
    opener: request.OpenerDirector,
    url: str,
) -> list[dict[str, Any]]:
    req = request.Request(url, headers={"Accept": "text/event-stream"}, method="GET")
    events: list[dict[str, Any]] = []
    current_event: str | None = None
    current_data: list[str] = []

    def flush() -> bool:
        nonlocal current_event, current_data
        if current_event is None:
            return False
        payload = "\n".join(current_data).strip()
        data = json.loads(payload) if payload else {}
        event = {"type": current_event, "data": data}
        events.append(event)
        current_event = None
        current_data = []
        return event["type"] == "message_end"

    with opener.open(req, timeout=120) as resp:
        for raw_line in resp:
            line = raw_line.decode("utf-8").rstrip("\n")
            if line == "":
                if flush():
                    break
                continue
            if line.startswith("event: "):
                current_event = line.removeprefix("event: ").strip()
                continue
            if line.startswith("data: "):
                current_data.append(line.removeprefix("data: "))

    return events


def _docker_exec(service: str, *args: str) -> str:
    proc = subprocess.run(
        [*COMPOSE_ARGS, "exec", "-T", service, *args],
        cwd=REPO_ROOT,
        capture_output=True,
        check=True,
        text=True,
    )
    return proc.stdout.strip()


def _clickhouse_json_rows(service: str, query: str) -> list[dict[str, Any]]:
    output = _docker_exec(service, "clickhouse-client", "--query", f"{query} FORMAT JSONEachRow")
    if output == "":
        return []
    return [json.loads(line) for line in output.splitlines() if line.strip()]


def _docker_logs(*services: str, since: str) -> str:
    proc = subprocess.run(
        [*COMPOSE_ARGS, "logs", "--since", since, *services],
        cwd=REPO_ROOT,
        capture_output=True,
        check=True,
        text=True,
    )
    return proc.stdout.strip()


def _filter_relevant_logs(log_text: str, operation_id: str, trace_id: str) -> list[str]:
    selected: list[str] = []
    for line in log_text.splitlines():
        lowered = line.lower()
        if any(term in line for term in (operation_id, trace_id)) or any(
            term in lowered for term in ("error", "warn", "otlp", "langfuse")
        ):
            selected.append(line)
    return selected[-80:]


def _verify_langfuse(trace_id: str) -> dict[str, Any]:
    trace_rows = _clickhouse_json_rows(
        "langfuse-clickhouse",
        (
            "SELECT id, name, user_id, session_id, input, output, timestamp "
            "FROM default.traces "
            f"WHERE id = '{trace_id}' "
            "ORDER BY timestamp ASC LIMIT 20"
        ),
    )
    observation_rows = _clickhouse_json_rows(
        "langfuse-clickhouse",
        (
            "SELECT name, type, level, provided_model_name, prompt_name, prompt_version, status_message "
            "FROM default.observations "
            f"WHERE trace_id = '{trace_id}' "
            "ORDER BY start_time ASC LIMIT 50"
        ),
    )
    best_trace = None
    if trace_rows:
        best_trace = max(
            trace_rows,
            key=lambda row: sum(
                1
                for field in ("name", "input", "output", "user_id", "session_id")
                if row.get(field) not in (None, "")
            ),
        )
    return {"trace": best_trace, "traceRows": trace_rows, "observations": observation_rows}


def _verify_signoz(trace_id: str, start_ms: int) -> dict[str, Any]:
    trace_rows = _clickhouse_json_rows(
        "signoz-clickhouse",
        (
            "SELECT trace_id, name, serviceName, statusCodeString, "
            "attributes_string['app.operation_id'] AS operation_id, "
            "attributes_string['app.intent'] AS intent "
            "FROM signoz_traces.distributed_signoz_index_v3 "
            f"WHERE trace_id = '{trace_id}' "
            "ORDER BY timestamp ASC LIMIT 100"
        ),
    )
    # ``distributed_time_series_v4_1day`` buckets ``unix_milli`` to the start
    # of each day, so a ``unix_milli >= smoke_start_ms`` filter against it
    # never matches within-day samples.  Query raw samples instead.
    metric_rows = _clickhouse_json_rows(
        "signoz-clickhouse",
        (
            "SELECT metric_name, count() AS samples "
            "FROM signoz_metrics.distributed_samples_v4 "
            f"WHERE unix_milli >= {start_ms} "
            "AND (metric_name LIKE 'assistant.%' "
            "OR metric_name LIKE 'veupathdb.%') "
            "GROUP BY metric_name ORDER BY metric_name"
        ),
    )
    return {"traces": trace_rows, "metrics": metric_rows}


def _signoz_org_id(volume_name: str) -> str:
    """Read the SigNoz admin org ID from the signoz_data sqlite store.

    SigNoz v0.118 requires an explicit ``orgID`` at login.  The value is only
    accessible via authenticated API calls or the internal sqlite store, so
    spin up a one-shot Python container with the volume mounted read-only.
    """
    proc = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{volume_name}:/sdata:ro",
            "python:3.14-slim",
            "python",
            "-c",
            (
                "import sqlite3; "
                "print(sqlite3.connect('/sdata/signoz.db')"
                ".execute('SELECT id FROM organizations LIMIT 1').fetchone()[0])"
            ),
        ],
        capture_output=True,
        check=True,
        text=True,
    )
    return proc.stdout.strip()


def _signoz_login(config: SmokeConfig, org_id: str) -> str:
    """Authenticate against SigNoz and return a bearer access token."""
    payload = json.dumps(
        {
            "email": config.signoz_email,
            "password": config.signoz_password,
            "orgID": org_id,
        }
    ).encode("utf-8")
    req = request.Request(
        f"{config.signoz_base_url}/api/v2/sessions/email_password",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    token = body.get("data", {}).get("accessToken")
    if not token:
        raise RuntimeError(f"SigNoz login did not return accessToken: {body}")
    return str(token)


def _signoz_get(config: SmokeConfig, token: str, path: str) -> dict[str, Any]:
    req = request.Request(
        f"{config.signoz_base_url}{path}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        method="GET",
    )
    with request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _expected_dashboard_specs() -> list[dict[str, Any]]:
    """Load the source dashboard pack JSONs that the bootstrap should import."""
    specs: list[dict[str, Any]] = []
    for path in sorted(SIGNOZ_DASHBOARDS_DIR.glob("*.json")):
        if path.name == "manifest.json":
            continue
        spec = json.loads(path.read_text())
        specs.append(
            {
                "file": path.name,
                "title": spec.get("title") or path.stem,
                "expectedWidgetCount": len(spec.get("widgets") or []),
                "tags": list(spec.get("tags") or []),
            }
        )
    return specs


def _verify_signoz_dashboards(config: SmokeConfig) -> dict[str, Any]:
    """Confirm every source dashboard is present in SigNoz with matching panels."""
    expected = _expected_dashboard_specs()
    if not expected:
        return {"status": "skip", "reason": "no source dashboards on disk"}

    org_id = _signoz_org_id(config.signoz_data_volume)
    token = _signoz_login(config, org_id)

    listing = _signoz_get(config, token, "/api/v1/dashboards")
    by_title: dict[str, dict[str, Any]] = {}
    for entry in listing.get("data", []) or []:
        data = entry.get("data") or {}
        title = data.get("title") or entry.get("title")
        if isinstance(title, str):
            by_title[title] = entry

    results: list[dict[str, Any]] = []
    all_ok = True
    for spec in expected:
        title = spec["title"]
        live = by_title.get(title)
        if live is None:
            all_ok = False
            results.append(
                {
                    "file": spec["file"],
                    "title": title,
                    "present": False,
                    "expectedWidgetCount": spec["expectedWidgetCount"],
                    "actualWidgetCount": None,
                    "panelMatch": False,
                    "id": None,
                }
            )
            continue
        dashboard_id = live.get("id") or (live.get("data") or {}).get("id")
        detail = _signoz_get(config, token, f"/api/v1/dashboards/{dashboard_id}")
        detail_data = (detail.get("data") or {}).get("data") or {}
        actual_widgets = detail_data.get("widgets") or []
        match = len(actual_widgets) == spec["expectedWidgetCount"]
        if not match:
            all_ok = False
        results.append(
            {
                "file": spec["file"],
                "title": title,
                "present": True,
                "expectedWidgetCount": spec["expectedWidgetCount"],
                "actualWidgetCount": len(actual_widgets),
                "panelMatch": match,
                "id": dashboard_id,
            }
        )

    return {
        "status": "ok" if all_ok else "mismatch",
        "orgId": org_id,
        "expectedCount": len(expected),
        "presentCount": sum(1 for r in results if r["present"]),
        "panelMatchCount": sum(1 for r in results if r["panelMatch"]),
        "dashboards": results,
    }


def _wait_for_telemetry(trace_id: str, start_ms: int, wait_seconds: float) -> tuple[dict[str, Any], dict[str, Any]]:
    deadline = time.time() + wait_seconds
    latest_langfuse: dict[str, Any] = {"trace": None, "observations": []}
    latest_signoz: dict[str, Any] = {"traces": [], "metrics": []}
    while time.time() < deadline:
        latest_langfuse = _verify_langfuse(trace_id)
        latest_signoz = _verify_signoz(trace_id, start_ms)
        if (
            latest_langfuse["trace"] is not None
            and len(latest_signoz["traces"]) > 0
            and len(latest_signoz["metrics"]) > 0
        ):
            return latest_langfuse, latest_signoz
        time.sleep(2)
    return latest_langfuse, latest_signoz


def run_smoke_test(config: SmokeConfig) -> dict[str, Any]:
    cookie_jar = http.cookiejar.CookieJar()
    opener = request.build_opener(request.HTTPCookieProcessor(cookie_jar))

    start_ms = int(time.time() * 1000) - 2_000
    login = _http_json(
        opener,
        "POST",
        f"{config.api_base_url}/api/v1/dev/login?{parse.urlencode({'user_id': config.user_id})}",
    )
    chat = _http_json(
        opener,
        "POST",
        f"{config.api_base_url}/api/v1/chat",
        {
            "siteId": config.site_id,
            "message": config.message,
            "pipeline": DEFAULT_PIPELINE,
        },
    )
    operation_id = str(chat["operationId"])
    sse_events = _collect_sse_events(
        opener,
        f"{config.api_base_url}/api/v1/operations/{operation_id}/subscribe",
    )
    message_end = next(
        (event for event in reversed(sse_events) if event["type"] == "message_end"),
        None,
    )
    if message_end is None:
        raise RuntimeError("Smoke test did not receive a message_end event.")
    trace_id = message_end["data"].get("traceId")
    if not trace_id:
        raise RuntimeError("message_end did not include a traceId.")

    langfuse, signoz = _wait_for_telemetry(
        str(trace_id),
        start_ms,
        config.export_wait_seconds,
    )
    logs = _docker_logs(
        "api",
        "signoz",
        "signoz-otel-collector",
        "langfuse",
        "langfuse-worker",
        since=config.log_since,
    )

    dashboards = _verify_signoz_dashboards(config)

    return {
        "login": login,
        "chat": chat,
        "operationId": operation_id,
        "traceId": trace_id,
        "eventTypes": [event["type"] for event in sse_events],
        "messageEnd": message_end["data"],
        "langfuse": langfuse,
        "signoz": signoz,
        "signozDashboards": dashboards,
        "logExcerpt": _filter_relevant_logs(logs, operation_id, str(trace_id)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base-url", default="http://localhost:8000")
    parser.add_argument("--site-id", default="veupathdb")
    parser.add_argument(
        "--message",
        default="What can you help me do in PathFinder?",
    )
    parser.add_argument("--user-id", default="observability-smoke")
    parser.add_argument("--export-wait-seconds", type=float, default=45.0)
    parser.add_argument("--log-since", default="5m")
    parser.add_argument("--signoz-base-url", default="http://localhost:3301")
    parser.add_argument(
        "--signoz-email",
        default=os.environ.get("SIGNOZ_ROOT_USER_EMAIL", "dev@pathfinder.local"),
    )
    parser.add_argument(
        "--signoz-password",
        default=os.environ.get("SIGNOZ_ROOT_USER_PASSWORD", "PathfinderLocal1!"),
    )
    parser.add_argument(
        "--signoz-data-volume",
        default=f"{REPO_ROOT.name}_signoz_data",
        help="Docker volume that holds /var/lib/signoz/signoz.db (compose project + named volume).",
    )
    args = parser.parse_args()

    summary = run_smoke_test(
        SmokeConfig(
            api_base_url=args.api_base_url,
            site_id=args.site_id,
            message=args.message,
            user_id=args.user_id,
            export_wait_seconds=args.export_wait_seconds,
            log_since=args.log_since,
            signoz_base_url=args.signoz_base_url,
            signoz_email=args.signoz_email,
            signoz_password=args.signoz_password,
            signoz_data_volume=args.signoz_data_volume,
        )
    )
    json.dump(summary, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
