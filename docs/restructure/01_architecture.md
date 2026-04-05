# Architecture : restructuration de l'écosystème mychat.fake-domain

## Vue d'ensemble

Le monorepo `grafrag-experimentation` est découpé en :
- **`experimentation-owui`** — socle commun (OpenWebUI + Keycloak + Pipelines)
- **Feature repos** — 1 repo par fonctionnalité, intégré via `owui-plugin.yaml`

Déploiement : Docker Compose (dev local) + Kubernetes sur Scaleway (prod).

## Services du socle

| Service | Image | Port | Requis | Ingress K8s |
|---------|-------|------|--------|-------------|
| openwebui | `ghcr.io/open-webui/open-webui:v0.8.10` | 3000 | requis | `${OPENWEBUI_HOST}` |
| keycloak | `quay.io/keycloak/keycloak:24.0` | 8082 | requis | `${KEYCLOAK_HOST}` |
| pipelines | `ghcr.io/open-webui/pipelines:main` | 9099 | requis | - |
| searxng | `docker.io/searxng/searxng:latest` | 8083 | optionnel | `${SEARXNG_HOST}` |
| search-valkey | `docker.io/valkey/valkey:8-alpine` | - | optionnel | - |

## Namespaces K8s (stratégie : hybrid)

Socle : `owui-socle`

| Feature repo | Namespace | Mode |
|-------------|-----------|------|
| grafrag-experimentation | `grafrag` | dédié |
| anef-knowledge-assistant | `anef` | dédié |
| tchap-reader | `owui-socle` | colocalisé socle |
| browser-skill-owui | `browser-use` | dédié |

## Contrat d'intégration : `owui-plugin.yaml`

Chaque feature repo déclare à sa racine un fichier `owui-plugin.yaml`.
C'est le seul point de contact avec le socle — le feature repo est autonome.

```yaml
name: mon-feature
version: "1.0.0"

services:                    # Containers propres au feature
  - name: mon-service
    port: 8086

pipelines:                   # Fichiers .py montés dans le container pipelines du socle
  files:
    - pipelines/mon_pipeline.py
  requirements: requirements-pipeline.txt   # optionnel

tools:                       # Code .py injecté dans Open WebUI via API
  entries:
    - id: mon_tool
      source_file: app/openwebui_tool.py
      service_name: mon-service
      service_port: 8086
      url_replacements:
        "http://host.docker.internal:8086": "http://{{service}}:{{port}}"

model_tools:                 # Associations modèle → tools + system prompt
  - models: ["scaleway-general.*"]
    tool_ids: [mon_tool]
    system: "System prompt optionnel."

env_vars: []                 # Variables d'env spécifiques

k8s:
  namespace: mon-namespace
  custom_image: true
```

**Principes :**
- Ajouter un tool = modifier `owui-plugin.yaml` dans son feature repo. C'est tout.
- Le socle scanne les plugins depuis une source de découverte explicite et déterministe. Aucun scan implicite "magique" du filesystem.
- Le socle agrège, enregistre, et ne demande pas de modifier manuellement ses manifests à chaque nouveau tool.
- Chaque étape est idempotente.

## Docker Compose (dev local)

```
experimentation-owui/
  docker-compose.yml          # Services socle (owui, keycloak, pipelines, searxng)
                              # Réseau 'owui-net' (external)
                              # Stockage persistant pour OpenWebUI / agent conversationnel
                              # Service register-watcher (profil dev) pour hot-reload

feature-repo/
  docker-compose.yml          # Services feature uniquement
                              # networks: owui-net (external)
  owui-plugin.yaml            # Contrat
```

**Réseau** : `owui-net` créé par le socle, rejoint par les features.
**Pipelines** : bind mount des fichiers déclarés dans `owui-plugin.yaml`.
**Tools** : `register-watcher` surveille les `owui-plugin.yaml` et enregistre via l'API OWUI.

## Persistance

- OpenWebUI / agent conversationnel reste stateful et ne doit pas perdre ses conversations, métadonnées ou état utile après redémarrage.
- En Docker : bind mount ou volume nommé persistant pour les données OpenWebUI.
- En K8s : PVC ou backend persistant équivalent.
- Un volume partagé entre services n'est acceptable que s'il est réellement nécessaire et justifié ; sinon préférer des frontières de stockage claires.

## Kubernetes sur Scaleway

**Cluster :**
- Registry : `rg.fr-par.scw.cloud/funcscwnspricelessmontalcinhiacgnzi`
- LLM API : `https://api.scaleway.ai/<PROJECT_ID>/v1`
- Modèle : `mistral-small-3.2-24b-instruct-2506`
- Ingress : NGINX + cert-manager (`letsencrypt-prod`)

**Déploiement :**
```
make deploy-socle             # Namespace owui-socle, services socle
make deploy-plugin REPO=path  # Lit owui-plugin.yaml, build/push image, apply K8s
make deploy                   # Socle + tous les plugins découverts
make register                 # Enregistre tools + pipelines + model_tools dans OWUI
```

Pendant la transition, `deploy/deploy-k8s.sh` reste une entrée valide. Il peut devenir un wrapper vers la nouvelle orchestration, mais ne doit pas casser les usages existants.

**Secrets :**
- `owui-socle-secrets` — SCW API keys, Keycloak admin, OWUI secret
- `owui-registry` — imagePullSecrets (répliqué dans chaque namespace)
- `<feature>-secrets` — secrets spécifiques par feature

**Pipelines en K8s :** ConfigMap agrégée depuis tous les `owui-plugin.yaml`.
Le script `render_pipelines_configmap.py` scanne les plugins et génère la ConfigMap.

**Tools en K8s :** CronJob `register-plugins` (toutes les 2min) qui :
1. Lit les `owui-plugin.yaml` depuis les ConfigMaps/volumes
2. Compare avec l'état actuel via `GET /api/v1/tools`
3. Applique les diffs via `PUT /api/v1/tools/{id}`

## Hot-reload (montage dynamique)

| Composant | Docker (dev) | K8s (prod) |
|-----------|-------------|------------|
| Pipelines | watchdog sur bind mount → `importlib.reload()` | ConfigMap update + `kubectl rollout restart` |
| Tools | `register-watcher` service (inotify → API OWUI) | CronJob `register-plugins` toutes les 2min |
| Model-tools | même service que tools | même CronJob |

**Docker** : le service `register-watcher` tourne en continu, surveille les
`owui-plugin.yaml` et source files, met à jour OWUI en temps réel.
Un wrapper watchdog dans le container pipelines recharge les modules modifiés.

**K8s** : on privilégie la simplicité. Pas de sidecar complexe.
- Pipelines : mise à jour ConfigMap + `rollout restart` (30s de downtime acceptable)
- Tools : CronJob toutes les 2min, diff-only, idempotent

## Discipline d'exécution Git et tests

À chaque phase de migration :

1. Identifier les tests existants pertinents.
2. Créer les tests minimaux manquants avant la modification si la couverture ne protège pas suffisamment la régression visée.
3. Exécuter les tests avant la phase pour établir une baseline.
4. Faire un commit de checkpoint avant de modifier le code.
5. Réaliser la phase.
6. Exécuter les tests après la phase, y compris les nouveaux tests ajoutés.
7. Faire un commit de fin de phase après validation.

## Structure du socle

```
experimentation-owui/
├── docker-compose.yml
├── .env.example
├── Makefile
├── owui-plugin.schema.yaml     # Schéma de validation du contrat
├── openwebui/                  # Config + data OWUI persistantes
├── keycloak/                   # Realm configs
├── search/                     # SearXNG config
├── tests/                      # Tests smoke / intégration / régression du socle
├── scripts/
│   ├── register_plugins.py     # Scan + register tools/pipelines/model_tools
│   ├── discover_plugins.sh     # Découverte des repos frères
│   ├── render_pipelines_configmap.py
│   ├── render_keycloak_realm.py
│   ├── rotate_keycloak_passwords.py
│   ├── provision_openwebui_model_aliases.py
│   └── pipelines_watcher.py    # Hot-reload wrapper (dev)
├── deploy/
│   ├── deploy-k8s.sh           # Déploiement socle K8s
│   ├── deploy-plugins.sh       # Déploiement plugins K8s
│   ├── prepare-k8s-env.sh
│   ├── prepare-k8s-secrets.sh
│   └── prepare-registry-secrets.sh
└── k8s/
    ├── base/                   # Templates Kustomize
    └── rendered/               # Gitignored
```

## Structure d'un feature repo

```
mon-feature/
├── owui-plugin.yaml            # Contrat (seul fichier requis par le socle)
├── docker-compose.yml          # Services feature, réseau owui-net
├── .env.example
├── app/                        # Code applicatif
├── pipelines/                  # Fichiers pipeline (si applicable)
├── tests/                      # Tests ciblés du feature
├── deploy/
│   ├── deploy-k8s.sh           # Déploiement autonome ou via socle
│   └── build-push.sh
└── k8s/
    └── base/                   # Manifests Kustomize du feature
```

## Fonctionnalités supplémentaires
_(aucune)_

## Notes
_(aucune)_
