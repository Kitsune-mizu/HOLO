"""Cek internet: sambungan TCP kecil dengan batas waktu pendek."""
from __future__ import annotations

import socket

_PROBES = (("1.1.1.1", 443), ("8.8.8.8", 53))


def has_internet(timeout: float = 1.5) -> bool:
    for host, port in _PROBES:
        try:
            socket.create_connection((host, port), timeout=timeout).close()
            return True
        except OSError:
            continue
    return False
