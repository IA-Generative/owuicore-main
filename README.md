# experimentation-owui — Socle Miraiku

Socle OpenWebUI pour l'écosystème Miraiku. Fournit l'infrastructure partagée
(OpenWebUI, Keycloak, Pipelines, SearXNG) sur laquelle se branchent les
feature repos via le contrat `owui-plugin.yaml`.

## Démarrage rapide

```bash
# 1. Configurer
cp .env.example .env
cp search/local/settings.yml.example search/local/settings.yml
# Éditer .env : remplir les secrets (SCW_SECRET_KEY_LLM, KEYCLOAK_ADMIN_PASSWORD, etc.)
# Éditer search/local/settings.yml : ajouter la clé API Brave si disponible

# 2. Lancer le socle
make up-socle              # OpenWebUI + Keycloak + Pipelines
# ou
make up-socle-full         # + SearXNG + Valkey (recherche web)
# ou
make up-images             # + génération d'images HuggingFace
# ou
make up-dev                # + register-watcher (hot-reload tools)

# 3. Les tools sont enregistrés automatiquement au démarrage
# Le service ensure-tools s'exécute après le healthcheck d'OpenWebUI
# et injecte tous les tools depuis les owui-plugin.yaml des repos frères

# 4. Accéder
# OpenWebUI : http://localhost:3000
# Keycloak  : http://localhost:8082
# SearXNG   : http://localhost:8083 (si profil search)
```

## Architecture

```
experimentation-owui/          ← ce repo (socle)
├── docker-compose.yml         Services socle + profils (search, image-gen, dev)
├── .env / .env.example        Configuration et secrets
├── Makefile                   Commandes (up, down, register, deploy, etc.)
├── owui-plugin.schema.yaml    Schéma de validation du contrat plugin
│
├── openwebui/                 Custom UI (CSS)
├── keycloak/                  Realm configs
├── search/local/              SearXNG settings (gitignored, contient API key Brave)
├── pipelines/                 Mount point pour les pipelines feature
├── image-gen/                 Proxy HuggingFace → OpenAI image gen
│
├── scripts/
│   ├── ensure_tools.py        ★ Auto-registration tools + MCP au démarrage
│   ├── register_plugins.py    Registration via API REST OWUI
│   ├── discover_plugins.sh    Découverte des repos frères
│   ├── register_watcher.py    Hot-reload dev (poll + register)
│   └── ...                    Keycloak, pipelines, smoke tests
│
├── deploy/
│   ├── deploy-k8s.sh          Déploiement socle K8s
│   ├── deploy-plugins.sh      Déploiement plugins K8s
│   └── prepare-*.sh           Secrets, registry, env K8s
│
├── k8s/base/                  Manifests Kustomize (namespace owui-socle/miraiku)
│
└── .github/workflows/         CI (lint + smoke test) + CD (deploy K8s)
```

## Services

### Socle (toujours lancés)

| Service | Image | Port | Rôle |
|---------|-------|------|------|
| **openwebui** | `ghcr.io/open-webui/open-webui:v0.8.12` | 3000 | Interface chat + admin |
| **keycloak** | `quay.io/keycloak/keycloak:24.0` | 8082 | SSO / OIDC |
| **pipelines** | `ghcr.io/open-webui/pipelines:main` | 9099 | Pipelines LLM custom |

### Profils optionnels

| Profil | Services | Commande |
|--------|----------|----------|
| `search` | SearXNG + Valkey | `make up-socle-full` |
| `image-gen` | image-gen (HuggingFace) | `make up-images` |
| `dev` | register-watcher (hot-reload) | `make up-dev` |

### Service ensure-tools (automatique)

Le service `ensure-tools` s'exécute automatiquement après chaque démarrage d'OpenWebUI.
Il scanne les `owui-plugin.yaml` des repos frères et injecte les tools dans la DB OWUI.

**Fonctionnement :**
1. Attend que le healthcheck OpenWebUI passe
2. Lit `PLUGIN_PATHS` (ou scanne les répertoires frères)
3. Pour chaque `owui-plugin.yaml` trouvé, injecte les tools en DB (`INSERT OR REPLACE`)
4. Vérifie que les MCP servers sont configurés (data.gouv.fr)

**Idempotent** : peut être relancé à tout moment sans effet de bord.

```bash
# Relancer manuellement
make ensure-tools

# Ou via docker
docker compose up ensure-tools
```

## Contrat d'intégration : owui-plugin.yaml

Chaque feature repo déclare un `owui-plugin.yaml` à sa racine :

```yaml
name: mon-feature
version: "1.0.0"

services:
  - name: mon-service
    port: 8086

pipelines:
  files:
    - pipelines/mon_pipeline.py

tools:
  entries:
    - id: mon_tool
      source_file: app/openwebui_tool.py
      service_name: mon-service
      service_port: 8086

model_tools: []
env_vars: []

k8s:
  namespace: miraiku
  custom_image: true
```

## Feature repos connectés

| Repo | Services | Tools | Namespace K8s |
|------|----------|-------|---------------|
| **grafrag-experimentation** | bridge, corpus-*, drive | — | miraiku |
| **tchap-reader** | tchap-reader:8087 | tchap_reader (5), tchap_admin (3) | miraiku |
| **browser-skill-owui** | browser-use:8000 | browser_use (3), vision_filter (2) | miraiku |
| **anef-knowledge-assistant** | anef-api:8000 | — (pipeline) | miraiku |
| **data-query-owui** *(à venir)* | data-query:8093 | data_query, data_preview, data_schema | miraiku |

## MCP Servers

| Serveur | URL | Status |
|---------|-----|--------|
| **data.gouv.fr** | `https://mcp.data.gouv.fr/mcp` | Fonctionnel (auto-configuré) |

Les MCP servers sont configurés automatiquement par `ensure-tools` au démarrage.

## Moteurs de recherche (SearXNG)

| Moteur | Poids | Type |
|--------|-------|------|
| Qwant | 1.6 | Built-in (primaire) |
| Brave API | 1.5 | API key (pas de rate limit) |
| Startpage | 1.4 | Built-in |
| Mojeek | 1.1 | Built-in |
| DuckDuckGo | 1.0 | Built-in |
| Wikipedia | 0.8 | Built-in |
| Bing | 0.7 | Built-in |
| Google | 0.6 | Built-in |

Configuration dans `search/local/settings.yml` (gitignored car contient la clé API Brave).
Template dans `search/local/settings.yml.example`.

## Génération d'images

Proxy FastAPI (`image-gen/`) qui traduit l'API OpenAI `/v1/images/generations`
vers HuggingFace Inference API.

| Modèle | Alias | Vitesse |
|--------|-------|---------|
| FLUX.1-schnell | `flux-schnell` | ~5s |
| SDXL | `sdxl` | ~10s |

Activation : `make up-images` ou profil `image-gen`.
Configuration : `HF_TOKEN` et `HF_IMAGE_MODEL` dans `.env`.

## Déploiement K8s (Scaleway)

```bash
# Déployer le socle
make deploy-socle

# Déployer les plugins
make deploy-plugins

# Déployer tout
make deploy

# Enregistrer les tools après déploiement
# (automatique via Job ensure-tools, ou manuellement)
make ensure-tools
```

**Namespace** : `miraiku` (ex-`grafrag`)
**Registry** : `rg.fr-par.scw.cloud/funcscwnspricelessmontalcinhiacgnzi`
**Cluster** : `k8s-par-brave-bassi`

### Build pour K8s (images AMD64)

```bash
# Depuis un Mac ARM, toujours builder en AMD64
docker buildx build --platform linux/amd64 --push \
  -t rg.fr-par.scw.cloud/funcscwnspricelessmontalcinhiacgnzi/mon-image:tag .
```

## Commandes Makefile

| Commande | Description |
|----------|-------------|
| `make help` | Liste toutes les commandes |
| `make up-socle` | Lancer le socle (OWUI + Keycloak + Pipelines) |
| `make up-socle-full` | + SearXNG + Valkey |
| `make up-images` | + génération d'images HuggingFace |
| `make up-dev` | + register-watcher (hot-reload) |
| `make down` | Arrêter tout |
| `make logs` | Suivre les logs |
| `make ps` | Lister les services |
| `make ensure-tools` | Enregistrer tools + MCP dans OWUI |
| `make register` | Registration via API REST OWUI |
| `make discover` | Lister les plugins découverts |
| `make smoke-test` | Tests de fumée |
| `make deploy` | Déployer socle + plugins sur K8s |

## Persistance

| Composant | Docker | K8s |
|-----------|--------|-----|
| OpenWebUI (conversations, users, tools) | Volume `owui-socle-openwebui-data` | PVC |
| Keycloak | Import realm au boot | PVC |
| SearXNG | Stateless (cache Valkey) | Stateless |
| Tools OWUI | Auto-registrés via `ensure-tools` | Auto-registrés via Job |
| MCP servers | Auto-configurés via `ensure-tools` | Auto-configurés via Job |

## Documentation

- [Comparaison Tools OWUI vs MCP vs A2A](../grafrag-experimentation/docs/comparaison-tools-owui-vs-mcp.md)
- [Synthèse d'apprentissage](../grafrag-experimentation/docs/synthese-apprentissage-miraiku.md)
- [Prompt build data-query](../grafrag-experimentation/prompts/build-data-query-tool.md)
- [Prompt deploy data-query](../grafrag-experimentation/prompts/deploy-data-query.md)

## Pièges connus

- **PersistentConfig OWUI** : les env vars sont ignorées après le premier boot si la DB a déjà une valeur. Utiliser l'API admin ou `ensure-tools`.
- **Custom index.html** : ne pas monter de `index.html` custom (casse après upgrade OWUI).
- **ARM vs AMD64** : toujours `--platform linux/amd64` pour Scaleway.
- **PVC RWO K8s** : scale à 0 avant de changer l'image, puis scale à 1.
- **Nommage services K8s** : ne pas nommer un service comme une env var K8s connue (ex: `searxng` → collision avec `SEARXNG_PORT`).
- **MCP DNS rebinding** : les serveurs MCP internes nécessitent de désactiver la DNS rebinding protection.
