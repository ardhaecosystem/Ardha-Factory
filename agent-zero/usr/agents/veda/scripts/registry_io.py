"""
registry_io.py — Ardha Factory shared registry I/O with checksum protection.

Every registry JSON file gets a sidecar .sha256 file written alongside it.
On load, the checksum is recomputed and compared. Mismatch = corruption detected.

Usage:
    from registry_io import save_registry, load_registry, verify_checksum

    data = load_registry("/a0/usr/veda-state/team_registry.json")
    save_registry("/a0/usr/veda-state/team_registry.json", data)
"""

import hashlib
import json
import os
import tempfile
from typing import Any


def _checksum_path(json_path: str) -> str:
    """Return the .sha256 sidecar path for a given JSON file."""
    return json_path + ".sha256"


def _compute_checksum(content: str) -> str:
    """Compute SHA-256 of the JSON string content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def save_registry(path: str, data: dict[str, Any]) -> None:
    """
    Atomically write a registry JSON file and its SHA-256 sidecar.
    Uses write-then-rename for atomicity (POSIX safe).
    Raises OSError on filesystem failure.
    """
    content = json.dumps(data, indent=2)
    checksum = _compute_checksum(content)
    dir_name = os.path.dirname(path)

    # Write JSON atomically
    fd, tmp_json = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
        os.rename(tmp_json, path)
    except Exception:
        try:
            os.unlink(tmp_json)
        except OSError:
            pass
        raise

    # Write checksum sidecar atomically
    sidecar = _checksum_path(path)
    fd2, tmp_sha = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
    try:
        with os.fdopen(fd2, "w") as f:
            f.write(checksum)
        os.rename(tmp_sha, sidecar)
    except Exception:
        try:
            os.unlink(tmp_sha)
        except OSError:
            pass
        raise


def load_registry(path: str) -> dict[str, Any] | None:
    """
    Load a registry JSON file and verify its SHA-256 checksum.

    Returns the parsed dict on success.
    Returns None if the file does not exist.
    Raises CorruptionError if the file exists but checksum fails or JSON is invalid.
    """
    if not os.path.exists(path):
        return None

    # Read JSON content
    try:
        with open(path, "r") as f:
            content = f.read()
    except OSError as e:
        raise CorruptionError(path, f"Cannot read file: {e}")

    # Parse JSON
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        raise CorruptionError(path, f"Invalid JSON: {e}")

    # Verify checksum if sidecar exists
    sidecar = _checksum_path(path)
    if os.path.exists(sidecar):
        try:
            with open(sidecar, "r") as f:
                stored_checksum = f.read().strip()
        except OSError as e:
            raise CorruptionError(path, f"Cannot read checksum sidecar: {e}")

        actual_checksum = _compute_checksum(content)
        if actual_checksum != stored_checksum:
            raise CorruptionError(
                path,
                f"Checksum mismatch — file may be corrupt or tampered.\n"
                f"  Stored:   {stored_checksum}\n"
                f"  Computed: {actual_checksum}"
            )
    # No sidecar yet — legacy file, load without verification
    # (sidecar will be written on next save_registry call)

    return data


def verify_checksum(path: str) -> tuple[bool, str]:
    """
    Verify checksum of a registry file without loading it into memory.
    Returns (ok: bool, message: str).
    """
    if not os.path.exists(path):
        return False, f"File not found: {path}"

    sidecar = _checksum_path(path)
    if not os.path.exists(sidecar):
        return True, f"No sidecar yet (legacy) — will be written on next save"

    try:
        with open(path, "r") as f:
            content = f.read()
        with open(sidecar, "r") as f:
            stored = f.read().strip()
    except OSError as e:
        return False, f"Read error: {e}"

    try:
        json.loads(content)
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON: {e}"

    actual = _compute_checksum(content)
    if actual != stored:
        return False, (
            f"CHECKSUM MISMATCH\n"
            f"  Stored:   {stored}\n"
            f"  Computed: {actual}"
        )

    return True, f"OK (sha256:{stored[:16]}...)"


class CorruptionError(Exception):
    """Raised when a registry file fails checksum verification or JSON parsing."""

    def __init__(self, path: str, reason: str):
        self.path = path
        self.reason = reason
        super().__init__(f"Registry corruption detected in {path}: {reason}")
