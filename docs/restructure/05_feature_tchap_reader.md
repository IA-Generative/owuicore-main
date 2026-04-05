# Adapter `tchap-reader` au contrat socle

Lecture et analyse de salons Tchap (Matrix). Intégration au socle `experimentation-owui` via `owui-plugin.yaml`.

## owui-plugin.yaml

```yaml
name: tchap-reader
version: "1.0.0"

# Services Docker/K8s propres à ce feature (pas le socle)
services:
  - name: tchap-reader
    port: 8087

# Pipelines chargées dans le container pipelines du socle
pipelines:
  files: []

# Tools/filters injectés dans Open WebUI
tools:
  entries:
  - id: tchap_reader
    source_file: app/openwebui_tchap_reader.py
    service_name: tchap-reader
    service_port: 8087
  - id: tchap_admin
    source_file: app/openwebui_tchap_admin.py
    service_name: tchap-reader
    service_port: 8087

# Associations modèle → tools (optionnel)
model_tools: []
#  - models: ["scaleway-general.*"]
#    tool_ids: [tchap_reader, tchap_admin]
#    system: "System prompt quand ces tools sont actifs."

# Variables d'environnement spécifiques
env_vars: []

# K8s
k8s:
  namespace: owui-socle
  custom_image: true

```

## Docker Compose
- Réseau externe `owui-net` (créé par le socle)
- Services feature uniquement : tchap-reader:8087
- Pas de openwebui, keycloak, pipelines dans ce compose

## Kubernetes
- Namespace : `owui-socle` (colocalisé avec le socle)
- Même namespace `owui-socle` → accès direct : `http://openwebui:8080`
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
4. Adapter `k8s/base/` : namespace `owui-socle`, retirer ou désactiver les manifests socle côté feature
5. Adapter `deploy/deploy-k8s.sh` : autonome ou appelé par le socle, sans casser l'entrée existante pendant la transition
6. Vérifier que les pipelines et tools fonctionnent avec le socle lancé
7. Exécuter les tests après changement puis faire le commit de fin de phase
