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
    connections = config["tool_server"].get("connections", [])

    # Build lookup by URL
    existing_by_url = {c.get("url"): i for i, c in enumerate(connections)}

    for server in servers:
        idx = existing_by_url.get(server["url"])
        if idx is not None:
            # Update existing entry (fix missing id, etc.)
            old = connections[idx]
            if not old.get("id") or old.get("id") != server.get("id"):
                connections[idx] = server
                print(f"  Updated MCP server: {server['name']} (fixed id)")
            else:
                print(f"  Already configured: {server['name']}")
        else:
            connections.append(server)
            print(f"  Added MCP server: {server['name']}")

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


def deploy_pipelines(plugins: list[Path], pipelines_dir: Path) -> int:
    """Copy pipeline files declared in owui-plugin.yaml to the pipelines mount."""
    pipelines_dir.mkdir(parents=True, exist_ok=True)
    total = 0
    for plugin_file in plugins:
        plugin = yaml.safe_load(plugin_file.read_text())
        plugin_dir = plugin_file.parent
        plugin_name = plugin.get("name", plugin_dir.name)
        files = plugin.get("pipelines", {}).get("files", [])
        if not files:
            continue
        for rel_path in files:
            src = plugin_dir / rel_path
            if not src.exists():
                print(f"  SKIP {plugin_name}: {rel_path} not found")
                continue
            dst = pipelines_dir / src.name
            dst.write_text(src.read_text())
            print(f"  Copied: {src.name} ({plugin_name})")
            total += 1
    return total


def ensure_owui_config(db_path: str) -> None:
    """Ensure OpenWebUI config entries for web search, image gen, etc."""
    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT id, data FROM config ORDER BY id DESC LIMIT 1").fetchall()

    if rows:
        config = json.loads(rows[0][1])
    else:
        config = {}

    changed = False

    # --- Web search (SearXNG) ---
    # Disabled as OWUI feature to avoid auto-injection and max_tokens overflow.
    # SearXNG remains available via direct API calls from tools.
    if "web_search" not in config:
        config["web_search"] = {
            "enable": False,
            "engine": "searxng",
            "searxng_query_url": os.environ.get("SEARXNG_QUERY_URL", "http://searxng:8080/search"),
        }
        print("  Configured: web search (disabled as OWUI feature, SearXNG available for tools)")
        changed = True
    else:
        print("  Already configured: web search")

    # --- Image generation ---
    if "image_generation" not in config:
        config["image_generation"] = {
            "enable": True,
            "engine": "openai",
            "openai": {
                "IMAGES_OPENAI_API_BASE_URL": os.environ.get("IMAGES_OPENAI_API_BASE_URL", "http://image-gen:9100/v1"),
                "IMAGES_OPENAI_API_KEY": os.environ.get("HF_TOKEN", ""),
            },
            "model": os.environ.get("HF_IMAGE_MODEL", "black-forest-labs/FLUX.1-schnell"),
        }
        print("  Configured: image generation (HuggingFace proxy)")
        changed = True
    else:
        print("  Already configured: image generation")

    # --- Default model ---
    default_model = os.environ.get("DEFAULT_MODEL", "")
    if default_model and config.get("default_models") != default_model:
        config["default_models"] = default_model
        print(f"  Configured: default model = {default_model}")
        changed = True

    if changed:
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


def make_tools_global(db_path: str) -> None:
    """Set access_control on all tools and filters so every user can use them."""
    public_acl = {"read": {"group_ids": [], "user_ids": []}, "write": {"group_ids": [], "user_ids": []}}
    conn = sqlite3.connect(db_path)

    # Tools
    for row in conn.execute("SELECT id, meta FROM tool").fetchall():
        meta = json.loads(row[1]) if row[1] else {}
        if meta.get("access_control") != public_acl:
            meta["access_control"] = public_acl
            conn.execute("UPDATE tool SET meta = ? WHERE id = ?", (json.dumps(meta), row[0]))
            print(f"  Tool {row[0]}: set global access")

    # Functions (filters)
    for row in conn.execute("SELECT id, meta, is_global FROM function").fetchall():
        meta = json.loads(row[1]) if row[1] else {}
        changed = False
        if meta.get("access_control") != public_acl:
            meta["access_control"] = public_acl
            changed = True
        updates = []
        if changed:
            updates.append(("meta", json.dumps(meta)))
        if not row[2]:  # is_global = 0
            updates.append(("is_global", 1))
        if updates:
            set_clause = ", ".join(f"{k} = ?" for k, _ in updates)
            values = [v for _, v in updates] + [row[0]]
            conn.execute(f"UPDATE function SET {set_clause} WHERE id = ?", values)
            print(f"  Filter {row[0]}: set global access")

    conn.commit()
    conn.close()


SYSTEM_PROMPTS = {
    # --- Pipeline models ---
    "anef-regulatory.assistant": (
        "Tu es un assistant réglementaire spécialisé dans le droit des étrangers en France "
        "(CESEDA, titres de séjour ANEF). Tu réponds exclusivement en français.\n\n"
        "Tes capacités :\n"
        "- Rechercher un titre de séjour par mots-clés\n"
        "- Vérifier l'éligibilité d'un demandeur et lister les pièces justificatives\n"
        "- Expliquer les conditions d'obtention, le fondement légal et les points de vigilance\n"
        "- Générer des fiches réflexe pour les agents\n\n"
        "Règles impératives :\n"
        "- Ne jamais inventer d'article de loi, de condition ou de pièce justificative.\n"
        "- Toujours citer la base légale (article CESEDA) quand disponible.\n"
        "- Signaler clairement quand une vérification humaine est nécessaire.\n"
        "- Distinguer métropole / Mayotte quand le contexte l'exige.\n"
        "- Les liens vers les articles s'ouvrent dans le viewer intégré."
    ),
    "anef-regulatory.legal": (
        "Tu es un assistant juridique spécialisé dans le CESEDA (Code de l'entrée et du séjour "
        "des étrangers et du droit d'asile). Tu réponds exclusivement en français.\n\n"
        "Tes capacités :\n"
        "- Rechercher des articles de loi par mots-clés ou numéro d'article\n"
        "- Expliquer le contenu d'un article en langage clair\n"
        "- Croiser plusieurs articles pour répondre à une question juridique\n\n"
        "Règles impératives :\n"
        "- Ne citer que des articles réellement retournés par la recherche.\n"
        "- Ne jamais inventer de contenu juridique.\n"
        "- Toujours fournir la référence exacte (numéro d'article, section).\n"
        "- Signaler si la réponse nécessite une validation par un juriste."
    ),
    "graphrag-bridge.graphrag-local": (
        "Tu es un assistant de recherche documentaire utilisant GraphRAG (méthode locale). "
        "Tu analyses un corpus de documents structurés sous forme de graphe de connaissances.\n\n"
        "Tes capacités :\n"
        "- Répondre à des questions factuelles à partir du corpus indexé\n"
        "- Citer les sources et documents pertinents\n"
        "- Fournir un lien vers le graphe interactif pour explorer les relations\n\n"
        "Règles :\n"
        "- Base tes réponses uniquement sur les documents du corpus.\n"
        "- Cite toujours tes sources (noms de fichiers, sections).\n"
        "- Si l'information n'est pas dans le corpus, dis-le clairement.\n"
        "- Pour sélectionner un corpus spécifique, utilise la syntaxe [[corpus:id]] devant la question."
    ),
    "graphrag-bridge.graphrag-global": (
        "Tu es un assistant de recherche documentaire utilisant GraphRAG (méthode globale). "
        "Tu synthétises l'ensemble d'un corpus pour produire des analyses de haut niveau.\n\n"
        "Tes capacités :\n"
        "- Produire des synthèses thématiques sur l'ensemble du corpus\n"
        "- Identifier les thèmes dominants, les acteurs clés, les chronologies\n"
        "- Comparer et croiser des informations entre documents\n\n"
        "Règles :\n"
        "- Privilégie les vues d'ensemble et les analyses transversales.\n"
        "- Cite les sources quand tu détailles un point spécifique.\n"
        "- Si l'information n'est pas dans le corpus, dis-le clairement."
    ),
    # --- Scaleway LLM models (general purpose with tool calling) ---
    "__default_llm__": (
        "Tu es MirAI, un assistant intelligent. Reponds dans la langue de l'utilisateur.\n\n"
        "QUAND UTILISER QUEL OUTIL :\n\n"
        "Si l'utilisateur donne une URL :\n"
        "- \"capture\", \"screenshot\", \"voir le site\", \"montre-moi\" → `screenshot(url)`\n"
        "- \"extrais\", \"contenu\", \"lis\", \"resume cette page\" → `websnap(url)`\n"
        "- \"compare\" + plusieurs URLs → `compare_urls(urls)`\n\n"
        "Si l'utilisateur uploade une image → `analyze_image(query)`\n\n"
        "Si l'utilisateur parle de donnees (CSV, Excel, fichier, open data) :\n"
        "- chercher des datasets open data → `data_search(query)` (filtres: organization, tag)\n"
        "- lister les datasets populaires → `data_list_popular(theme)` (themes: transport, sante, emploi, education, environnement, logement)\n"
        "- apercu / premieres lignes → `data_preview(url)`\n"
        "- schema / colonnes / types → `data_schema(url)`\n"
        "- question sur les donnees → `data_query(url, question)`\n"
        "- si l'utilisateur uploade un fichier tabulaire → `data_preview()` (sans url)\n"
        "IMPORTANT : ne passe JAMAIS de parametres vides aux tools. Utilise les mots-cles de l'utilisateur.\n\n"
        "Si l'utilisateur parle de Tchap (messagerie) :\n"
        "- se connecter → `tchap_connect()`\n"
        "- lister les salons → `tchap_rooms()`\n"
        "- chercher un salon → `tchap_search_rooms(query)`\n"
        "- analyser un salon → `tchap_analyze(room_id, question, since_hours)`\n"
        "- administration → `tchap_admin(action, target)` (admins uniquement)\n\n"
        "Donnees ouvertes : utilise `data_search(query)` pour chercher parmi 74 000+ jeux de donnees publics sur data.gouv.fr. Utilise `data_list_popular()` pour voir les datasets les plus consultes.\n\n"
        "Regles :\n"
        "- Appelle un seul outil a la fois, le plus specifique possible.\n"
        "- Ne reponds jamais a la place d'un outil : appelle-le.\n"
        "- Ne fabrique pas d'URL, de salons, ni de messages.\n"
        "- Cite toujours la source (URL) dans ta reponse.\n"
        "- Pour Tchap : pseudonymise les noms (Utilisateur_1, etc.)."
    ),
}

VISION_SYSTEM_PROMPT = (
    "Tu es un assistant multimodal. Quand des images sont présentes dans la conversation :\n\n"
    "1. **Si l'image contient du texte** (imprimé, manuscrit, formulaire, tableau, capture d'écran) :\n"
    "   - Concentre-toi PRIORITAIREMENT sur l'extraction et la retranscription fidèle du texte.\n"
    "   - Reproduis le texte tel quel, en préservant la structure (paragraphes, listes, tableaux).\n"
    "   - Pour l'écriture manuscrite, transcris au mieux et signale les mots incertains avec [illisible] ou [incertain: mot].\n"
    "   - Mentionne brièvement le contexte visuel (ex: « Document scanné, format A4, en-tête ministériel ») "
    "mais ne décris pas l'image en détail.\n\n"
    "2. **Si l'image ne contient pas de texte** (photo, schéma, graphique) :\n"
    "   - Fournis une description détaillée du contenu visuel.\n"
    "   - Pour les graphiques/diagrammes, extrais les données clés et les tendances.\n\n"
    "3. **Règles générales :**\n"
    "   - Réponds TOUJOURS dans la même langue que le message de l'utilisateur.\n"
    "   - Utilise les liens markdown cliquables pour référencer les images, ne les invente pas.\n"
    "   - Si plusieurs images sont présentes, traite-les dans l'ordre."
)


def register_pipeline_models(db_path: str, pipelines_api_url: str, api_key: str) -> None:
    """Fetch pipeline models from the API and register them in the model table with global access and system prompts."""
    import urllib.request

    url = f"{pipelines_api_url}/v1/models"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key}"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
    except Exception as exc:
        print(f"  Could not fetch pipelines models: {exc}")
        return

    public_acl = {"read": {"group_ids": [], "user_ids": []}, "write": {"group_ids": [], "user_ids": []}}
    conn = sqlite3.connect(db_path)
    now = int(time.time())

    for model in data.get("data", []):
        model_id = model["id"]
        model_name = model["name"]
        system_prompt = SYSTEM_PROMPTS.get(model_id, "")
        meta = json.dumps({
            "access_control": public_acl,
            "description": "",
            "capabilities": {},
        })
        params = json.dumps({"system": system_prompt} if system_prompt else {})
        conn.execute(
            """INSERT OR REPLACE INTO model
            (id, user_id, base_model_id, name, meta, params, is_active, created_at, updated_at)
            VALUES (?, '', ?, ?, ?, ?, 1, ?, ?)""",
            (model_id, model_id, model_name, meta, params, now, now),
        )
        print(f"  Model {model_id}: {model_name} (global, prompt={'yes' if system_prompt else 'no'})")

    conn.commit()
    conn.close()


def register_llm_models(db_path: str, llm_api_url: str, api_key: str) -> None:
    """Register Scaleway LLM models with default system prompt and global access."""
    import urllib.request

    url = f"{llm_api_url}/models"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key}"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
    except Exception as exc:
        print(f"  Could not fetch LLM models: {exc}")
        return

    public_acl = {"read": {"group_ids": [], "user_ids": []}, "write": {"group_ids": [], "user_ids": []}}
    conn = sqlite3.connect(db_path)
    now = int(time.time())

    # Skip embedding and audio models
    skip_patterns = ["embedding", "whisper", "bge-"]
    vision_models = ["pixtral"]
    default_prompt = SYSTEM_PROMPTS["__default_llm__"]

    for model in data.get("data", []):
        model_id = model["id"]
        if any(p in model_id.lower() for p in skip_patterns):
            continue

        is_vision = any(v in model_id.lower() for v in vision_models)
        system_prompt = VISION_SYSTEM_PROMPT if is_vision else default_prompt

        # Tool IDs to attach to the model
        tool_ids = ["tchapreader", "tchapreader_admin", "websnap", "dataview"]
        filter_ids = ["vision_image_filter"] if is_vision else []

        meta = json.dumps({
            "access_control": public_acl,
            "description": "Vision LLM" if is_vision else "",
            "capabilities": {"vision": True} if is_vision else {},
            "toolIds": tool_ids,
            "filterIds": filter_ids,
        })
        params = json.dumps({"system": system_prompt})

        # Use pipelines prefix for routing through pipelines service
        conn.execute(
            """INSERT OR REPLACE INTO model
            (id, user_id, base_model_id, name, meta, params, is_active, created_at, updated_at)
            VALUES (?, '', ?, ?, ?, ?, 1, ?, ?)""",
            (model_id, model_id, model_id, meta, params, now, now),
        )
        label = "vision" if is_vision else "chat"
        print(f"  Model {model_id} ({label}, {len(tool_ids)} tools)")

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

    # 2. Deploy pipelines
    print("\n--- Pipelines ---")
    if args.mode == "docker":
        # /pipelines-out is mounted RW from host ./pipelines/
        pipelines_dir = Path("/pipelines-out") if Path("/pipelines-out").exists() else ROOT_DIR / "pipelines"
    else:
        pipelines_dir = Path("/app/pipelines")
    try:
        pipeline_count = deploy_pipelines(plugins, pipelines_dir)
        print(f"Deployed {pipeline_count} pipelines")
    except OSError as e:
        print(f"  SKIP pipelines: {e}")

    # 3. MCP servers
    print("\n--- MCP Servers ---")
    mcp_servers = [
        {
            "id": "data-gouv-fr",
            "url": "https://mcp.data.gouv.fr/mcp",
            "type": "mcp",
            "path": "",
            "name": "Open Data (mcp)",
            "description": "Recherche parmi 74 000+ jeux de données publics (data.gouv.fr)",
            "auth_type": "none",
            "key": "",
            "config": {"enable": True},
        },
    ]
    ensure_mcp_servers(db_path, mcp_servers)

    # 4. Ensure OpenWebUI config (web search, image gen)
    print("\n--- OpenWebUI Config ---")
    ensure_owui_config(db_path)

    # 5. Make all tools and filters globally accessible
    print("\n--- Global Access ---")
    make_tools_global(db_path)

    # 6. Register pipeline models with global access
    print("\n--- Pipeline Models ---")
    pipelines_url = os.environ.get("PIPELINES_URL", "http://pipelines:9099")
    pipelines_key = os.environ.get("PIPELINES_API_KEY", "")
    if pipelines_key:
        register_pipeline_models(db_path, pipelines_url, pipelines_key)
    else:
        print("  SKIP: PIPELINES_API_KEY not set")

    # 7. Register Scaleway LLM models with system prompts and tool bindings
    print("\n--- LLM Models ---")
    llm_url = os.environ.get("SCW_LLM_BASE_URL", "")
    llm_key = os.environ.get("SCW_SECRET_KEY_LLM", "")
    if llm_url and llm_key:
        register_llm_models(db_path, llm_url, llm_key)
    else:
        print("  SKIP: SCW_LLM_BASE_URL or SCW_SECRET_KEY_LLM not set")

    # 8. Patch MCP label in OWUI source (use connection name instead of generic "MCP Tool Server")
    print("\n--- MCP Label Patch ---")
    # The MCP label patch is applied at container startup via:
    # - Docker: entrypoint sed in docker-compose.yml
    # - K8s: lifecycle.postStart in deployment-openwebui.yaml
    # This section patches if running inside the openwebui container directly.
    tools_py_paths = [
        Path("/app/backend/open_webui/routers/tools.py"),
    ]
    for tools_py in tools_py_paths:
        if not tools_py.exists():
            continue
        content = tools_py.read_text()
        old_label = "'name': server.get('info', {}).get('name', 'MCP Tool Server')"
        new_label = "'name': server.get('info', {}).get('name', server.get('name', 'MCP Tool Server'))"
        if old_label in content:
            tools_py.write_text(content.replace(old_label, new_label))
            print(f"  Patched: {tools_py}")
        elif new_label in content:
            print(f"  Already patched: {tools_py}")
        else:
            print(f"  Skip: pattern not found in {tools_py}")

    print("\n=== Done ===")


if __name__ == "__main__":
    main()
