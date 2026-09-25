"""The integration tier refuses VEuPathDB to a test that is not ``live_wdk``."""

import asyncio
import socket

import pytest

from pathfinder.tests._support.network_guard import NetworkAccessError


def test_a_site_lookup_is_refused() -> None:
    with pytest.raises(NetworkAccessError) as excinfo:
        socket.getaddrinfo("plasmodb.org", 443)
    assert "plasmodb.org:443" in str(excinfo.value)
    assert "test_a_site_lookup_is_refused" in str(excinfo.value)


def test_every_site_and_its_subdomains_are_refused() -> None:
    for host in ("toxodb.org", "veupathdb.org", "auth.veupathdb.org"):
        with pytest.raises(NetworkAccessError):
            socket.getaddrinfo(host, 443)


async def test_an_event_loop_connection_to_a_site_is_refused() -> None:
    loop = asyncio.get_running_loop()
    with pytest.raises(NetworkAccessError):
        await loop.getaddrinfo("plasmodb.org", 443)
    with pytest.raises(NetworkAccessError):
        await loop.create_connection(asyncio.Protocol, "plasmodb.org", 443)


def test_a_socket_connect_to_a_site_is_refused() -> None:
    with socket.socket() as sock, pytest.raises(NetworkAccessError):
        sock.connect(("plasmodb.org", 443))


def test_a_host_that_is_no_site_stays_open() -> None:
    """The tier's own database and servers are reached by address."""
    with (
        socket.create_server(("127.0.0.1", 0)) as server,
        socket.create_connection(server.getsockname()) as conn,
    ):
        assert conn.getpeername() == server.getsockname()


@pytest.mark.live_wdk
def test_the_live_marker_keeps_the_real_resolver() -> None:
    assert socket.getaddrinfo.__module__ == "socket"
