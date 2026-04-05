# Meta-prompt : restructuration de l'écosystème mychat.fake-domain

Tu es un coding assistant. Tu vas exécuter la restructuration d'un écosystème
de microservices autour d'Open WebUI. Ce document est ton brief complet.

## Ce que tu dois faire

Transformer un monorepo (`grafrag-experimentation`) en architecture modulaire :
- **1 repo socle** (`experimentation-owui`) : services partagés (OpenWebUI, Keycloak, Pipelines)
- **N repos features** : chacun autonome, intégré via un contrat `owui-plugin.yaml`

## Contexte technique

### Repo source : `grafrag-experimentation`
- Docker Compose avec 9 services : openwebui, keycloak, pipelines, searxng, valkey, bridge, corpus-manager, corpus-worker, drive
- Déploiement K8s sur Scaleway (namespace `grafrag`, registry `rg.fr-par.scw.cloud`)
- Scripts dans `scripts/` : provisioning OWUI, rotation Keycloak, rendering ConfigMaps
- Scripts dans `deploy/` : build, push, deploy K8s complet
- Les tools OWUI sont déclarés dans `openwebui/tools/manifest.yaml` et injectés via `scripts/register_all_openwebui_tools.py` (accès SQLite direct)
- Les pipelines sont des fichiers .py montés dans un container partagé `ghcr.io/open-webui/pipelines:main`

### Repos features existants (déjà séparés, mais couplés au monorepo)
- `anef-knowledge-assistant` — API FastAPI + pipeline OWUI, namespace K8s propre
- `tchap-reader` — API FastAPI + tools OWUI, actuellement couplé au monorepo ; cible K8s : `owui-socle`
- `browser-skill-owui` — API FastAPI + tool/filter OWUI, namespace `browser-use`

### Ce qui fonctionne aujourd'hui et ne doit PAS casser
- Le flux complet : OpenWebUI → pipeline → microservice → réponse
- L'auth OIDC Keycloak → OpenWebUI
- L'enregistrement des tools dans OWUI (même si le mécanisme change)
- Le déploiement K8s via `deploy/deploy-k8s.sh`
- La recherche web via SearXNG
- La persistance de l'état applicatif d'OpenWebUI / agent conversationnel

## Architecture cible

Lis le fichier `prompts/restructure/01_architecture.md` — c'est la spec.

Points clés :
1. **`owui-plugin.yaml`** est le contrat unique entre feature repo et socle
2. **Réseau Docker `owui-net`** partagé entre socle et features
3. **`scripts/register_plugins.py`** remplace `register_all_openwebui_tools.py` — scanne les `owui-plugin.yaml`, utilise l'API REST OWUI (pas SQLite)
4. **Hot-reload** : service `register-watcher` en Docker, CronJob en K8s
5. **K8s hybrid** : socle dans `owui-socle`, features lourdes dans leurs namespaces
6. **Persistance** : OpenWebUI / agent conversationnel reste stateful ; son stockage doit survivre aux redémarrages via DB persistante et/ou volume partagé si pertinent et nécessaire

## Décisions de migration à respecter

Ces points priment sur toute interprétation implicite :

1. **Coexistence pendant la transition**
   - Ne supprime pas brutalement le mode monorepo existant tant que le mode modulaire n'est pas validé.
   - La coexistence doit être explicite : profils Docker Compose, fichiers `docker-compose.*.yml` séparés, wrapper compatible, ou mécanisme équivalent.
   - Tant que la migration n'est pas validée, il doit exister un chemin de retour simple pour relancer le fonctionnement actuel.

2. **Compatibilité de l'entrée de déploiement**
   - `deploy/deploy-k8s.sh` doit rester une entrée valide pendant la transition.
   - Il peut devenir un wrapper vers la nouvelle orchestration, mais ne doit pas disparaître ni casser les usages actuels.

3. **Socle seul vs flux bout en bout**
   - Le socle doit pouvoir démarrer seul pour valider boot, OIDC, stockage et enregistrement.
   - Le flux complet `OpenWebUI -> pipeline -> microservice` se valide ensuite avec au moins une feature branchée sur le socle.
   - Ne crée pas de dépendance bloquante du socle à un microservice feature au boot.

4. **Découverte des plugins**
   - Ne suppose pas un scan magique du filesystem.
   - La découverte des feature repos doit avoir une source explicite : variable d'environnement, liste de chemins, convention de repos frères documentée, ou script `discover_plugins.sh` déterministe.

5. **API OpenWebUI**
   - Utiliser l'API REST OWUI en priorité pour tools / filters / model_tools si elle couvre réellement le besoin.
   - Si certains objets ne sont pas couverts par l'API de la version cible, documenter précisément le fallback SQLite et l'isoler dans une couche dédiée.

6. **Namespace cible**
   - La cible K8s de `tchap-reader` est `owui-socle`.
   - Ne pas laisser d'ambiguïté entre `socle`, `grafrag` et `owui-socle` dans les manifests, URLs internes ou scripts.

7. **Persistance du stockage conversationnel**
   - L'agent conversationnel ne doit pas perdre ses conversations, ses métadonnées, ni son état utile après redémarrage.
   - Prévoir une persistance explicite pour OpenWebUI : base de données persistante et/ou volume partagé si le composant le nécessite.
   - En Docker : bind mount / volume nommé persistant.
   - En K8s : PVC ou backend persistant équivalent.
   - Si un volume partagé entre composants est nécessaire pour cohérence, cache ou artefacts runtime, le documenter et le justifier ; sinon éviter les partages inutiles.

## Plan d'exécution

Lis `prompts/restructure/02_migration.md` pour les phases.
Lis `prompts/restructure/03_feature_*.md` à `06_feature_*.md` pour chaque feature.

## Discipline d'exécution Git et tests

Cette discipline est obligatoire à chaque phase :

1. Identifier les tests existants pertinents pour la phase.
2. Si la couverture est insuffisante, créer les tests minimaux nécessaires avant la modification.
3. Exécuter les tests pertinents avant la phase pour établir une baseline.
4. Faire un commit de checkpoint avant de modifier le code.
   - Ce commit ne doit pas inclure de secrets ni de fichiers hors périmètre.
   - Si le dépôt contient déjà des changements utiles à conserver, les intégrer proprement au commit de checkpoint ou créer un commit de sauvegarde équivalent.
5. Réaliser la phase.
6. Exécuter les tests après la phase, y compris les nouveaux tests ajoutés.
7. Corriger jusqu'à obtenir un résultat stable et vert.
8. Faire un commit de fin de phase après validation.

### Ordre d'exécution recommandé

```
Phase 1 : Créer experimentation-owui
  ├─ 1a. Initialiser le repo, copier openwebui/, keycloak/, search/
  ├─ 1b. Écrire docker-compose.yml (socle seul, réseau owui-net, stockage persistant)
  ├─ 1c. Écrire k8s/base/ (namespace owui-socle)
  ├─ 1d. Écrire scripts/register_plugins.py (API OWUI, scan owui-plugin.yaml)
  ├─ 1e. Écrire Makefile, .env.example
  └─ 1f. Tester : make up-socle

Phase 2 : Adapter grafrag-experimentation
  ├─ 2a. Créer owui-plugin.yaml (voir 03_feature_grafrag_experimentation.md)
  ├─ 2b. Isoler les services socle du docker-compose sans casser le mode historique
  ├─ 2c. Adapter k8s/ : retirer ou désactiver les manifests socle côté feature sans casser `deploy/deploy-k8s.sh`
  └─ 2d. Tester : socle + grafrag ensemble

Phase 3 : Vérifier les autres features (en parallèle)
  ├─ 3a. anef-knowledge-assistant (voir 04_feature_*.md)
  ├─ 3b. tchap-reader (voir 05_feature_*.md)
  └─ 3c. browser-skill-owui (voir 06_feature_*.md)

Phase 4 : Orchestration
  ├─ 4a. scripts/discover_plugins.sh
  ├─ 4b. deploy/deploy-plugins.sh
  └─ 4c. Service register-watcher + CronJob K8s
```

## Critères d'acceptation

Après chaque phase, vérifie :

- [ ] Les tests pertinents ont été identifiés et exécutés avant la phase
- [ ] Les tests manquants ont été créés avant la modification si nécessaire
- [ ] Un commit de checkpoint existe avant la phase
- [ ] Les tests passent après la phase
- [ ] Un commit de fin de phase existe après validation

### Phase 1 (socle)
- [ ] `make up-socle` lance OpenWebUI + Keycloak + Pipelines
- [ ] Le socle démarre sans dépendre d'un microservice feature
- [ ] OpenWebUI accessible sur http://localhost:3000
- [ ] Auth Keycloak fonctionne (OIDC)
- [ ] Le réseau `owui-net` est créé
- [ ] Les données OpenWebUI / agent conversationnel persistent après redémarrage
- [ ] `k8s/base/` contient les manifests pour tous les services socle

### Phase 2 (grafrag comme feature)
- [ ] `owui-plugin.yaml` existe dans grafrag-experimentation
- [ ] Le docker-compose de grafrag ne contient PAS openwebui/keycloak/pipelines
- [ ] Un mécanisme explicite de compatibilité transitoire existe pour relancer le mode historique
- [ ] `docker compose up` de grafrag rejoint le réseau `owui-net`
- [ ] La pipeline graphrag est montée dans le container pipelines du socle
- [ ] Le bridge est accessible via le réseau partagé
- [ ] Le flux complet OpenWebUI → pipeline → bridge fonctionne avec le socle lancé séparément

### Phase 3 (autres features)
- [ ] Chaque feature a un `owui-plugin.yaml` valide
- [ ] Chaque docker-compose ne duplique pas les services socle
- [ ] Les tools sont déclarés dans `owui-plugin.yaml` (pas dans le socle)
- [ ] `tchap-reader` cible explicitement le namespace `owui-socle`

### Phase 4 (orchestration)
- [ ] `make register` depuis le socle enregistre tous les tools de tous les plugins
- [ ] `make register` est idempotent (2 exécutions successives = pas de duplication)
- [ ] `make deploy` déploie socle + plugins sur K8s
- [ ] `deploy/deploy-k8s.sh` reste utilisable comme point d'entrée de transition
- [ ] Le CronJob `register-plugins` fonctionne en K8s

## Contraintes

- **Ne pas casser le fonctionnement actuel** tant que la migration n'est pas complète.
  Pendant la transition, les deux modes (monorepo et modulaire) doivent coexister.
- **Coexistence explicite** : la coexistence ne doit pas reposer sur des manipulations manuelles implicites ; elle doit être matérialisée par des fichiers, profils ou wrappers versionnés.
- **Pas de sur-ingénierie** : si un script shell de 20 lignes suffit, pas besoin
  d'un framework. Le code existant est pragmatique, rester dans cet esprit.
- **API OWUI** : vérifier que les endpoints `/api/v1/tools` existent dans la
  version v0.8.10 avant d'implémenter `register_plugins.py`. Fallback : SQLite.
- **Couverture fonctionnelle OWUI** : vérifier aussi les endpoints nécessaires pour filters et model_tools ; si l'API ne couvre pas tout, documenter le fallback au lieu de supposer.
- **Idempotence** : chaque script doit pouvoir être relancé sans effet de bord.
- **Secrets** : ne jamais commiter de secrets. Les `.env` restent gitignored.
  Les secrets K8s sont créés par script, pas dans les manifests.
- **Persistance** : les composants stateful du socle, en particulier OpenWebUI / agent conversationnel, doivent avoir un stockage persistant. Ne pas s'appuyer sur un filesystem éphémère.
- **Volumes partagés** : n'introduire un volume partagé entre services que si un besoin réel l'exige ; sinon préférer des frontières claires et une persistance locale à chaque composant stateful.

## Fichiers de référence à lire

Avant de coder, lis ces fichiers pour comprendre l'existant :

```
grafrag-experimentation/
  docker-compose.yml                         # Services actuels
  .env.example                               # Variables d'env
  openwebui/tools/manifest.yaml              # Manifest tools actuel
  scripts/register_all_openwebui_tools.py    # Script d'injection actuel
  scripts/redeploy_openwebui_stack.sh        # Script de redéploiement
  deploy/deploy-k8s.sh                       # Déploiement K8s actuel
  k8s/base/                                  # Manifests K8s actuels
  pipelines/graphrag_pipeline.py             # Exemple de pipeline
  pipelines/scaleway_general_pipeline.py     # Pipeline socle (à migrer)
```

## Comment procéder

1. Commence par Phase 1a-1b : crée le repo socle avec le docker-compose
2. Commence par sécuriser le stockage persistant d'OpenWebUI / agent conversationnel dès la Phase 1
3. Montre-moi le résultat avant de passer à la suite
4. Si une ambiguïté de spec bloque une implémentation sûre, tranche-la explicitement dans le code ou la doc au lieu de laisser deux interprétations possibles
5. Chaque phase se termine par un test de validation
6. Préserve un chemin de retour simple tant que la migration n'est pas validée
7. À chaque phase, respecte la discipline Git et tests définie plus haut : tests avant, commit avant, tests après, commit après

Ne génère pas tout d'un coup. Procède étape par étape, valide avec moi entre chaque phase.
