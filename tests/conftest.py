"""Offline tests: forbid production databases and external network access."""
import sqlite3
import ipaddress
import socket
import sys
import tempfile
from pathlib import Path



import pytest


REPO = Path(__file__).resolve().parents[1]
_original_connect = sqlite3.connect
_original_dbapi_connect = sqlite3.dbapi2.connect


def _isolated_connect(database, *args, **kwargs):
    value = str(database)
    if value.startswith("file:") or (
        value != ":memory:" and Path(value).resolve().is_relative_to(REPO / "data")
    ):
        raise RuntimeError("Tests must not open the business database or SQLite URI paths")
    return _original_connect(database, *args, **kwargs)


# Runs before collection, not merely before individual tests.
sqlite3.connect = _isolated_connect
sqlite3.dbapi2.connect = _isolated_connect


@pytest.fixture(autouse=True)
def no_external_network(monkeypatch):
    # Windows asyncio builds its internal socketpair using a loopback TCP
    # connection. Permit that, but reject remote endpoints and hostnames.
    def guard(original):
        def connect(sock, address):
            try:
                local = isinstance(address, tuple) and ipaddress.ip_address(address[0]).is_loopback
            except ValueError:
                local = False
            if not local:
                raise RuntimeError("Offline test attempted an external network connection")
            return original(sock, address)
        return connect
    monkeypatch.setattr(socket.socket, 'connect', guard(socket.socket.connect))
    monkeypatch.setattr(socket.socket, 'connect_ex', guard(socket.socket.connect_ex))


def pytest_unconfigure(config):
    sqlite3.connect = _original_connect
    sqlite3.dbapi2.connect = _original_dbapi_connect
