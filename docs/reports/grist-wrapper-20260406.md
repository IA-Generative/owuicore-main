# Rapport — Grist Wrapper Tool OWUI

**Date** : 2026-04-06
**Contexte** : Contournement du bug #15 (OWUI v0.8.12 ne pre-charge pas les specs MCP)

---

## Fichiers crees

| Fichier | Repo | Description |
|---|---|---|
| `openwebui/grist_tool.py` | owuitools-gristmcp | Wrapper tool OWUI (5 fonctions, HTMLResponse) |
| `owui-plugin.yaml` | owuitools-gristmcp | Descripteur plugin pour ensure-tools |

## Fichiers modifies

| Fichier | Repo | Modification |
|---|---|---|
| `.env` | owuicore-main | Ajout `../owuitools-gristmcp` dans PLUGIN_PATHS |
| `.env.example` | owuicore-main | Idem + ajout `../owuitools-dataview` manquant |
| `scripts/ensure_tools.py` | owuicore-main | System prompt Grist : MCP -> wrapper tool ; ajout `grist` dans toolIds |
| `docs/cahier-de-tests.md` | owuicore-main | Section 11 : MCP -> wrapper tool, doc_id corriges |

## Fonctions du tool

| Fonction | Description |
|---|---|
| `grist_navigate(org_name, workspace_name, doc_name)` | Navigation : orgs -> workspaces -> docs |
| `grist_read_table(doc_id, table_id, limit)` | Lecture des records d'une table |
| `grist_query(doc_id, sql)` | Requete SQL SELECT |
| `grist_schema(doc_id, table_id)` | Schema : tables d'un doc ou colonnes d'une table |
| `grist_export(doc_id, table_id, format)` | Export CSV |

## Resultats des tests

| Test | Description | Resultat |
|---|---|---|
| T11.1 | `grist_navigate()` → 3 orgs (Personal, SDID, templates) | PASS |
| T11.2 | `grist_navigate(org_name="SDID")` → 1 workspace, 4 docs | PASS |
| T11.3 | `grist_read_table("qXWzdtyGgNh2T64Ti1SQfc", "Epics")` → 54 records | PASS |
| T11.4 | `grist_query("qXWzdtyGgNh2T64Ti1SQfc", "SELECT * FROM Epics LIMIT 5")` → 5 resultats | PASS |
| T11.5 | `grist_export("qXWzdtyGgNh2T64Ti1SQfc", "Epics")` → CSV complet | PASS |

## Deploiement

- Docker : `deploy-plugins-docker.sh` — 4 plugins deployes, tool `grist` enregistre (5 methods)
- Valves configurees en DB (grist_api_url, grist_api_key, timeout)
- OpenWebUI redemarre

## Erreurs rencontrees

Aucune.
