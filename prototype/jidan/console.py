from __future__ import annotations

from typing import Any
import sys


def configure_utf8_stdio(*, stdout: Any = None, stderr: Any = None) -> None:
    """Make JSON/Chinese CLI output deterministic on Windows and redirected pipes."""

    streams = (
        sys.stdout if stdout is None else stdout,
        sys.stderr if stderr is None else stderr,
    )
    for stream in streams:
        reconfigure = getattr(stream, "reconfigure", None)
        if not callable(reconfigure):
            continue
        try:
            reconfigure(encoding="utf-8", errors="backslashreplace")
        except (OSError, ValueError):
            # Closed/replaced test streams should not prevent the command itself.
            continue
