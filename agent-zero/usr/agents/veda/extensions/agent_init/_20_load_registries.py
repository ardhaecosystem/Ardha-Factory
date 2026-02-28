import json
import os
import sys
from python.helpers.extension import Extension

VEDA_STATE_DIR = "/a0/usr/veda-state"
SCRIPTS_DIR = "/a0/usr/agents/veda/scripts"

REGISTRY_FILES = [
    "team_registry.json",
    "project_registry.json",
    "pipeline_state.json",
    "restart_required.json",
    "faiss_namespace_map.json",
    "extension_mtimes.json",
]


def _import_registry_io():
    if SCRIPTS_DIR not in sys.path:
        sys.path.insert(0, SCRIPTS_DIR)
    from registry_io import load_registry, verify_checksum, CorruptionError
    return load_registry, verify_checksum, CorruptionError


class VedaLoadRegistries(Extension):
    """
    Fired once at agent_init (after _10_veda_identity.py).
    Loads all Veda state registry files from usr/veda-state/
    into agent.data["registries"] for session-wide access.

    Performs startup health checks:
    - SHA-256 checksum verification on every registry file
    - Validates schema_version on every registry file
    - Detects missing registry files and reports them
    - Detects restart_required flag and injects warning
    - Detects extension file mtime drift from baseline
    """

    async def execute(self, **kwargs) -> None:
        load_registry, verify_checksum, CorruptionError = _import_registry_io()

        registries = {}
        errors = []
        warnings = []

        for fname in REGISTRY_FILES:
            fpath = os.path.join(VEDA_STATE_DIR, fname)
            key = fname.replace(".json", "")

            if not os.path.exists(fpath):
                errors.append(f"MISSING registry file: {fpath}")
                registries[key] = None
                continue

            try:
                data = load_registry(fpath)
                if data.get("schema_version") != "3.0.0":
                    warnings.append(
                        f"Schema mismatch in {fname}: "
                        f"expected 3.0.0, got {data.get('schema_version')}"
                    )
                registries[key] = data
            except CorruptionError as e:
                errors.append(f"CORRUPTION in {fname}: {e.reason}")
                registries[key] = None
            except Exception as e:
                errors.append(f"Load error in {fname}: {e}")
                registries[key] = None

        self.agent.set_data("registries", registries)

        restart = registries.get("restart_required")
        if restart and restart.get("required") is True:
            warnings.append(
                f"[RESTART REQUIRED] Reason: {restart.get('reason')} | "
                f"Triggered by: {restart.get('triggered_by')} | "
                f"Triggered at: {restart.get('triggered_at')} | "
                f"Pending changes: {restart.get('pending_changes')}"
            )

        mtime_data = registries.get("extension_mtimes")
        if mtime_data and mtime_data.get("files"):
            drift_detected = []
            for rel_path, baseline_mtime in mtime_data["files"].items():
                abs_path = os.path.join("/a0/usr", rel_path)
                if os.path.exists(abs_path):
                    current_mtime = os.path.getmtime(abs_path)
                    if abs(current_mtime - baseline_mtime) > 1.0:
                        drift_detected.append(rel_path)
            if drift_detected:
                warnings.append(
                    f"[EXTENSION DRIFT] The following extension files have changed "
                    f"since baseline — a container restart is required: {drift_detected}"
                )

        health = {
            "errors": errors,
            "warnings": warnings,
            "registry_files_loaded": [k for k, v in registries.items() if v is not None],
            "registry_files_missing": [k for k, v in registries.items() if v is None],
        }
        self.agent.set_data("veda_health", health)

        if errors:
            for e in errors:
                print(f"[Veda:INIT:ERROR] {e}")
        if warnings:
            for w in warnings:
                print(f"[Veda:INIT:WARN] {w}")
        if not errors and not warnings:
            print(
                f"[Veda:INIT] Registries loaded successfully. "
                f"Files: {health['registry_files_loaded']}"
            )
