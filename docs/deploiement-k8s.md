# Deploiement Kubernetes

## Deploiement rapide

```bash
# 1. Configurer .env (NAMESPACE=miraiku, secrets Scaleway, etc.)
cp .env.example .env && vim .env

# 2. Deployer le socle (build images, push, apply manifests)
./deploy/deploy-k8s.sh

# 3. Synchroniser tools, prompts et config depuis l'etat de reference
OWUI_POD=$(kubectl get pod -n miraiku -l app=openwebui -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n miraiku "$OWUI_POD" -- chmod 666 /app/backend/data/webui.db
kubectl cp scripts/owui-state.json "miraiku/${OWUI_POD}:/tmp/owui-state.json"
kubectl cp scripts/sync_owui_state.py "miraiku/${OWUI_POD}:/tmp/sync_owui_state.py"
kubectl exec -n miraiku "$OWUI_POD" -- python3 /tmp/sync_owui_state.py \
  --state /tmp/owui-state.json --db /app/backend/data/webui.db

# 4. Valider
MODE=k8s OWUI_URL=https://mychat.fake-domain.name ./tests/smoke_test.sh --quick
```

## Pieges connus (post-deploy checklist)

Le deploiement k8s a plusieurs points de friction silencieux. Si les tools "ne marchent pas" alors que tout semble OK, verifier dans cet ordre :

### 1. DB SQLite readonly

**Symptome** : Les chats retournent 400, les logs affichent `attempt to write a readonly database`.

**Cause** : `kubectl cp` cree les fichiers avec uid 501 (Mac) et permissions 644. Le process OWUI ne peut pas ecrire.

**Fix** :
```bash
kubectl exec -n miraiku deploy/openwebui -- chmod 666 /app/backend/data/webui.db
kubectl delete pod -n miraiku -l app=openwebui  # restart necessaire
```

### 2. DIRECT_TOOL_CALLING absent

**Symptome** : Les tools sont enregistres, le system prompt est la, mais le LLM ne les appelle jamais. Il repond en texte simple.

**Cause** : Sans `DIRECT_TOOL_CALLING=true`, Open WebUI n'envoie pas les `tools` dans la requete au LLM.

**Fix** : Verifier que le deployment a la variable :
```yaml
env:
  - name: DIRECT_TOOL_CALLING
    value: "true"
```

### 3. System prompt vide

**Symptome** : Le LLM a les tools mais ne sait pas quand les utiliser. Il repond "je n'ai pas d'outil pour ca".

**Cause** : Le script `ensure_tools.py` a crashe avant d'atteindre l'etape des modeles (ex: erreur pipelines). Les tools sont la mais pas les prompts.

**Fix** : Utiliser `sync_owui_state.py` qui applique tout d'un coup a partir du fichier de reference :
```bash
kubectl exec -n miraiku deploy/openwebui -- python3 /tmp/sync_owui_state.py \
  --state /tmp/owui-state.json --db /app/backend/data/webui.db
```

### 4. MCP label "MCP Tool Server"

**Symptome** : Dans l'UI, les serveurs MCP s'affichent sous le nom generique "MCP Tool Server" au lieu de leur vrai nom.

**Cause** : Le code Open WebUI utilise `server.info.name` avec fallback `'MCP Tool Server'`. Les serveurs MCP qui ne publient pas `info.name` (comme data.gouv.fr) affichent le fallback.

**Fix** : Le deployment inclut un `lifecycle.postStart` qui patche le code au demarrage. Verifier que le patch est present :
```bash
kubectl exec -n miraiku deploy/openwebui -- \
  grep "server.get('name', 'MCP Tool Server')" /app/backend/open_webui/routers/tools.py
```

### 5. Tool valves pointent vers localhost

**Symptome** : Les tools sont appeles par le LLM mais retournent des erreurs de connexion (`Connection refused`, `Name resolution failed`).

**Cause** : Les valves (URLs des backends) utilisent les defauts Docker (`http://host.docker.internal:8086`, `http://localhost:8087`) qui n'existent pas en k8s.

**Fix** : Mettre a jour les valves apres le sync :
```bash
kubectl exec -n miraiku deploy/openwebui -- python3 -c "
import sqlite3, json
db = sqlite3.connect('/app/backend/data/webui.db')
db.execute('UPDATE tool SET valves=? WHERE id=\"dataview\"', (json.dumps({
    'dataview_api_url': 'http://data-query:8093',
    'openwebui_url': 'http://openwebui:80',
    'datagouv_api_url': 'https://www.data.gouv.fr/api/1',
    'timeout': 60,
}),))
db.execute('UPDATE tool SET valves=? WHERE id=\"websnap\"', (json.dumps({
    'websnap_base_url': 'http://browser-use:80',
    'websnap_browser_url': 'http://browser-use-full:80',
    'openwebui_url': 'http://openwebui:80',
}),))
db.execute('UPDATE tool SET valves=? WHERE id=\"tchapreader\"', (json.dumps({
    'tchap_api_url': 'http://tchap-reader:8087',
}),))
db.execute('UPDATE tool SET valves=? WHERE id=\"tchapreader_admin\"', (json.dumps({
    'tchap_api_url': 'http://tchap-reader:8087',
}),))
db.commit()
print('Done')
"
```

## Architecture des fichiers de config

```
scripts/
  owui-state.json       # Etat de reference (tools, prompts, models, config MCP)
                        # Exporte depuis Docker local (source de verite)
  sync_owui_state.py    # Applique owui-state.json dans une DB OWUI
  ensure_tools.py       # Decouvre les plugins, genere tools/prompts, ecrit en DB

k8s/base/
  deployment-openwebui.yaml  # Inclut lifecycle.postStart pour le patch MCP
```

## Mettre a jour l'etat de reference

Apres avoir modifie les tools/prompts en local (Docker), exporter le nouvel etat :

```bash
docker exec owuicore-openwebui-1 python3 -c "
import sqlite3, json
db = sqlite3.connect('/app/backend/data/webui.db')
# ... (voir le script complet dans le README)
" > scripts/owui-state.json
```

Puis commiter et redeployer sur k8s.

## Tests

```bash
# Docker local
./tests/smoke_test.sh

# Kubernetes
MODE=k8s K8S_NAMESPACE=miraiku \
  OWUI_URL=https://mychat.fake-domain.name \
  ./tests/smoke_test.sh
```

Les tests verifient automatiquement les 4 pieges ci-dessus (DB writable, DIRECT_TOOL_CALLING, system prompt, MCP patch).
