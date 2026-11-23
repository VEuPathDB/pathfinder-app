from __future__ import annotations

import asyncio
import selectors
from collections.abc import Awaitable, Callable
from dataclasses import dataclass


@dataclass
class _Clock:
    seconds: float = 0.0


class _SkippingSelector(selectors.DefaultSelector):
    def __init__(self, clock: _Clock) -> None:
        super().__init__()
        self._clock = clock

    def select(
        self, timeout: float | None = None
    ) -> list[tuple[selectors.SelectorKey, int]]:
        ready = super().select(0)
        if ready or timeout == 0:
            return ready
        if timeout is None:
            return super().select()
        self._clock.seconds += timeout
        return []


class _VirtualTimeLoop(asyncio.SelectorEventLoop):
    def __init__(self) -> None:
        self._clock = _Clock()
        super().__init__(_SkippingSelector(self._clock))

    def time(self) -> float:
        return self._clock.seconds


def run_in_virtual_time[T](main: Callable[[], Awaitable[T]]) -> tuple[T, float]:
    with asyncio.Runner(loop_factory=_VirtualTimeLoop) as runner:
        result = runner.run(_awaited(main))
        return result, runner.get_loop().time()


async def _awaited[T](main: Callable[[], Awaitable[T]]) -> T:
    return await main()
