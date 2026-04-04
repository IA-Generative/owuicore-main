#!/usr/bin/env python3
"""
Hot-reload watcher for dev: monitors owui-plugin.yaml and tool source files
in discovered plugin repos, and re-registers into OpenWebUI when changes occur.

Runs as a Docker service (profile: dev) or standalone:
  python3 scripts/register_watcher.py
  python3 scripts/register_watcher.py --interval 10

Dependencies: watchdog, pyyaml (both in requirements-watcher.txt)
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
REGISTER_SCRIPT = ROOT_DIR / "scripts" / "register_plugins.py"
DISCOVER_SCRIPT = ROOT_DIR / "scripts" / "discover_plugins.sh"

POLL_INTERVAL = int(os.environ.get("WATCHER_INTERVAL", "5"))


def discover_watch_paths() -> list[Path]:
    """Find all owui-plugin.yaml files and their tool source dirs."""
    result = subprocess.run(
        ["bash", str(DISCOVER_SCRIPT)],
        capture_output=True, text=True, cwd=str(ROOT_DIR),
    )
    paths = []
    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue
        repo = (ROOT_DIR / line.strip()).resolve()
        plugin_file = repo / "owui-plugin.yaml"
        if plugin_file.exists():
            paths.append(plugin_file)
            # Also watch source files referenced in the plugin
            try:
                import yaml
                with open(plugin_file) as f:
                    plugin = yaml.safe_load(f)
                for entry in plugin.get("tools", {}).get("entries", []):
                    src = repo / entry.get("source_file", "")
                    if src.exists():
                        paths.append(src)
                for pf in plugin.get("pipelines", {}).get("files", []):
                    src = repo / pf
                    if src.exists():
                        paths.append(src)
            except Exception:
                pass
    return paths


def get_mtimes(paths: list[Path]) -> dict[Path, float]:
    """Get modification times for all watched paths."""
    mtimes = {}
    for p in paths:
        try:
            mtimes[p] = p.stat().st_mtime
        except FileNotFoundError:
            pass
    return mtimes


def run_register():
    """Execute the registration script."""
    print(f"[watcher] Registering plugins...", flush=True)
    result = subprocess.run(
        [sys.executable, str(REGISTER_SCRIPT)],
        cwd=str(ROOT_DIR),
    )
    if result.returncode == 0:
        print(f"[watcher] Registration complete.", flush=True)
    else:
        print(f"[watcher] Registration failed (exit {result.returncode}).", flush=True)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval", type=int, default=POLL_INTERVAL)
    args = parser.parse_args()

    print(f"[watcher] Starting (poll interval: {args.interval}s)", flush=True)

    # Initial registration
    run_register()

    # Watch loop
    watch_paths = discover_watch_paths()
    print(f"[watcher] Watching {len(watch_paths)} files", flush=True)
    last_mtimes = get_mtimes(watch_paths)

    while True:
        time.sleep(args.interval)

        # Re-discover periodically (new plugins may appear)
        watch_paths = discover_watch_paths()
        current_mtimes = get_mtimes(watch_paths)

        if current_mtimes != last_mtimes:
            changed = [
                str(p) for p in current_mtimes
                if current_mtimes.get(p) != last_mtimes.get(p)
            ]
            new_files = [str(p) for p in current_mtimes if p not in last_mtimes]
            if changed:
                print(f"[watcher] Changed: {', '.join(changed)}", flush=True)
            if new_files:
                print(f"[watcher] New: {', '.join(new_files)}", flush=True)
            run_register()
            last_mtimes = current_mtimes


if __name__ == "__main__":
    main()
