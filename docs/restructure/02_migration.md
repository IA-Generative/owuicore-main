# Plan de migration vers l'architecture experimentation-owui

## Workflow obligatoire pour chaque phase

1. Identifier les tests existants pertinents pour la phase.
2. Créer les tests minimaux manquants avant la modification si nécessaire.
3. Exécuter les tests avant la phase pour établir une baseline.
4. Faire un commit de checkpoint avant d'ouvrir la phase.
5. Réaliser la phase.
6. Exécuter les tests après la phase.
7. Faire un commit de fin de phase après validation.

## Phase 1 — Créer le socle (sans casser l'existant)
1. Créer le repo `experimentation-owui` sur GitHub
2. Extraire de grafrag-experimentation : `openwebui/`, `keycloak/`, `search/`, scripts socle
3. Créer `docker-compose.yml` avec réseau `owui-net`, services socle et stockage persistant pour OpenWebUI / agent conversationnel
4. Créer `k8s/base/` avec manifests socle (namespace `owui-socle`)
5. Écrire `scripts/register_plugins.py` (refonte de `register_all_openwebui_tools.py`)
6. Créer ou adapter les tests socle : boot, OIDC, persistance, enregistrement
7. Valider : `make up-socle` fonctionne en local

## Phase 2 — Transformer grafrag-experimentation en feature repo
1. Créer `owui-plugin.yaml` à la racine
2. Isoler du docker-compose : openwebui, keycloak, pipelines, searxng, valkey sans casser le mode historique pendant la transition
3. Garder : bridge, corpus-manager, corpus-worker, drive
4. Rejoindre le réseau `owui-net` (external)
5. Adapter k8s/ : retirer ou désactiver les manifests socle côté feature sans casser `deploy/deploy-k8s.sh`
6. Créer ou adapter les tests d'intégration feature + socle
7. Valider : socle + grafrag ensemble (local + K8s)

## Phase 3 — Vérifier les autres feature repos
Pour chaque repo (`grafrag-experimentation`, `anef-knowledge-assistant`, `tchap-reader`, `browser-skill-owui`) :
1. Vérifier que `owui-plugin.yaml` existe et est correct
2. Vérifier que le docker-compose ne duplique pas le socle
3. Adapter k8s/ si besoin (namespace, cross-namespace refs)
4. Créer ou adapter les tests pertinents du feature
5. Tester l'intégration

## Phase 4 — Orchestration et hot-reload
1. `scripts/discover_plugins.sh` dans le socle
2. `deploy/deploy-plugins.sh` pour K8s
3. Service `register-watcher` (Docker, profil dev)
4. CronJob `register-plugins` (K8s)
5. Cycle complet : socle up → discover → register → smoke test

## Phase 5 — Secrets et CI/CD
1. Secrets socle : `owui-socle-secrets`, `owui-registry`
2. Secrets feature : `<feature>-secrets` par namespace
3. GitHub Actions : build + push par repo, deploy coordonné, tests avant et après déploiement si pertinent
4. Template cookiecutter pour nouveau feature repo
