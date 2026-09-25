"""The unit tier refuses network connections unless a test opts in."""

import asyncio
import contextlib
import socket
import tempfile
from pathlib import Path

import pytest

from pathfinder.tests._support.network_guard import NetworkAccessError


def test_an_outbound_connection_is_refused() -> None:
    with socket.socket() as sock, pytest.raises(NetworkAccessError) as excinfo:
        sock.connect(("plasmodb.org", 443))
    assert "plasmodb.org:443" in str(excinfo.value)


def test_the_refusal_names_the_test() -> None:
    with socket.socket() as sock, pytest.raises(NetworkAccessError) as excinfo:
        sock.connect(("plasmodb.org", 443))
    assert "test_the_refusal_names_the_test" in str(excinfo.value)


def test_name_resolution_is_refused() -> None:
    with pytest.raises(NetworkAccessError):
        socket.getaddrinfo("plasmodb.org", 443)


def test_loopback_is_refused_too() -> None:
    with socket.create_server(("127.0.0.1", 0)) as server:
        address = server.getsockname()
    with socket.socket() as sock, pytest.raises(NetworkAccessError):
        sock.connect(address)


async def test_an_event_loop_connection_is_refused() -> None:
    loop = asyncio.get_running_loop()
    with pytest.raises(NetworkAccessError):
        await loop.getaddrinfo("plasmodb.org", 443)

    with pytest.raises(NetworkAccessError):
        await loop.create_connection(asyncio.Protocol, "plasmodb.org", 443)


def test_a_retry_loop_that_catches_exception_cannot_swallow_it() -> None:
    """The refusal must survive `except Exception`, which every HTTP client has."""
    attempts = 0

    def retrying_client() -> None:
        nonlocal attempts
        for _ in range(3):
            attempts += 1
            with contextlib.suppress(Exception):
                socket.getaddrinfo("plasmodb.org", 443)

    with pytest.raises(NetworkAccessError):
        retrying_client()
    assert attempts == 1


def test_it_is_not_an_exception_subclass() -> None:
    assert not issubclass(NetworkAccessError, Exception)
    assert issubclass(NetworkAccessError, BaseException)


def test_a_bytes_host_is_decoded_in_the_message() -> None:
    loop = asyncio.new_event_loop()
    try:
        with pytest.raises(NetworkAccessError) as excinfo:
            loop.run_until_complete(loop.getaddrinfo(b"plasmodb.org", 443))
    finally:
        loop.close()
    assert "plasmodb.org:443" in str(excinfo.value)
    assert "b'plasmodb.org'" not in str(excinfo.value)


def test_a_unix_socket_is_not_the_network() -> None:
    """The docker client the database fixtures use talks over AF_UNIX.

    The `tmp_path` fixture names the test, which overruns the 104-byte limit on
    an AF_UNIX path, so this makes its own short directory.
    """
    with tempfile.TemporaryDirectory() as directory:
        path = str(Path(directory) / "s")
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
            server.bind(path)
            server.listen(1)
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.connect(path)
                assert client.getpeername() == path


@pytest.mark.allow_network
def test_the_marker_restores_the_real_socket() -> None:
    with (
        socket.create_server(("127.0.0.1", 0)) as server,
        socket.create_connection(server.getsockname()) as conn,
    ):
        assert conn.getpeername() == server.getsockname()
