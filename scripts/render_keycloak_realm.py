#!/usr/bin/env python3
"""Render the Keycloak realm JSON with optional local password overrides."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


PLACEHOLDER_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def fail(message: str) -> "NoReturn":
    print(f"Error: {message}", file=sys.stderr)
    raise SystemExit(1)


def render_template(text: str, env: dict[str, str]) -> str:
    missing: set[str] = set()

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in env:
            missing.add(name)
            return match.group(0)
        return env[name]

    rendered = PLACEHOLDER_RE.sub(replace, text)
    if missing:
        fail(
            "Missing environment variables required to render the Keycloak realm: "
            + ", ".join(sorted(missing))
        )
    return rendered


def load_password_overrides(path: Path | None) -> dict[str, str]:
    if path is None or not path.exists():
        return {}

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        fail(f"Password override file must contain a JSON object: {path}")

    if "users" in payload:
        users = payload.get("users")
        if not isinstance(users, list):
            fail(f"'users' must be a list in {path}")
        overrides: dict[str, str] = {}
        for item in users:
            if not isinstance(item, dict):
                fail(f"Each user entry must be an object in {path}")
            username = item.get("username")
            password = item.get("password")
            if username and password:
                overrides[str(username)] = str(password)
        return overrides

    if "passwords" in payload:
        passwords = payload.get("passwords")
        if not isinstance(passwords, dict):
            fail(f"'passwords' must be an object in {path}")
        return {
            str(username): str(password)
            for username, password in passwords.items()
            if username and password
        }

    return {
        str(username): str(password)
        for username, password in payload.items()
        if username and password
    }


def apply_password_overrides(realm: dict[str, Any], overrides: dict[str, str]) -> dict[str, Any]:
    if not overrides:
        return realm

    users = realm.get("users")
    if not isinstance(users, list):
        fail("Realm JSON does not contain a top-level 'users' array.")

    for user in users:
        username = user.get("username")
        if username not in overrides:
            continue

        credentials = user.setdefault("credentials", [])
        if not isinstance(credentials, list):
            fail(f"User '{username}' has a non-list 'credentials' value.")

        password_credentials = [
            credential
            for credential in credentials
            if isinstance(credential, dict) and credential.get("type") == "password"
        ]

        if not password_credentials:
            credentials.append(
                {
                    "type": "password",
                    "value": overrides[str(username)],
                    "temporary": False,
                }
            )
            continue

        for credential in password_credentials:
            credential["value"] = overrides[str(username)]
            credential["temporary"] = False

    return realm


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render the Keycloak realm JSON with optional local password overrides."
    )
    parser.add_argument("--source", required=True, help="Source realm JSON template.")
    parser.add_argument("--output", required=True, help="Rendered realm JSON output path.")
    parser.add_argument(
        "--password-file",
        help="Optional JSON file containing per-user password overrides.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source_path = Path(args.source).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    password_path = (
        Path(args.password_file).expanduser().resolve() if args.password_file else None
    )

    source_text = source_path.read_text(encoding="utf-8")
    rendered_text = render_template(source_text, dict(os.environ))
    realm = json.loads(rendered_text)
    overrides = load_password_overrides(password_path)
    rendered_realm = apply_password_overrides(realm, overrides)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(rendered_realm, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
