from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager, suppress

import httpx
from veupathdb.wdk import (
    StrategyAPI,
    StrategyRequest,
    VEuPathDBClient,
    WDKStepTree,
    strategy_gate,
    use_strategy_gate,
    walk_wdk_step_tree,
)

STRATEGY = 214644620
TEXT, GO, INNER, SIGNAL, OUTER = 227283340, 227283350, 227283440, 227283370, 227283450
BEFORE_THE_DELETE = WDKStepTree(
    step_id=OUTER,
    primary_input=WDKStepTree(
        step_id=INNER,
        primary_input=WDKStepTree(step_id=TEXT),
        secondary_input=WDKStepTree(step_id=GO),
    ),
    secondary_input=WDKStepTree(step_id=SIGNAL),
)
AFTER_THE_DELETE = WDKStepTree(
    step_id=INNER,
    primary_input=WDKStepTree(step_id=TEXT),
    secondary_input=WDKStepTree(step_id=GO),
)
_PUT_WAITS_SECONDS = 0.5
_STRATEGY_READ = re.compile(r"/strategies/(\d+)$")


class ReadSavesBack(httpx.AsyncBaseTransport):
    def __init__(self, *, put_waits_for_a_reader: bool = True) -> None:
        self.held = BEFORE_THE_DELETE
        self.put_waits_for_a_reader = put_waits_for_a_reader
        self.reverted = False
        self.put_started = asyncio.Event()
        self.reader_loaded = asyncio.Event()
        self.put_landed = asyncio.Event()
        self.release_the_put = asyncio.Event()
        self.release_the_put.set()
        self.reads: list[int] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.startswith("/app"):
            return httpx.Response(200, text="ok")
        if request.method == "PUT" and path.endswith("/step-tree"):
            return await self._put(request)
        read = _STRATEGY_READ.search(path)
        if request.method == "GET" and read is not None:
            return await self._read(int(read.group(1)))
        return httpx.Response(204)

    async def _put(self, request: httpx.Request) -> httpx.Response:
        self.put_started.set()
        await self.release_the_put.wait()
        if self.put_waits_for_a_reader:
            with suppress(TimeoutError):
                await asyncio.wait_for(self.reader_loaded.wait(), _PUT_WAITS_SECONDS)
        if not self.reverted:
            written = json.loads(request.content)["stepTree"]
            self.held = WDKStepTree.model_validate(written)
        self.put_landed.set()
        return httpx.Response(204)

    async def _read(self, strategy_id: int) -> httpx.Response:
        loaded = self.held
        self.reads.append(loaded.step_id)
        self.reader_loaded.set()
        if self.put_started.is_set():
            await self.put_landed.wait()
        self.held = loaded
        return httpx.Response(200, json=_details(loaded, strategy_id))


def _details(tree: WDKStepTree, strategy_id: int) -> dict[str, object]:
    return {
        "strategyId": strategy_id,
        "name": "Signal peptide kinases",
        "rootStepId": tree.step_id,
        "recordClassName": "transcript",
        "stepTree": tree.model_dump(by_alias=True, exclude_none=True),
        "steps": {
            str(node.step_id): {
                "id": node.step_id,
                "searchName": "GenesByText",
                "searchConfig": {"parameters": {}},
                "recordClassName": "transcript",
                "estimatedSize": 48,
            }
            for node in walk_wdk_step_tree(tree)
        },
    }


async def strategy_api_on(site: ReadSavesBack) -> StrategyAPI:
    client = VEuPathDBClient(
        base_url="https://plasmodb.invalid/service", site_id="plasmodb"
    )
    async with client._client_lock:
        client._client = httpx.AsyncClient(
            base_url=client.base_url, transport=site, follow_redirects=True
        )
    return StrategyAPI(client, user_id="1")


@contextmanager
def one_request_per_strategy() -> Iterator[None]:
    previous = strategy_gate()
    locks: dict[StrategyRequest, asyncio.Lock] = {}

    @asynccontextmanager
    async def line(request: StrategyRequest) -> AsyncIterator[None]:
        async with locks.setdefault(request, asyncio.Lock()):
            yield

    use_strategy_gate(line)
    try:
        yield
    finally:
        use_strategy_gate(previous)
