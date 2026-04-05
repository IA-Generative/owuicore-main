# Adapter `grafrag-experimentation` au contrat socle

GraphRAG bridge, corpus manager, indexation multi-corpus. Intégration au socle `experimentation-owui` via `owui-plugin.yaml`.

## owui-plugin.yaml

```yaml
name: grafrag-experimentation
version: "1.0.0"

# Services Docker/K8s propres à ce feature (pas le socle)
services:
  - name: bridge
    port: 8081
  - name: corpus-manager
    port: 8084
  - name: corpus-worker
    port: 8000
  - name: drive
    port: 8085

# Pipelines chargées dans le container pipelines du socle
pipelines:
  files:
  - pipelines/graphrag_pipeline.py

# Tools/filters injectés dans Open WebUI
tools:
  entries: []

# Associations modèle → tools (optionnel)
model_tools: []
#  - models: ["scaleway-general.*"]
#    tool_ids: [my_tool]
#    system: "System prompt quand ces tools sont actifs."

# Variables d'environnement spécifiques
env_vars: []

# K8s
k8s:
  namespace: grafrag
  custom_image: true

```

## Docker Compose
- Réseau externe `owui-net` (créé par le socle)
- Services feature uniquement : bridge:8081, corpus-manager:8084, corpus-worker, drive:8085
- Pas de openwebui, keycloak, pipelines dans ce compose

## Kubernetes
- Namespace : `grafrag` (namespace dédié)
- Namespace `grafrag` → cross-ns : `http://openwebui.owui-socle.svc.cluster.local:8080`
- URLs du socle configurables via env : `${OPENWEBUI_INTERNAL_URL}`, `${KEYCLOAK_INTERNAL_URL}`
- Image custom : oui → build + push vers rg.fr-par.scw.cloud/funcscwnspricelessmontalcinhiacgnzi

## Workflow obligatoire

1. Identifier les tests existants pertinents.
2. Créer les tests minimaux manquants avant modification si nécessaire.
3. Exécuter les tests avant la phase.
4. Faire un commit de checkpoint avant de modifier le repo.
5. Réaliser les changements.
6. Exécuter les tests après la phase.
7. Faire un commit de fin de phase après validation.

## Tâches
1. Créer ou adapter les tests ciblés du feature et les exécuter avant changement
2. Créer `owui-plugin.yaml` (ci-dessus)
3. Adapter `docker-compose.yml` : isoler les services socle, joindre `owui-net`, préserver un mode historique transitoire si nécessaire
4. Adapter `k8s/base/` : namespace `grafrag`, retirer ou désactiver les manifests socle côté feature
5. Adapter `deploy/deploy-k8s.sh` : autonome ou appelé par le socle, sans casser l'entrée existante pendant la transition
6. Vérifier que les pipelines et tools fonctionnent avec le socle lancé
7. Exécuter les tests après changement puis faire le commit de fin de phase
