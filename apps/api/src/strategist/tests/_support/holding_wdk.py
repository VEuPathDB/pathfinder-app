from __future__ import annotations

import copy
import json
import re
import sys
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.domain.strategy import StrategyStep
from veupathdb.wdk import (
    StrategyAPI,
    VEuPathDBClient,
    WDKSearch,
    WDKSearchResponse,
    WDKStepTree,
)

from strategist.services.strategies.sync_state import WDKSyncState
from strategist.tests._support.held_steps import (
    BOOLEAN_SEARCH,
    SPAN_SEARCH,
    held_config,
    held_step,
    tree_of,
)

_INPUT_PARAMS = {
    BOOLEAN_SEARCH: ("bq_left_op_", "bq_right_op_"),
    SPAN_SEARCH: ("span_a", "span_b"),
}
_SEARCH_PARAMS = {BOOLEAN_SEARCH: ("bq_left_op_", "bq_right_op_", "bq_operator")}
USER = "1"
TOKEN = "a-registered-token"
_STEP = re.compile(r"/users/\w+/steps/(\d+)")
_STEP_CONFIG = re.compile(r"/users/\w+/steps/(\d+)/search-config")
_STRATEGY = re.compile(r"/users/\w+/strategies/(\d+)")
_STRATEGY_TREE = re.compile(r"/users/\w+/strategies/(\d+)/step-tree")
_SEARCH = re.compile(r"/record-types/(\w+)/searches/(\w+)")
_STEP_REPORT = re.compile(r"/users/\w+/steps/(\d+)/reports/standard")
_SEARCH_REPORT = re.compile(r"/record-types/\w+/searches/\w+/reports/standard")
_REFRESH = re.compile(r"/record-types/\w+/searches/\w+/refreshed-dependent-params")


@dataclass
class Write:
    method: str
    path: str
    body: Any


@dataclass
class HoldingWDK(httpx.AsyncBaseTransport):
    steps: dict[int, dict[str, Any]] = field(default_factory=dict)
    strategies: dict[int, dict[str, Any]] = field(default_factory=dict)
    writes: list[Write] = field(default_factory=list)
    drops_the_weight_on_create: bool = False
    refuses_patches: bool = False
    keeps_its_own_tree: bool = False
    refuses_once: set[str] = field(default_factory=set)
    garbles_once: set[str] = field(default_factory=set)
    answers_before_refusing: dict[str, int] = field(default_factory=dict)
    answer_size: int | None = 100
    sizes: dict[int, int | None] = field(default_factory=dict)
    next_id: int = 5000
    next_dataset_id: int = 7000
    sent: Counter[str] = field(default_factory=Counter)

    def written(self, method: str, suffix: str = "") -> list[Write]:
        return [
            w for w in self.writes if w.method == method and w.path.endswith(suffix)
        ]

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/service")
        body = json.loads(request.content) if request.content else None
        self.sent[request_kind(request.method, path)] += 1
        if request.method != "GET":
            self.writes.append(Write(request.method, path, copy.deepcopy(body)))
        refused = self._refusal(request.method, path)
        if refused is not None:
            return refused
        answer = self._answer(request.method, path, body)
        if answer is None:
            return httpx.Response(204)
        return httpx.Response(200, json=answer)

    def _refusal(self, method: str, path: str) -> httpx.Response | None:
        if method == "PATCH" and self.refuses_patches:
            return httpx.Response(422, json={"message": "refused"})
        absent = (
            method == "GET"
            and (m := _STEP.fullmatch(path)) is not None
            and int(m[1]) not in self.steps
        ) or (
            (m := _STRATEGY.match(path)) is not None
            and int(m[1]) not in self.strategies
        )
        if absent:
            return httpx.Response(404, json={"message": "not held"})
        return self._scripted(_kind_of(method, path))

    def _scripted(self, kind: str) -> httpx.Response | None:
        left = self.answers_before_refusing.get(kind)
        if left is not None:
            self.answers_before_refusing[kind] = left - 1
            if left <= 0:
                return httpx.Response(503, json={"message": f"{kind} not answered"})
        if kind in self.refuses_once:
            self.refuses_once.discard(kind)
            return httpx.Response(422, json={"message": f"{kind} refused"})
        if kind in self.garbles_once:
            self.garbles_once.discard(kind)
            return httpx.Response(200, json={"strategyId": "not a strategy"})
        return None

    def _answer(self, method: str, path: str, body: Any) -> Any:
        match method:
            case "GET":
                return self._get(path)
            case "POST":
                return self._post(path, body)
            case "PUT":
                return self._put(path, body)
            case "PATCH":
                return self._patch(path, body)
            case _:
                return self._delete(path)

    def _alloc(self) -> int:
        self.next_id += 1
        return self.next_id

    def _get(self, path: str) -> Any:
        if path.startswith("/app"):
            return {}
        if path.endswith("/searches") and path.startswith("/record-types/"):
            return [{"urlSegment": name} for name in (BOOLEAN_SEARCH, SPAN_SEARCH)]
        if m := _SEARCH.fullmatch(path):
            return _search_details(m[2])
        if m := _STEP.fullmatch(path):
            return self._step_json(int(m[1]))
        if m := _STRATEGY.fullmatch(path):
            return self._strategy_json(int(m[1]))
        msg = f"HoldingWDK: no GET {path}"
        raise AssertionError(msg)

    def _read(self, path: str) -> Any:
        if m := _STEP_REPORT.fullmatch(path):
            return _answer_of(self.sizes.get(int(m[1]), self.answer_size))
        if _SEARCH_REPORT.fullmatch(path):
            return _answer_of(self.answer_size)
        if _REFRESH.fullmatch(path):
            return []
        if m := _SEARCH.fullmatch(path):
            return _search_details(m[2])
        return None

    def _post(self, path: str, body: Any) -> Any:
        read = self._read(path)
        if read is not None:
            return read
        if path.endswith("/datasets"):
            self.next_dataset_id += 1
            return {"id": self.next_dataset_id}
        if path.endswith("/steps"):
            return {"id": self._create_step(body)}
        if path.endswith("/strategies"):
            sid = self._alloc()
            self.strategies[sid] = {
                "name": body["name"],
                "isSaved": bool(body.get("isSaved")),
                "description": body.get("description", ""),
                "stepTree": copy.deepcopy(body["stepTree"]),
            }
            self._wire_inputs(body["stepTree"])
            return {"id": sid}
        msg = f"HoldingWDK: no POST {path}"
        raise AssertionError(msg)

    def _create_step(self, body: dict[str, Any]) -> int:
        sid = self._alloc()
        config = dict(body.get("searchConfig") or {})
        self.steps[sid] = {
            "id": sid,
            "searchName": body["searchName"],
            "searchConfig": held_config(body["searchName"], config),
            "customName": body.get("customName"),
            "expanded": False,
            "expandedName": None,
            "displayPreferences": {},
        }
        if self.drops_the_weight_on_create:
            self.steps[sid]["searchConfig"]["wdkWeight"] = 0
        return sid

    def _put(self, path: str, body: Any) -> Any:
        if m := _STEP_CONFIG.fullmatch(path):
            step = self._held(int(m[1]))
            step["searchConfig"] = held_config(step["searchName"], body)
            return None
        if m := _STRATEGY_TREE.fullmatch(path):
            if self.keeps_its_own_tree:
                return None
            self.strategies[int(m[1])]["stepTree"] = copy.deepcopy(body["stepTree"])
            self._wire_inputs(body["stepTree"])
            return None
        msg = f"HoldingWDK: no PUT {path}"
        raise AssertionError(msg)

    def _patch(self, path: str, body: Any) -> Any:
        if m := _STEP.fullmatch(path):
            step = self._held(int(m[1]))
            for key in ("customName", "expanded", "expandedName", "displayPreferences"):
                if key in body:
                    step[key] = copy.deepcopy(body[key])
            return None
        if m := _STRATEGY.fullmatch(path):
            strategy = self.strategies[int(m[1])]
            for key in ("name", "description", "isSaved"):
                if key in body:
                    strategy[key] = body[key]
            return None
        msg = f"HoldingWDK: no PATCH {path}"
        raise AssertionError(msg)

    def _delete(self, path: str) -> Any:
        if m := _STEP.fullmatch(path):
            self.steps.pop(int(m[1]), None)
            return None
        if m := _STRATEGY.fullmatch(path):
            self.strategies.pop(int(m[1]), None)
            return None
        msg = f"HoldingWDK: no DELETE {path}"
        raise AssertionError(msg)

    def holds(
        self,
        steps: Mapping[str, StrategyStep],
        sync_state: WDKSyncState,
        *,
        root_id: str | None = None,
        name: str = "Test",
        description: str = "",
    ) -> None:
        for step_id, wdk_id in sync_state.wdk_step_ids.items():
            step = steps.get(step_id)
            if step is not None:
                self.steps[wdk_id] = held_step(wdk_id, step)
        self.next_id = max([self.next_id, *self.steps])
        strategy_id = sync_state.wdk_strategy_id
        if strategy_id is None or root_id is None:
            return
        tree = tree_of(root_id, steps, sync_state.wdk_step_ids)
        if tree is None:
            return
        sync_state.wdk_step_tree = WDKStepTree.model_validate(tree)
        self.strategies[strategy_id] = {
            "name": name,
            "isSaved": False,
            "description": description,
            "stepTree": tree,
        }
        self._wire_inputs(tree)

    def holds_the_strategy(self, details: dict[str, Any]) -> None:
        for key, step in details["steps"].items():
            self.steps[int(key)] = {
                "id": int(key),
                "searchName": step["searchName"],
                "searchConfig": {
                    "parameters": dict(step["searchConfig"].get("parameters", {})),
                    "filters": list(step["searchConfig"].get("filters", [])),
                    "wdkWeight": step["searchConfig"].get("wdkWeight", 0),
                },
                "customName": step.get("customName"),
                "expanded": step.get("expanded", False),
                "expandedName": step.get("expandedName"),
                "displayPreferences": {},
            }
            if step.get("estimatedSize") is not None:
                self.sizes[int(key)] = step["estimatedSize"]
        self.strategies[details["strategyId"]] = {
            "name": details.get("name", ""),
            "isSaved": details.get("isSaved", False),
            "description": details.get("description", ""),
            "stepTree": copy.deepcopy(details["stepTree"]),
        }
        self.next_id = max([self.next_id, *self.steps])

    def _held(self, step_id: int) -> dict[str, Any]:
        return self.steps[step_id]

    def _wire_inputs(self, tree: dict[str, Any]) -> None:
        step = self._held(tree["stepId"])
        names = _INPUT_PARAMS.get(step["searchName"])
        inputs = [tree.get("primaryInput"), tree.get("secondaryInput")]
        if names is not None:
            for name, sub in zip(names, inputs, strict=True):
                if sub is not None:
                    step["searchConfig"]["parameters"][name] = str(sub["stepId"])
        for sub in inputs:
            if sub is not None:
                self._wire_inputs(sub)

    def strategy_of(self, step_id: int) -> int | None:
        for strategy_id, strategy in self.strategies.items():
            if step_id in tree_ids(strategy["stepTree"]):
                return strategy_id
        return None

    def _step_json(self, step_id: int) -> dict[str, Any]:
        step = copy.deepcopy(self._held(step_id))
        step.update(
            {
                "recordClassName": "transcript",
                "estimatedSize": self.sizes.get(step_id, self.answer_size),
                "validation": {"level": "RUNNABLE", "isValid": True},
                "displayName": step["customName"] or step["searchName"],
                "strategyId": self.strategy_of(step_id),
            }
        )
        return step

    def _strategy_json(self, strategy_id: int) -> dict[str, Any]:
        strategy = self.strategies[strategy_id]
        tree = strategy["stepTree"]
        return {
            "strategyId": strategy_id,
            "name": strategy["name"],
            "description": strategy["description"],
            "isSaved": strategy["isSaved"],
            "recordClassName": "transcript",
            "rootStepId": tree["stepId"],
            "stepTree": copy.deepcopy(tree),
            "steps": {
                str(i): self._step_json(i) for i in tree_ids(tree) if i in self.steps
            },
        }


def _kind_of(method: str, path: str) -> str:
    if method == "GET" and _STEP.fullmatch(path):
        return "step read"
    if method == "GET" and _STRATEGY.fullmatch(path):
        return "strategy read"
    if method == "PUT" and _STEP_CONFIG.fullmatch(path):
        return "search-config put"
    if method == "PUT" and _STRATEGY_TREE.fullmatch(path):
        return "strategy tree put"
    if method == "POST" and path.endswith("/steps"):
        return "step create"
    return ""


def request_kind(method: str, path: str) -> str:
    return f"{method} {re.sub(r'/\d+', '/N', path)}"


def _answer_of(size: int | None) -> dict[str, Any]:
    return {"meta": {"totalCount": size, "responseCount": 0}, "records": []}


def tree_ids(tree: dict[str, Any] | None) -> list[int]:
    if tree is None:
        return []
    return [
        tree["stepId"],
        *tree_ids(tree.get("primaryInput")),
        *tree_ids(tree.get("secondaryInput")),
    ]


def _search_details(search_name: str) -> dict[str, Any]:
    inputs = _INPUT_PARAMS.get(search_name, ())
    names = _SEARCH_PARAMS.get(search_name, inputs)
    return {
        "searchData": {
            "urlSegment": search_name,
            "paramNames": list(names),
            "parameters": [
                {
                    "name": name,
                    "type": "input-step" if name in inputs else "string",
                    "displayName": name,
                }
                for name in names
            ],
        },
        "validation": {"level": "NONE", "isValid": False},
    }


def held_definition(search_name: str) -> WDKSearch:
    return WDKSearchResponse.model_validate(_search_details(search_name)).search_data


def holding_strategy_api(wdk: HoldingWDK) -> StrategyAPI:
    client = VEuPathDBClient(
        base_url="https://plasmodb.invalid/service",
        site_id="plasmodb",
        transport=wdk,
    )
    return StrategyAPI(client, user_id=USER)


def serve_the_holding_wdk(monkeypatch: pytest.MonkeyPatch, wdk: HoldingWDK) -> None:
    api = holding_strategy_api(wdk)
    veupathdb_auth_token_ctx.set(TOKEN)

    def _api(_site_id: str) -> StrategyAPI:
        return api

    for name, module in list(sys.modules.items()):
        if name.startswith("strategist.") and "get_strategy_api" in vars(module):
            monkeypatch.setattr(module, "get_strategy_api", _api)
