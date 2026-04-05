#!/usr/bin/env python3
"""
Ensure all tools from owui-plugin.yaml files are registered in OpenWebUI.

Runs after OWUI boot (as init sidecar, CronJob, or manually).
Idempotent: safe to run multiple times.

Usage:
  python3 scripts/ensure_tools.py
  python3 scripts/ensure_tools.py --db-path /path/to/webui.db
  python3 scripts/ensure_tools.py --mode k8s --namespace miraiku
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import yaml

ROOT_DIR = Path(__file__).resolve().parent.parent


def discover_plugins() -> list[Path]:
    """Find all owui-plugin.yaml from PLUGIN_PATHS env or sibling repos."""
    plugins = []

    # 1. From PLUGIN_PATHS env var
    env_paths = os.environ.get("PLUGIN_PATHS", "")
    if env_paths:
        for p in env_paths.split(","):
            p = p.strip()
            if not p:
                continue
            # Try relative to ROOT_DIR first, then /parent/ (Docker mount)
            for base in [ROOT_DIR, Path("/parent")]:
                candidate = (base / p.lstrip("./")).resolve()
                plugin_file = candidate / "owui-plugin.yaml"
                if plugin_file.exists():
                    plugins.append(plugin_file)
                    break
            else:
                # Try the path as-is
                plugin_file = Path(p).resolve() / "owui-plugin.yaml"
                if plugin_file.exists():
                    plugins.append(plugin_file)

    # 2. Fallback: discover_plugins.sh
    if not plugins:
        try:
            result = subprocess.run(
                ["bash", str(ROOT_DIR / "scripts" / "discover_plugins.sh")],
                capture_output=True, text=True, cwd=str(ROOT_DIR),
            )
            for line in result.stdout.strip().split("\n"):
                if not line.strip():
                    continue
                plugin_file = (ROOT_DIR / line.strip() / "owui-plugin.yaml").resolve()
                if plugin_file.exists():
                    plugins.append(plugin_file)
        except Exception:
            pass

    return plugins


def generate_specs(content: str) -> list[dict]:
    """Parse Python tool file and extract function specs."""
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return []
    specs = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        if node.name.startswith("_") or node.name == "__init__":
            continue
        docstring = ast.get_docstring(node) or ""
        params, required = {}, []
        user_args = [a for a in node.args.args if a.arg != "self" and not a.arg.startswith("__")]
        num_defaults = len(node.args.defaults)
        for i, arg in enumerate(user_args):
            type_map = {"str": "string", "int": "integer", "bool": "boolean", "float": "number"}
            param_type = "string"
            if arg.annotation and isinstance(arg.annotation, ast.Name):
                param_type = type_map.get(arg.annotation.id, "string")
            desc = f"Parameter {arg.arg}"
            for line in docstring.split("\n"):
                if f":param {arg.arg}:" in line:
                    desc = line.split(f":param {arg.arg}:")[1].strip()
                    break
            params[arg.arg] = {"type": param_type, "description": desc}
            if i < (len(user_args) - num_defaults):
                required.append(arg.arg)
        specs.append({
            "name": node.name,
            "description": docstring.split(":param")[0].strip(),
            "parameters": {"type": "object", "properties": params, "required": required},
        })
    return specs


def register_tools_in_db(db_path: str, plugins: list[Path], url_context: str = "k8s") -> int:
    """Register all tools from plugins into OWUI SQLite DB. Returns count."""
    conn = sqlite3.connect(db_path)
    now = int(time.time())
    total = 0

    for plugin_file in plugins:
        plugin = yaml.safe_load(plugin_file.read_text())
        plugin_dir = plugin_file.parent
        plugin_name = plugin.get("name", plugin_dir.name)
        entries = plugin.get("tools", {}).get("entries", [])

        if not entries:
            continue

        print(f"\n--- {plugin_name} ---")

        for entry in entries:
            tool_id = entry["id"]
            source_path = plugin_dir / entry.get("source_file", "")

            if not source_path.exists():
                print(f"  SKIP {tool_id}: {source_path} not found")
                continue

            content = source_path.read_text()

            # Apply URL replacements for the target context
            service = entry.get("service_name", "localhost")
            port = str(entry.get("service_port", 8000))
            for old, new in entry.get("url_replacements", {}).items():
                replacement = new.replace("{{service}}", service).replace("{{port}}", port)
                content = content.replace(old, replacement)

            # For K8s context, also replace host.docker.internal
            if url_context == "k8s":
                content = content.replace(
                    f"http://host.docker.internal:{port}",
                    f"http://{service}:{port}"
                )

            try:
                compile(content, tool_id, "exec")
            except SyntaxError as exc:
                print(f"  SKIP {tool_id}: syntax error line {exc.lineno}")
                continue

            specs = generate_specs(content)
            meta = json.dumps({
                "description": entry.get("description", entry.get("name", tool_id)),
                "manifest": {
                    "title": entry.get("name", tool_id),
                    "author": "auto-registered",
                    "version": "auto",
                },
            })

            # Detect if it's a filter (class Filter) or a tool (class Tools)
            is_filter = "class Filter" in content and "class Tools" not in content

            if is_filter:
                conn.execute(
                    """INSERT OR REPLACE INTO function
                    (id, user_id, name, type, content, meta, is_active, is_global, created_at, updated_at)
                    VALUES (?, ?, ?, 'filter', ?, ?, 1, 1, ?, ?)""",
                    (tool_id, "", entry.get("name", tool_id), content, meta, now, now),
                )
                # Remove from tool table if it was incorrectly placed there
                conn.execute("DELETE FROM tool WHERE id = ?", (tool_id,))
                print(f"  OK: {tool_id} (filter, {len(specs)} methods)")
            else:
                conn.execute(
                    """INSERT OR REPLACE INTO tool
                    (id, user_id, name, content, specs, meta, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (tool_id, "", entry.get("name", tool_id), content, json.dumps(specs), meta, now, now),
                )
                print(f"  OK: {tool_id} ({len(specs)} methods)")
            total += 1

    conn.commit()
    conn.close()
    return total


def ensure_mcp_servers(db_path: str, servers: list[dict]) -> None:
    """Ensure MCP tool servers are configured in the OWUI config table."""
    conn = sqlite3.connect(db_path)

    rows = conn.execute("SELECT id, data FROM config ORDER BY id DESC LIMIT 1").fetchall()

    if rows:
        config = json.loads(rows[0][1])
    else:
        config = {}

    config.setdefault("tool_server", {})
    existing_urls = {c.get("url") for c in config["tool_server"].get("connections", [])}

    connections = config["tool_server"].get("connections", [])
    for server in servers:
        if server["url"] not in existing_urls:
            connections.append(server)
            print(f"  Added MCP server: {server['name']}")
        else:
            print(f"  Already configured: {server['name']}")

    config["tool_server"]["connections"] = connections

    if rows:
        conn.execute("UPDATE config SET data = ? WHERE id = ?", (json.dumps(config), rows[0][0]))
    else:
        import datetime
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        conn.execute(
            "INSERT INTO config (data, version, created_at, updated_at) VALUES (?, 0, ?, ?)",
            (json.dumps(config), now, now),
        )

    conn.commit()
    conn.close()


def wait_for_db(db_path: str, timeout: int = 120) -> bool:
    """Wait for OWUI DB to be available and have the tool table."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            conn = sqlite3.connect(db_path)
            conn.execute("SELECT count(*) FROM tool")
            conn.close()
            return True
        except Exception:
            time.sleep(5)
    return False


def main():
    parser = argparse.ArgumentParser(description="Ensure tools are registered in OpenWebUI")
    parser.add_argument("--db-path", default=None, help="Path to webui.db")
    parser.add_argument("--mode", choices=["docker", "k8s"], default="docker")
    parser.add_argument("--namespace", default="miraiku")
    parser.add_argument("--wait", action="store_true", help="Wait for DB to be ready")
    args = parser.parse_args()

    # Determine DB path
    if args.db_path:
        db_path = args.db_path
    elif args.mode == "docker":
        # Try common Docker paths
        candidates = [
            "/app/backend/data/webui.db",  # inside OWUI container
            str(ROOT_DIR / "openwebui" / "data" / "webui.db"),  # bind mount
        ]
        db_path = next((p for p in candidates if Path(p).exists()), candidates[0])
    else:
        db_path = "/app/backend/data/webui.db"

    print(f"=== ensure_tools (mode={args.mode}, db={db_path}) ===\n")

    if args.wait:
        print("Waiting for OWUI DB...")
        if not wait_for_db(db_path):
            print("ERROR: DB not ready after timeout")
            sys.exit(1)
        print("DB ready\n")

    # 1. Register tools from plugins
    plugins = discover_plugins()
    print(f"Found {len(plugins)} plugins")

    url_context = "docker" if args.mode == "docker" else "k8s"
    total = register_tools_in_db(db_path, plugins, url_context)
    print(f"\nRegistered {total} tools")

    # 2. Ensure MCP servers
    print("\n--- MCP Servers ---")
    mcp_servers = [
        {
            "url": "https://mcp.data.gouv.fr/mcp",
            "type": "mcp",
            "path": "",
            "name": "Données ouvertes France (data.gouv.fr)",
            "description": "Recherche parmi 74 000+ jeux de données publics",
            "auth_type": "none",
            "key": "",
            "config": {"enable": True},
        },
    ]
    ensure_mcp_servers(db_path, mcp_servers)

    print("\n=== Done ===")


if __name__ == "__main__":
    main()
