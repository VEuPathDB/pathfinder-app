"""Shared fixtures for unit tests."""

import asyncio.base_events
import socket
from collections.abc import AsyncGenerator
from typing import Any, NoReturn
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from veupathdb.domain.strategy.ast import StrategyStepNode
from veupathdb.domain.strategy.graph_model import flatten_tree

from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.persistence.models import User
from pathfinder.persistence.repositories import ConversationRepository

# Network guard.


class UnitTestNetworkAccessError(BaseException):
    """A unit test tried to open a network connection.

    This derives from ``BaseException``, not ``Exception``: every HTTP client in
    the tree retries under ``except Exception``, and a refusal that a retry loop
    can swallow would restore the hazard the guard exists to close.
    """


_real_connect = socket.socket.connect
_real_connect_ex = socket.socket.connect_ex
_real_getaddrinfo = socket.getaddrinfo
_real_create_connection = asyncio.base_events.BaseEventLoop.create_connection
_real_loop_getaddrinfo = asyncio.base_events.BaseEventLoop.getaddrinfo

_IP_FAMILIES = frozenset({socket.AF_INET, socket.AF_INET6})


def _refuse(nodeid: str, target: str) -> NoReturn:
    msg = (
        f"{nodeid} opened a network connection to {target}. Unit tests must "
        "not reach the network: a stub that misses its seam is inert, and the "
        "test then passes against a live server. Repoint the stub at the seam "
        "the code calls, or mark the test with @pytest.mark.allow_network."
    )
    raise UnitTestNetworkAccessError(msg)


def _host_text(host: object) -> str:
    """The host as text. The socket API accepts bytes, which must not print raw."""
    if isinstance(host, bytes | bytearray):
        return bytes(host).decode("ascii", "replace")
    return str(host)


def _check_address(nodeid: str, sock: socket.socket, address: Any) -> None:
    if sock.family not in _IP_FAMILIES:
        return
    # An IPv6 address carries four members and an IPv4 address two, but a
    # shorter one must still be refused rather than raise IndexError here.
    if len(address) < 2:
        _refuse(nodeid, _host_text(address))
    _refuse(nodeid, f"{_host_text(address[0])}:{address[1]}")


def _check_host(nodeid: str, host: Any, port: Any) -> None:
    # An absent host means the caller supplied its own socket, which
    # `connect` then guards. An empty host is the same case.
    text = "" if host is None else _host_text(host)
    if text:
        _refuse(nodeid, f"{text}:{port}")


def _install_network_guard(monkeypatch: pytest.MonkeyPatch, nodeid: str) -> None:
    """Makes every outbound connection attempt raise, naming the test."""

    def guarded_connect(sock: socket.socket, address: Any) -> Any:
        _check_address(nodeid, sock, address)
        return _real_connect(sock, address)

    def guarded_connect_ex(sock: socket.socket, address: Any) -> Any:
        _check_address(nodeid, sock, address)
        return _real_connect_ex(sock, address)

    def guarded_getaddrinfo(host: Any, port: Any, *args: Any, **kwargs: Any) -> Any:
        _check_host(nodeid, host, port)
        return _real_getaddrinfo(host, port, *args, **kwargs)

    async def guarded_create_connection(
        loop: Any,
        protocol_factory: Any,
        host: Any = None,
        port: Any = None,
        **kwargs: Any,
    ) -> Any:
        _check_host(nodeid, host, port)
        return await _real_create_connection(
            loop, protocol_factory, host, port, **kwargs
        )

    async def guarded_loop_getaddrinfo(
        loop: Any, host: Any, port: Any, **kwargs: Any
    ) -> Any:
        _check_host(nodeid, host, port)
        return await _real_loop_getaddrinfo(loop, host, port, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)
    monkeypatch.setattr(socket, "getaddrinfo", guarded_getaddrinfo)
    monkeypatch.setattr(
        asyncio.base_events.BaseEventLoop,
        "create_connection",
        guarded_create_connection,
    )
    monkeypatch.setattr(
        asyncio.base_events.BaseEventLoop, "getaddrinfo", guarded_loop_getaddrinfo
    )


@pytest.fixture(autouse=True)
def _no_network(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Refuses network connections for the duration of a unit test.

    A test that needs a real connection carries the `allow_network` marker.
    """
    if request.node.get_closest_marker("allow_network") is None:
        _install_network_guard(monkeypatch, request.node.nodeid)


@pytest.fixture
async def db_session(
    session_maker: async_sessionmaker[AsyncSession],
    db_cleaner: None,
) -> AsyncGenerator[AsyncSession]:
    async with session_maker() as session:
        yield session


@pytest.fixture
async def conv_repo(
    db_session: AsyncSession,
) -> ConversationRepository:
    return ConversationRepository(db_session)


@pytest.fixture
async def user_id(db_session: AsyncSession) -> UUID:
    """Create a User row and return its id."""
    uid = uuid4()
    db_session.add(User(id=uid))
    await db_session.flush()
    return uid


def populate_graph(graph: StrategyGraph, *steps: StrategyStepNode) -> None:
    """Add steps to graph bypassing single-root invariant for test setup."""
    for step in steps:
        graph.steps.update(flatten_tree(step))
    graph.recompute_roots()
