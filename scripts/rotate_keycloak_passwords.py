#!/usr/bin/env python3
"""Rotate Keycloak realm user passwords for the Kubernetes deployment.

The current Kubernetes deployment imports the realm from a ConfigMap and runs
Keycloak with an ephemeral database. For that reason, password rotation needs
to update both:
- the live Keycloak users, so the new passwords work immediately
- the source realm files and the `keycloak-realm` ConfigMap, so the next
  Keycloak restart keeps the new passwords
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import secrets
import shutil
import string
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_FILES = (
    ROOT_DIR / "keycloak" / "realm-openwebui.k8s.json",
    ROOT_DIR / "keycloak" / "realm-openwebui.json",
)
DEFAULT_PASSWORD_STORE = ROOT_DIR / "keycloak" / "realm-passwords.local.json"
ENV_VAR_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
PLACEHOLDER_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def fail(message: str) -> "NoReturn":
    print(f"Error: {message}", file=sys.stderr)
    raise SystemExit(1)


def load_dotenv(env_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not env_path.exists():
        return values

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip("\r")
        if not line.strip():
            continue
        if line.lstrip().startswith("#"):
            continue

        stripped = line.lstrip()
        if stripped.startswith("export "):
            stripped = stripped[7:]

        if "=" not in stripped:
            continue

        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip()

        if not ENV_VAR_RE.match(key):
            continue

        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            quote = value[0]
            value = value[1:-1]
            if quote == '"':
                value = bytes(value, "utf-8").decode("unicode_escape")

        values[key] = value

    return values


def merged_env(env_path: Path) -> dict[str, str]:
    env = load_dotenv(env_path)
    env.update(os.environ)
    return env


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Rotate Keycloak user passwords for the Kubernetes deployment and "
            "keep the realm bootstrap files in sync."
        )
    )
    parser.add_argument(
        "--env-file",
        default=str(ROOT_DIR / ".env"),
        help="Path to the .env file used for defaults.",
    )
    parser.add_argument(
        "--source-file",
        action="append",
        default=[],
        help=(
            "Realm JSON file to update. Repeat the flag to update multiple files. "
            "Defaults to the Kubernetes and local realm files."
        ),
    )
    parser.add_argument(
        "--users",
        help=(
            "Comma-separated usernames to rotate. Defaults to all users declared "
            "in the primary source file."
        ),
    )
    parser.add_argument(
        "--password-store",
        default=str(DEFAULT_PASSWORD_STORE),
        help=(
            "Ignored local JSON file where rotated passwords are stored for future "
            "Kubernetes renders. Default: keycloak/realm-passwords.local.json."
        ),
    )
    parser.add_argument(
        "--length",
        type=int,
        default=32,
        help="Password length. Minimum: 16. Default: 32.",
    )
    parser.add_argument(
        "--namespace",
        help="Kubernetes namespace. Defaults to NAMESPACE from the environment.",
    )
    parser.add_argument(
        "--realm",
        help="Keycloak realm. Defaults to KEYCLOAK_REALM from the environment.",
    )
    parser.add_argument(
        "--keycloak-admin",
        help="Keycloak admin username. Defaults to KEYCLOAK_ADMIN from the environment.",
    )
    parser.add_argument(
        "--keycloak-label",
        default="app=keycloak",
        help="Label selector used to find the Keycloak pod. Default: app=keycloak.",
    )
    parser.add_argument(
        "--secret-name",
        default="grafrag-secrets",
        help="Secret containing the Keycloak admin password. Default: grafrag-secrets.",
    )
    parser.add_argument(
        "--secret-key",
        default="KEYCLOAK_ADMIN_PASSWORD",
        help="Key within the Kubernetes secret. Default: KEYCLOAK_ADMIN_PASSWORD.",
    )
    parser.add_argument(
        "--configmap-name",
        default="keycloak-realm",
        help="ConfigMap storing the rendered realm JSON. Default: keycloak-realm.",
    )
    parser.add_argument(
        "--deployment",
        default="keycloak",
        help="Keycloak deployment name used for rollout restart. Default: keycloak.",
    )
    parser.add_argument(
        "--output",
        help=(
            "Optional file path where the generated credentials will be written as JSON. "
            "The file is created with mode 0600."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate and display the rotation plan without changing files or the cluster.",
    )
    parser.add_argument(
        "--skip-live",
        action="store_true",
        help="Do not update passwords through the live Keycloak admin CLI.",
    )
    parser.add_argument(
        "--skip-configmap",
        action="store_true",
        help="Do not re-apply the keycloak-realm ConfigMap in Kubernetes.",
    )
    parser.add_argument(
        "--skip-restart",
        action="store_true",
        help="Do not restart the Keycloak deployment after rotation.",
    )
    return parser.parse_args()


def ensure_minimum_length(length: int) -> None:
    if length < 16:
        fail("--length must be at least 16.")


def resolve_source_files(args: argparse.Namespace) -> list[Path]:
    if args.source_file:
        files = [Path(path).expanduser().resolve() for path in args.source_file]
    else:
        files = [path.resolve() for path in DEFAULT_SOURCE_FILES if path.exists()]

    if not files:
        fail("No realm source files were found.")

    missing = [str(path) for path in files if not path.exists()]
    if missing:
        fail(f"Missing realm source files: {', '.join(missing)}")

    deduped: list[Path] = []
    seen: set[Path] = set()
    for path in files:
        if path in seen:
            continue
        deduped.append(path)
        seen.add(path)
    return deduped


def load_realm(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"Failed to parse JSON in {path}: {exc}")


def collect_users(realm: dict[str, Any]) -> list[dict[str, Any]]:
    users = realm.get("users")
    if not isinstance(users, list):
        fail("Realm JSON does not contain a top-level 'users' array.")
    return users


def select_user_records(
    realm_users: list[dict[str, Any]], requested_users: str | None
) -> list[dict[str, str]]:
    by_username: dict[str, dict[str, str]] = {}
    for user in realm_users:
        username = user.get("username")
        if not username:
            continue
        by_username[str(username)] = {
            "username": str(username),
            "email": str(user.get("email", "")),
        }

    if not by_username:
        fail("No users with a username were found in the primary realm file.")

    if requested_users:
        usernames = [item.strip() for item in requested_users.split(",") if item.strip()]
        if not usernames:
            fail("--users was provided but no valid usernames were parsed.")
    else:
        usernames = sorted(by_username)

    missing = [username for username in usernames if username not in by_username]
    if missing:
        fail(f"Unknown users in --users: {', '.join(missing)}")

    return [by_username[username] for username in usernames]


def generate_password(length: int) -> str:
    lower = string.ascii_lowercase
    upper = string.ascii_uppercase
    digits = string.digits
    symbols = "@#%+=:_-"
    alphabet = lower + upper + digits + symbols

    chars = [
        secrets.choice(lower),
        secrets.choice(upper),
        secrets.choice(digits),
        secrets.choice(symbols),
    ]
    chars.extend(secrets.choice(alphabet) for _ in range(length - len(chars)))
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


def update_realm_users(
    realm_data: dict[str, Any], password_by_user: dict[str, str], source_path: Path
) -> None:
    found: set[str] = set()
    for user in collect_users(realm_data):
        username = user.get("username")
        if username not in password_by_user:
            continue

        password_value = password_by_user[str(username)]
        credentials = user.setdefault("credentials", [])
        if not isinstance(credentials, list):
            fail(f"User '{username}' in {source_path} has a non-list 'credentials' value.")

        password_credentials = [
            credential
            for credential in credentials
            if isinstance(credential, dict) and credential.get("type") == "password"
        ]

        if not password_credentials:
            credentials.append(
                {
                    "type": "password",
                    "value": password_value,
                    "temporary": False,
                }
            )
        else:
            for credential in password_credentials:
                credential["value"] = password_value
                credential["temporary"] = False

        found.add(str(username))

    missing = sorted(set(password_by_user) - found)
    if missing:
        fail(f"Could not find users in {source_path}: {', '.join(missing)}")


def write_output_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


def build_password_payload(
    *,
    namespace: str,
    realm: str,
    target_users: list[dict[str, str]],
    password_by_user: dict[str, str],
) -> dict[str, Any]:
    return {
        "rotated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "namespace": namespace,
        "realm": realm,
        "users": [
            {
                "username": record["username"],
                "email": record["email"],
                "password": password_by_user[record["username"]],
            }
            for record in target_users
        ],
    }


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
            "Missing environment variables required to render the Kubernetes realm file: "
            + ", ".join(sorted(missing))
        )
    return rendered


def run_command(
    command: list[str], *, input_text: str | None = None, capture_output: bool = True
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            command,
            input=input_text,
            text=True,
            capture_output=capture_output,
            check=False,
        )
    except FileNotFoundError as exc:
        fail(f"Missing required command: {exc.filename}")
    if result.returncode != 0:
        stderr = result.stderr.strip()
        stdout = result.stdout.strip()
        details = stderr or stdout or "(no command output)"
        fail(f"Command failed: {' '.join(command)}\n{details}")
    return result


def ensure_command_available(command_name: str) -> None:
    if shutil.which(command_name) is None:
        fail(f"Missing required command: {command_name}")


def resolve_namespace(args: argparse.Namespace, env: dict[str, str]) -> str:
    namespace = args.namespace or env.get("NAMESPACE")
    if not namespace:
        fail("Missing namespace. Set NAMESPACE in .env or pass --namespace.")
    return namespace


def resolve_realm(args: argparse.Namespace, env: dict[str, str]) -> str:
    realm = args.realm or env.get("KEYCLOAK_REALM") or "openwebui"
    return realm


def resolve_keycloak_admin(args: argparse.Namespace, env: dict[str, str]) -> str:
    admin = args.keycloak_admin or env.get("KEYCLOAK_ADMIN") or "admin"
    return admin


def get_keycloak_pod(namespace: str, label_selector: str) -> str:
    result = run_command(
        [
            "kubectl",
            "-n",
            namespace,
            "get",
            "pod",
            "-l",
            label_selector,
            "-o",
            "jsonpath={.items[0].metadata.name}",
        ]
    )
    pod_name = result.stdout.strip()
    if not pod_name:
        fail(f"No Keycloak pod found with label selector '{label_selector}'.")
    return pod_name


def get_secret_value(namespace: str, secret_name: str, secret_key: str) -> str:
    result = run_command(
        [
            "kubectl",
            "-n",
            namespace,
            "get",
            "secret",
            secret_name,
            "-o",
            f"jsonpath={{.data.{secret_key}}}",
        ]
    )
    encoded = result.stdout.strip()
    if not encoded:
        fail(f"Secret {secret_name}/{secret_key} is empty or missing.")
    try:
        return base64.b64decode(encoded).decode("utf-8")
    except Exception as exc:  # noqa: BLE001
        fail(f"Failed to decode {secret_name}/{secret_key}: {exc}")


def kcadm_exec(namespace: str, pod_name: str, *args: str) -> None:
    run_command(
        [
            "kubectl",
            "-n",
            namespace,
            "exec",
            pod_name,
            "--",
            "env",
            "KCADM_CONFIG=/tmp/keycloak-password-rotation.kcadm",
            "/opt/keycloak/bin/kcadm.sh",
            *args,
        ]
    )


def rotate_live_passwords(
    namespace: str,
    pod_name: str,
    admin_user: str,
    admin_password: str,
    realm: str,
    password_by_user: dict[str, str],
) -> None:
    kcadm_exec(
        namespace,
        pod_name,
        "config",
        "credentials",
        "--server",
        "http://127.0.0.1:8080",
        "--realm",
        "master",
        "--user",
        admin_user,
        "--password",
        admin_password,
    )
    for username in sorted(password_by_user):
        kcadm_exec(
            namespace,
            pod_name,
            "set-password",
            "-r",
            realm,
            "--username",
            username,
            "--new-password",
            password_by_user[username],
        )


def cleanup_kcadm(namespace: str, pod_name: str) -> None:
    subprocess.run(
        [
            "kubectl",
            "-n",
            namespace,
            "exec",
            pod_name,
            "--",
            "rm",
            "-f",
            "/tmp/keycloak-password-rotation.kcadm",
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def apply_configmap(
    namespace: str,
    configmap_name: str,
    rendered_realm_path: Path,
) -> None:
    configmap_yaml = run_command(
        [
            "kubectl",
            "-n",
            namespace,
            "create",
            "configmap",
            configmap_name,
            f"--from-file=realm-openwebui.json={rendered_realm_path}",
            "--dry-run=client",
            "-o",
            "yaml",
        ]
    ).stdout
    run_command(["kubectl", "apply", "-f", "-"], input_text=configmap_yaml)


def rollout_restart(namespace: str, deployment: str) -> None:
    run_command(["kubectl", "-n", namespace, "rollout", "restart", f"deployment/{deployment}"])
    run_command(
        [
            "kubectl",
            "-n",
            namespace,
            "rollout",
            "status",
            f"deployment/{deployment}",
            "--timeout=240s",
        ]
    )


def find_kubernetes_source_file(source_files: list[Path]) -> Path:
    for path in source_files:
        if path.name.endswith(".k8s.json"):
            return path
    return source_files[0]


def main() -> None:
    args = parse_args()
    ensure_minimum_length(args.length)

    env_path = Path(args.env_file).expanduser().resolve()
    env = merged_env(env_path)
    source_files = resolve_source_files(args)
    password_store_path = Path(args.password_store).expanduser().resolve()

    if args.skip_configmap and not args.skip_restart:
        fail("--skip-configmap cannot be used without --skip-restart.")

    primary_realm = load_realm(source_files[0])
    target_users = select_user_records(collect_users(primary_realm), args.users)

    password_by_user = {
        record["username"]: generate_password(args.length) for record in target_users
    }

    needs_cluster = not args.skip_configmap or not args.skip_live or not args.skip_restart
    namespace = args.namespace or env.get("NAMESPACE", "")
    realm = args.realm or env.get("KEYCLOAK_REALM", "openwebui")
    admin_user = ""
    pod_name: str | None = None
    admin_password: str | None = None
    k8s_source_file = find_kubernetes_source_file(source_files)

    if needs_cluster:
        ensure_command_available("kubectl")
        namespace = resolve_namespace(args, env)
        realm = resolve_realm(args, env)
        if not args.skip_configmap:
            render_template(k8s_source_file.read_text(encoding="utf-8"), env)
        if not args.skip_live:
            admin_user = resolve_keycloak_admin(args, env)
            pod_name = get_keycloak_pod(namespace, args.keycloak_label)
            admin_password = get_secret_value(namespace, args.secret_name, args.secret_key)

    output_payload = build_password_payload(
        namespace=namespace,
        realm=realm,
        target_users=target_users,
        password_by_user=password_by_user,
    )

    if args.dry_run:
        print(json.dumps(output_payload, indent=2))
        return

    write_output_file(password_store_path, output_payload)
    print(
        "Updated local password store: "
        + (
            str(password_store_path.relative_to(ROOT_DIR))
            if password_store_path.is_relative_to(ROOT_DIR)
            else str(password_store_path)
        )
    )

    if args.output:
        output_path = Path(args.output).expanduser().resolve()
        if output_path != password_store_path:
            write_output_file(output_path, output_payload)
        print(f"Wrote generated passwords to {output_path}")

    rendered_path: Path | None = None
    if not args.skip_configmap:
        rendered_realm = render_template(k8s_source_file.read_text(encoding="utf-8"), env)
        rendered_realm_data = json.loads(rendered_realm)
        update_realm_users(rendered_realm_data, password_by_user, k8s_source_file)
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            prefix="keycloak-realm-",
            delete=False,
            encoding="utf-8",
        ) as handle:
            handle.write(json.dumps(rendered_realm_data, indent=2) + "\n")
            rendered_path = Path(handle.name)

        try:
            apply_configmap(namespace, args.configmap_name, rendered_path)
            print(f"Applied ConfigMap {args.configmap_name} in namespace {namespace}")
        finally:
            if rendered_path.exists():
                rendered_path.unlink()

    if not args.skip_live:
        if pod_name is None:
            fail("Missing Keycloak pod name.")
        if admin_password is None:
            fail("Missing Keycloak admin password.")
        try:
            rotate_live_passwords(
                namespace=namespace,
                pod_name=pod_name,
                admin_user=admin_user,
                admin_password=admin_password,
                realm=realm,
                password_by_user=password_by_user,
            )
            print(f"Rotated {len(password_by_user)} live Keycloak passwords in realm {realm}")
        finally:
            cleanup_kcadm(namespace, pod_name)

    if not args.skip_restart:
        rollout_restart(namespace, args.deployment)
        print(f"Restarted deployment/{args.deployment} in namespace {namespace}")


if __name__ == "__main__":
    main()
