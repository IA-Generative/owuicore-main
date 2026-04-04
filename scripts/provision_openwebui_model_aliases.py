from __future__ import annotations

import argparse
import json
import sqlite3
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT / "openwebui" / "data" / "webui.db"
DEFAULT_ENV_PATH = ROOT / ".env"
DEFAULT_ICON_FILENAME = "mirai-model-avatar-128.png"

MODEL_OVERRIDES = (
    {
        "id": "graphrag-bridge.graphrag-local",
        "name": "MirAI GraphRAG Local",
        "description": "Exploration ciblee du corpus GraphRAG.",
        "tags": ["MirAI", "GraphRAG"],
    },
    {
        "id": "graphrag-bridge.graphrag-global",
        "name": "MirAI GraphRAG Global",
        "description": "Synthese globale et transversale du corpus GraphRAG.",
        "tags": ["MirAI", "GraphRAG"],
    },
    {
        "id": "scaleway-general.gpt-oss-120b",
        "name": "MirAI Chat GPT-OSS 120B",
        "description": "Modele generaliste puissant pour raisonnement et taches complexes.",
        "tags": ["MirAI", "Scaleway", "General"],
    },
    {
        "id": "scaleway-general.llama-3.3-70b-instruct",
        "name": "MirAI Chat Llama 3.3 70B",
        "description": "Generaliste multilingue robuste pour conversation et analyse.",
        "tags": ["MirAI", "Scaleway", "General"],
    },
    {
        "id": "scaleway-general.mistral-small-3.2-24b-instruct-2506",
        "name": "MirAI Chat Mistral Small 3.2",
        "description": "Bon equilibre latence/qualite pour usage quotidien.",
        "tags": ["MirAI", "Scaleway", "General"],
    },
    {
        "id": "scaleway-general.qwen3-235b-a22b-instruct-2507",
        "name": "MirAI Chat Qwen3 235B",
        "description": "Grand contexte et bonnes performances generalistes multilingues.",
        "tags": ["MirAI", "Scaleway", "General"],
    },
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Deprovisionne puis reprovisionne les overrides de modeles Open WebUI "
            "pour GraphRAG avec une image issue de la mascotte."
        )
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"Chemin vers webui.db (defaut: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=DEFAULT_ENV_PATH,
        help=f"Fichier .env a lire pour BRIDGE_PUBLIC_URL (defaut: {DEFAULT_ENV_PATH})",
    )
    parser.add_argument(
        "--bridge-public-url",
        default=None,
        help="URL publique du bridge exposee au navigateur.",
    )
    parser.add_argument(
        "--icon-filename",
        default=DEFAULT_ICON_FILENAME,
        help=(
            "Nom du fichier d'icone dans bridge/assets "
            f"(defaut: {DEFAULT_ICON_FILENAME})"
        ),
    )
    parser.add_argument(
        "--owner-email",
        default=None,
        help="Email du proprietaire a utiliser. Sinon le premier admin est choisi.",
    )
    parser.add_argument(
        "--deprovision-only",
        action="store_true",
        help="Supprime les overrides cibles sans les recreer.",
    )
    return parser.parse_args()


def read_env_value(env_path: Path, key: str) -> str | None:
    if not env_path.exists():
        return None

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        env_key, value = line.split("=", 1)
        if env_key.strip() != key:
            continue
        cleaned = value.strip().strip("'").strip('"')
        return cleaned or None
    return None


def resolve_bridge_public_url(args: argparse.Namespace) -> str:
    if args.bridge_public_url:
        return args.bridge_public_url.rstrip("/")

    from_env = read_env_value(args.env_file, "BRIDGE_PUBLIC_URL")
    if from_env:
        return from_env.rstrip("/")

    return "http://localhost:8081"


def resolve_owner_user_id(conn: sqlite3.Connection, owner_email: str | None) -> str:
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if owner_email:
        row = cursor.execute(
            "SELECT id FROM user WHERE email = ? ORDER BY created_at LIMIT 1",
            (owner_email,),
        ).fetchone()
        if row:
            return str(row["id"])
        raise SystemExit(f"No Open WebUI user found for email: {owner_email}")

    row = cursor.execute(
        "SELECT id FROM user WHERE role = 'admin' ORDER BY created_at LIMIT 1"
    ).fetchone()
    if row:
        return str(row["id"])

    row = cursor.execute("SELECT id FROM user ORDER BY created_at LIMIT 1").fetchone()
    if row:
        return str(row["id"])

    raise SystemExit("No Open WebUI user found in webui.db.")


def collect_target_ids() -> tuple[list[str], list[str]]:
    override_ids = [model["id"] for model in MODEL_OVERRIDES]
    legacy_alias_ids = [
        "mirai-graphrag-local",
        "mirai-graphrag-global",
        "graphrag-local-alias",
        "graphrag-global-alias",
        "mirai-chat-gptoss",
        "mirai-chat-llama",
        "mirai-chat-mistral",
        "mirai-chat-qwen",
    ]
    return override_ids, legacy_alias_ids


def deprovision(conn: sqlite3.Connection) -> list[str]:
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    override_ids, legacy_alias_ids = collect_target_ids()
    resource_ids = override_ids + legacy_alias_ids

    rows = cursor.execute(
        """
        SELECT id
        FROM model
        WHERE id IN ({placeholders})
           OR base_model_id IN ({placeholders})
        """.format(placeholders=",".join("?" * len(resource_ids))),
        resource_ids + resource_ids,
    ).fetchall()

    removed_ids = [str(row["id"]) for row in rows]
    if not removed_ids:
        return []

    cursor.execute(
        "DELETE FROM access_grant WHERE resource_type = 'model' AND resource_id IN ({})".format(
            ",".join("?" * len(removed_ids))
        ),
        removed_ids,
    )
    cursor.execute(
        "DELETE FROM model WHERE id IN ({})".format(",".join("?" * len(removed_ids))),
        removed_ids,
    )
    conn.commit()
    return removed_ids


def provision(
    conn: sqlite3.Connection,
    owner_user_id: str,
    bridge_public_url: str,
    icon_filename: str,
) -> list[str]:
    cursor = conn.cursor()
    now = int(time.time())
    icon_url = f"{bridge_public_url}/assets/{icon_filename}"

    provisioned = []
    for model in MODEL_OVERRIDES:
        meta = {
            "profile_image_url": icon_url,
            "description": model["description"],
            "tags": [{"name": tag} for tag in model.get("tags", ["MirAI"])],
        }
        params = {}

        # Preserve existing toolIds, capabilities, and system prompt if present
        existing = cursor.execute(
            "SELECT meta, params FROM model WHERE id = ?", (model["id"],)
        ).fetchone()
        if existing:
            try:
                old_meta = json.loads(existing[0]) if existing[0] else {}
                if "toolIds" in old_meta:
                    meta["toolIds"] = old_meta["toolIds"]
                if "capabilities" in old_meta:
                    meta["capabilities"] = old_meta["capabilities"]
            except (json.JSONDecodeError, TypeError):
                pass
            try:
                old_params = json.loads(existing[1]) if existing[1] else {}
                if "system" in old_params:
                    params["system"] = old_params["system"]
            except (json.JSONDecodeError, TypeError):
                pass

        cursor.execute(
            """
            INSERT OR REPLACE INTO model (
                id, user_id, base_model_id, name, meta, params, created_at, updated_at, is_active
            ) VALUES (?, ?, NULL, ?, ?, ?, ?, ?, 1)
            """,
            (
                model["id"],
                owner_user_id,
                model["name"],
                json.dumps(meta, ensure_ascii=False),
                json.dumps(params, ensure_ascii=False),
                now,
                now,
            ),
        )
        provisioned.append(model["id"])

    conn.commit()
    return provisioned


def main() -> None:
    args = parse_args()
    db_path = args.db.resolve()
    if not db_path.exists():
        raise SystemExit(f"Open WebUI database not found: {db_path}")

    bridge_public_url = resolve_bridge_public_url(args)
    icon_path = ROOT / "bridge" / "assets" / args.icon_filename
    if not icon_path.exists():
        raise SystemExit(f"Model icon asset not found: {icon_path}")

    conn = sqlite3.connect(db_path)
    try:
        owner_user_id = resolve_owner_user_id(conn, args.owner_email)
        removed_ids = deprovision(conn)
        if args.deprovision_only:
            print(
                json.dumps(
                    {
                        "db": str(db_path),
                        "removed_model_ids": removed_ids,
                        "provisioned_model_ids": [],
                    },
                    indent=2,
                    ensure_ascii=True,
                )
            )
            return

        provisioned_ids = provision(conn, owner_user_id, bridge_public_url, args.icon_filename)
        print(
            json.dumps(
                {
                    "db": str(db_path),
                    "owner_user_id": owner_user_id,
                    "bridge_public_url": bridge_public_url,
                    "icon_url": f"{bridge_public_url}/assets/{args.icon_filename}",
                    "removed_model_ids": removed_ids,
                    "provisioned_model_ids": provisioned_ids,
                },
                indent=2,
                ensure_ascii=True,
            )
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
