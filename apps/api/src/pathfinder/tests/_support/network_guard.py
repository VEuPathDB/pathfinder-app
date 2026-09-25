"""The connection guard each test tier installs: which hosts it refuses, and how."""

from __future__ import annotations

import asyncio.base_events
import socket
from dataclasses import dataclass
from typing import Any, NoReturn
from urllib.parse import urlparse

import pytest
from veupathdb.wdk import get_site_router


class NetworkAccessError(BaseException):
    """A test opened a connection its tier refuses.

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


def _host_text(host: object) -> str:
    """The host as text. The socket API accepts bytes, which must not print raw."""
    if isinstance(host, bytes | bytearray):
        return bytes(host).decode("ascii", "replace")
    return str(host)


def veupathdb_hosts() -> frozenset[str]:
    """The host of every site the router serves."""
    hosts = (
        urlparse(site.base_url).hostname for site in get_site_router().list_sites()
    )
    return frozenset(host for host in hosts if host)


@dataclass(frozen=True)
class _Guard:
    """Refuses every host when ``hosts`` is None, else those hosts and their subdomains."""

    nodeid: str
    advice: str
    hosts: frozenset[str] | None

    def _refuse(self, target: str) -> NoReturn:
        msg = f"{self.nodeid} opened a network connection to {target}. {self.advice}"
        raise NetworkAccessError(msg)

    def _refuses(self, host: str) -> bool:
        if self.hosts is None:
            return True
        name = host.lower().rstrip(".")
        return any(name == h or name.endswith(f".{h}") for h in self.hosts)

    def check_address(self, sock: socket.socket, address: Any) -> None:
        if sock.family not in _IP_FAMILIES:
            return
        # An IPv6 address carries four members and an IPv4 address two, but a
        # shorter one must still be refused rather than raise IndexError here.
        if len(address) < 2:
            if self.hosts is None:
                self._refuse(_host_text(address))
            return
        host = _host_text(address[0])
        if self._refuses(host):
            self._refuse(f"{host}:{address[1]}")

    def check_host(self, host: Any, port: Any) -> None:
        # An absent host means the caller supplied its own socket, which
        # `connect` then guards. An empty host is the same case.
        text = "" if host is None else _host_text(host)
        if text and self._refuses(text):
            self._refuse(f"{text}:{port}")


def _install(monkeypatch: pytest.MonkeyPatch, guard: _Guard) -> None:
    def guarded_connect(sock: socket.socket, address: Any) -> Any:
        guard.check_address(sock, address)
        return _real_connect(sock, address)

    def guarded_connect_ex(sock: socket.socket, address: Any) -> Any:
        guard.check_address(sock, address)
        return _real_connect_ex(sock, address)

    def guarded_getaddrinfo(host: Any, port: Any, *args: Any, **kwargs: Any) -> Any:
        guard.check_host(host, port)
        return _real_getaddrinfo(host, port, *args, **kwargs)

    async def guarded_create_connection(
        loop: Any,
        protocol_factory: Any,
        host: Any = None,
        port: Any = None,
        **kwargs: Any,
    ) -> Any:
        guard.check_host(host, port)
        return await _real_create_connection(
            loop, protocol_factory, host, port, **kwargs
        )

    async def guarded_loop_getaddrinfo(
        loop: Any, host: Any, port: Any, **kwargs: Any
    ) -> Any:
        guard.check_host(host, port)
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


def refuse_every_connection(monkeypatch: pytest.MonkeyPatch, nodeid: str) -> None:
    """Makes every outbound connection attempt raise, naming the test."""
    advice = (
        "Unit tests must not reach the network: a stub that misses its seam is "
        "inert, and the test then passes against a live server. Repoint the stub "
        "at the seam the code calls, or mark the test with @pytest.mark.allow_network."
    )
    _install(monkeypatch, _Guard(nodeid=nodeid, advice=advice, hosts=None))


def refuse_veupathdb(monkeypatch: pytest.MonkeyPatch, nodeid: str) -> None:
    """Makes every connection to a VEuPathDB site raise, naming the test."""
    advice = (
        "This tier runs with no VEuPathDB credential, so a live read passes only "
        "where one is set. Serve the read from a recording, or mark the test "
        "with @pytest.mark.live_wdk when the live read is what it tests."
    )
    _install(monkeypatch, _Guard(nodeid=nodeid, advice=advice, hosts=veupathdb_hosts()))
