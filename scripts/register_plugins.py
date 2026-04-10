#!/usr/bin/env python3
"""
Register tools, pipelines, and model_tools from owui-plugin.yaml files
into OpenWebUI via its REST API.

Replaces the old register_all_openwebui_tools.py (SQLite direct access).

Discovery: reads PLUGIN_PATHS env var (comma-separated paths to feature repos)
or uses discover_plugins.sh to find sibling repos with owui-plugin.yaml.

Usage:
  python3 scripts/register_plugins.py
  python3 scripts/register_plugins.py --plugin-paths ../grafrag-experimentation,../tchap-reader
  PLUGIN_PATHS=../grafrag-experimentation python3 scripts/register_plugins.py
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

import yaml

ROOT_DIR = Path(__file__).resolve().parent.parent
OWUI_BASE_URL = os.environ.get("OWUI_API_URL", "http://localhost:3000")
OWUI_API_KEY = os.environ.get("OWUI_API_KEY", "")


# ---------------------------------------------------------------------------
# Plugin discovery
# ---------------------------------------------------------------------------

def discover_plugins(extra_paths: list[str] | None = None) -> list[Path]:
    """Find all owui-plugin.yaml files from configured sources."""
    paths: list[str] = []

    # From env var
    env_paths = os.environ.get("PLUGIN_PATHS", "")
    if env_paths:
        paths.extend(p.strip() for p in env_paths.split(",") if p.strip())

    # From CLI argument
    if extra_paths:
        paths.extend(extra_paths)

    # Fallback: run discover_plugins.sh if it exists and no paths given
    if not paths:
        discover_script = ROOT_DIR / "scripts" / "discover_plugins.sh"
        if discover_script.exists():
            result = subprocess.run(
                ["bash", str(discover_script)],
                capture_output=True, text=True, cwd=str(ROOT_DIR),
            )
            if result.returncode == 0:
                paths.extend(p.strip() for p in result.stdout.strip().split("\n") if p.strip())

    plugins = []
    for p in paths:
        repo_path = (ROOT_DIR / p).resolve()
        plugin_file = repo_path / "owui-plugin.yaml"
        if plugin_file.exists():
            plugins.append(plugin_file)
            print(f"  Found: {plugin_file}")
        else:
            print(f"  Skip: {repo_path} (no owui-plugin.yaml)")

    return plugins


def load_plugin(path: Path) -> dict:
    """Load and return the owui-plugin.yaml content."""
    with open(path) as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# OpenWebUI REST API client
# ---------------------------------------------------------------------------

def owui_request(method: str, endpoint: str, data: dict | None = None) -> dict | list | None:
    """Make a request to the OpenWebUI API."""
    url = f"{OWUI_BASE_URL}/api/v1{endpoint}"
    headers = {"Content-Type": "application/json"}
    if OWUI_API_KEY:
        headers["Authorization"] = f"Bearer {OWUI_API_KEY}"

    body = json.dumps(data).encode() if data else None
    req = Request(url, data=body, headers=headers, method=method)

    try:
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except HTTPError as e:
        body_text = e.read().decode()[:500]
        print(f"  API error {e.code} on {method} {endpoint}: {body_text}")
        return None
    except URLError as e:
        print(f"  Connection error on {method} {endpoint}: {e.reason}")
        return None


def get_existing_tools() -> dict[str, dict]:
    """Fetch all existing tools from OWUI, keyed by ID."""
    tools = owui_request("GET", "/tools/")
    if tools is None:
        return {}
    return {t["id"]: t for t in tools}


# ---------------------------------------------------------------------------
# Tool source processing (reused from old script)
# ---------------------------------------------------------------------------

def resolve_source(plugin_dir: Path, entry: dict, url_context: str = "k8s") -> str:
    """Read the source Python file and apply URL replacements."""
    file_path = plugin_dir / entry["source_file"]
    if not file_path.exists():
        print(f"  WARNING: {file_path} not found, skipping")
        return ""

    content = file_path.read_text()

    service = entry.get("service_name", "localhost")
    port = str(entry.get("service_port", 8000))
    k8s_port = str(entry.get("k8s_port", port))
    for old, new in entry.get("url_replacements", {}).items():
        replacement = new.replace("{{service}}", service).replace("{{port}}", port)
        content = content.replace(old, replacement)

    # For K8s context, replace Docker-local URLs with K8s service names
    if url_context == "k8s":
        for docker_host in [f"http://host.docker.internal:{port}",
                            f"http://localhost:{port}"]:
            content = content.replace(docker_host, f"http://{service}:{k8s_port}")
        # Also replace openwebui references (Docker port 8080 → K8s port 80)
        content = content.replace("http://host.docker.internal:8080", "http://openwebui:80")
        content = content.replace("http://localhost:8080", "http://openwebui:80")

    return content


def generate_specs(content: str) -> list[dict]:
    """Parse the Python tool file and extract function specs for OpenWebUI."""
    try:
        tree = ast.parse(content)
    except SyntaxError as exc:
        print(f"  SYNTAX ERROR: {exc}")
        return []

    specs = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        if node.name.startswith("_") or node.name == "__init__":
            continue

        docstring = ast.get_docstring(node) or ""
        params = {}
        required = []
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
            "parameters": {
                "type": "object",
                "properties": params,
                "required": required,
            },
        })

    return specs


# ---------------------------------------------------------------------------
# Registration logic
# ---------------------------------------------------------------------------

def register_tools(plugin_dir: Path, plugin: dict, existing_tools: dict[str, dict]) -> int:
    """Register tools from a plugin via OWUI REST API. Returns count of registered tools."""
    tools_section = plugin.get("tools", {})
    entries = tools_section.get("entries", [])
    if not entries:
        return 0

    count = 0
    for entry in entries:
        tool_id = entry["id"]
        content = resolve_source(plugin_dir, entry)
        if not content:
            continue

        try:
            compile(content, tool_id, "exec")
        except SyntaxError as exc:
            print(f"  SKIP {tool_id}: syntax error line {exc.lineno}")
            continue

        specs = generate_specs(content)
        meta = {
            "description": entry.get("description", entry.get("id", "")),
            "manifest": {
                "title": entry.get("name", tool_id),
                "author": "auto-registered",
                "version": "auto",
            },
        }

        payload = {
            "id": tool_id,
            "name": entry.get("name", tool_id),
            "content": content,
            "specs": specs,
            "meta": meta,
        }

        if tool_id in existing_tools:
            result = owui_request("POST", f"/tools/{tool_id}/update", payload)
            action = "Updated"
        else:
            result = owui_request("POST", "/tools/create", payload)
            action = "Created"

        if result:
            print(f"  OK {action}: {tool_id} ({len(specs)} methods)")
            count += 1
        else:
            print(f"  FAIL {action}: {tool_id}")

    return count


def register_model_tools(plugin: dict) -> int:
    """Apply model → tool associations. Returns count of updated models."""
    model_tools = plugin.get("model_tools", [])
    if not model_tools:
        return 0

    count = 0
    for entry in model_tools:
        model_ids = entry.get("models", [])
        tool_ids = entry.get("tool_ids", [])
        system_prompt = entry.get("system", "").strip()

        for model_id in model_ids:
            # Get current model config
            model = owui_request("GET", f"/models/{model_id}")
            if not model:
                print(f"  SKIP model {model_id}: not found")
                continue

            meta = model.get("meta", {})
            meta["toolIds"] = tool_ids

            params = model.get("params", {})
            if system_prompt:
                params["system"] = system_prompt

            result = owui_request("POST", f"/models/{model_id}/update", {
                "meta": meta,
                "params": params,
            })

            if result:
                tools_str = ", ".join(tool_ids)
                print(f"  OK model {model_id}: tools=[{tools_str}]")
                count += 1
            else:
                print(f"  FAIL model {model_id}")

    return count


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Register plugins into OpenWebUI via REST API")
    parser.add_argument("--plugin-paths", default=None, help="Comma-separated paths to feature repos")
    parser.add_argument("--owui-url", default=None, help="OpenWebUI base URL")
    parser.add_argument("--owui-api-key", default=None, help="OpenWebUI API key")
    args = parser.parse_args()

    global OWUI_BASE_URL, OWUI_API_KEY
    if args.owui_url:
        OWUI_BASE_URL = args.owui_url
    if args.owui_api_key:
        OWUI_API_KEY = args.owui_api_key

    print(f"=== Register plugins (API: {OWUI_BASE_URL}) ===\n")

    extra_paths = [p.strip() for p in args.plugin_paths.split(",")] if args.plugin_paths else None
    plugins = discover_plugins(extra_paths)

    if not plugins:
        print("No plugins found. Set PLUGIN_PATHS or run discover_plugins.sh.")
        sys.exit(0)

    # Fetch existing tools for idempotent upsert
    print("\nFetching existing tools from OpenWebUI...")
    existing_tools = get_existing_tools()
    print(f"  Found {len(existing_tools)} existing tools\n")

    total_tools = 0
    total_models = 0

    for plugin_path in plugins:
        plugin = load_plugin(plugin_path)
        plugin_dir = plugin_path.parent
        name = plugin.get("name", plugin_dir.name)
        print(f"\n--- Plugin: {name} (v{plugin.get('version', '?')}) ---\n")

        total_tools += register_tools(plugin_dir, plugin, existing_tools)
        total_models += register_model_tools(plugin)

    print(f"\n=== Done: {total_tools} tools, {total_models} model associations ===")


if __name__ == "__main__":
    main()
