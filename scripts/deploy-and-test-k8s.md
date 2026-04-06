# Instructions de déploiement et test K8s Scaleway

## Contexte
Tu dois déployer l'ensemble de la plateforme MirAI sur le cluster Kubernetes Scaleway (namespace `miraiku`), vérifier que tous les services et tools fonctionnent, puis générer un rapport de test.

## Prérequis
- Cluster k8s Scaleway accessible via `kubectl` (namespace `miraiku`)
- Docker local fonctionnel
- Repos dans `~/Documents/GitHub/` : owuicore-main, owuitools-dataview, owuitools-websnap, owuitools-tchapreader
- Fichier `.env` configuré dans owuicore-main avec les secrets Scaleway

## Étapes

### 1. Build et push des images custom (amd64)
Les images doivent être buildées en `--platform linux/amd64` (cluster AMD64, dev Mac ARM).

```bash
cd ~/Documents/GitHub/owuicore-main
REGISTRY=$(grep "^REGISTRY=" .env | cut -d= -f2)

# Dataview
cd ~/Documents/GitHub/owuitools-dataview
TAG="$(date +%Y%m%d-%H%M%S)"
docker buildx build --platform linux/amd64 --push -t "${REGISTRY}/data-query:${TAG}" -f Dockerfile .
kubectl set image deploy/data-query -n miraiku "data-query=${REGISTRY}/data-query:${TAG}"

# Websnap (browser-use)
cd ~/Documents/GitHub/owuitools-websnap
TAG="$(date +%Y%m%d-%H%M%S)"
docker buildx build --platform linux/amd64 --push -t "${REGISTRY}/browser-use:${TAG}" -f docker/Dockerfile .
kubectl set image deploy/browser-use -n miraiku "browser-use=${REGISTRY}/browser-use:${TAG}"

# Websnap full (browser-use-full)
TAG="$(date +%Y%m%d-%H%M%S)"
docker buildx build --platform linux/amd64 --push -t "${REGISTRY}/browser-use-full:${TAG}" -f docker/Dockerfile.browser .
kubectl set image deploy/browser-use-full -n miraiku "browser-use-full=${REGISTRY}/browser-use-full:${TAG}"

# Tchapreader
cd ~/Documents/GitHub/owuitools-tchapreader
TAG="$(date +%Y%m%d-%H%M%S)"
docker buildx build --platform linux/amd64 --push -t "${REGISTRY}/tchap-reader:${TAG}" -f Dockerfile .
kubectl set image deploy/tchap-reader -n miraiku "tchap-reader=${REGISTRY}/tchap-reader:${TAG}"
```

**CHECK** : Vérifier que chaque `kubectl set image` retourne "image updated", puis `kubectl rollout status deploy/XXX -n miraiku --timeout=120s` pour chaque.

### 2. Déployer le socle owuicore
```bash
cd ~/Documents/GitHub/owuicore-main
bash deploy/deploy-k8s.sh
```

**CHECK** : Le script doit se terminer avec `=== Socle deployment complete ===` et lister tous les pods/services/ingress.

### 3. Sync tools, prompts et config
La DB OWUI k8s est vierge après un restart. Il faut y injecter les tools, models et config.

```bash
OWUI_POD=$(kubectl get pod -n miraiku -l app=openwebui -o jsonpath='{.items[0].metadata.name}')

# Fix permissions DB (kubectl cp crée avec uid 501)
kubectl exec -n miraiku "$OWUI_POD" -- chmod 666 /app/backend/data/webui.db

# Copier le state de référence et le script de sync
kubectl cp scripts/owui-state.json "miraiku/${OWUI_POD}:/tmp/owui-state.json"
kubectl cp scripts/sync_owui_state.py "miraiku/${OWUI_POD}:/tmp/sync_owui_state.py"

# Sync
kubectl exec -n miraiku "$OWUI_POD" -- python3 /tmp/sync_owui_state.py \
  --state /tmp/owui-state.json --db /app/backend/data/webui.db
```

**CHECK** : Doit afficher "Synced N tools", "Synced N functions", "Synced N models", "Done".

### 4. Configurer les valves k8s
Les valves des tools doivent pointer vers les services k8s (pas localhost/docker).

```bash
OWUI_POD=$(kubectl get pod -n miraiku -l app=openwebui -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n miraiku "$OWUI_POD" -- python3 -c "
import sqlite3, json
db = sqlite3.connect('/app/backend/data/webui.db')

# Dataview
db.execute('UPDATE tool SET valves=? WHERE id=\"dataview\"', (json.dumps({
    'dataview_api_url': 'http://data-query:8093',
    'openwebui_url': 'http://openwebui:80',
    'datagouv_api_url': 'https://www.data.gouv.fr/api/1',
    'timeout': 60,
}),))

# Websnap
db.execute('UPDATE tool SET valves=? WHERE id=\"websnap\"', (json.dumps({
    'websnap_base_url': 'http://browser-use:80',
    'websnap_browser_url': 'http://browser-use-full:80',
    'openwebui_url': 'http://openwebui:80',
}),))

# Tchapreader
db.execute('UPDATE tool SET valves=? WHERE id=\"tchapreader\"', (json.dumps({
    'tchap_api_url': 'http://tchap-reader:8087',
}),))
db.execute('UPDATE tool SET valves=? WHERE id=\"tchapreader_admin\"', (json.dumps({
    'tchap_api_url': 'http://tchap-reader:8087',
}),))

# Vision filter
import os
scw_url = 'https://api.scaleway.ai/$(grep SCW_LLM_BASE_URL .env | cut -d/ -f4-5)'
# Note: get the real values from the .env file
db.execute('UPDATE function SET valves=? WHERE id=\"vision_image_filter\"', (json.dumps({
    'llm_api_url': scw_url,
    'llm_api_key': 'GET_FROM_ENV',
    'vision_model': 'pixtral-12b-2409',
    'timeout': 120,
    'enabled': True,
}),))

db.commit()
print('Valves configured')
"
```

**IMPORTANT** : Remplacer `scw_url` et `llm_api_key` avec les vraies valeurs du `.env` :
```bash
SCW_URL=$(grep "^SCW_LLM_BASE_URL=" .env | cut -d= -f2)
SCW_KEY=$(grep "^SCW_SECRET_KEY_LLM=" .env | cut -d= -f2)
```

**CHECK** : Vérifier avec :
```bash
kubectl exec -n miraiku "$OWUI_POD" -- python3 -c "
import sqlite3, json
db = sqlite3.connect('/app/backend/data/webui.db')
for t in db.execute('SELECT id, valves FROM tool').fetchall():
    v = json.loads(t[1]) if t[1] else {}
    print(f'{t[0]}: {list(v.keys()) or \"EMPTY\"}')" 
```

### 5. Vérifications post-deploy

#### 5a. Services health
```bash
for svc in openwebui keycloak pipelines searxng search-valkey tika data-query browser-use tchap-reader; do
  status=$(kubectl get deploy "$svc" -n miraiku -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
  echo "$svc: ${status:-0} ready"
done
```

#### 5b. DB writable
```bash
kubectl exec -n miraiku deploy/openwebui -- python3 -c "
import sqlite3
db = sqlite3.connect('/app/backend/data/webui.db')
db.execute('CREATE TABLE IF NOT EXISTS _t(x int)')
db.execute('DROP TABLE _t')
print('DB writable: OK')"
```

#### 5c. DIRECT_TOOL_CALLING
```bash
kubectl exec -n miraiku deploy/openwebui -- printenv DIRECT_TOOL_CALLING
# Must be "true"
```

#### 5d. System prompt
```bash
kubectl exec -n miraiku deploy/openwebui -- python3 -c "
import sqlite3, json
db = sqlite3.connect('/app/backend/data/webui.db')
m = db.execute('SELECT params FROM model WHERE id=\"gpt-oss-120b\"').fetchone()
p = json.loads(m[0]) if m and m[0] else {}
print(f'System prompt: {len(p.get(\"system\",\"\"))} chars')
print(f'data_search: {\"data_search\" in p.get(\"system\",\"\")}')"
```

#### 5e. Tools registered
```bash
kubectl exec -n miraiku deploy/openwebui -- python3 -c "
import sqlite3, json
db = sqlite3.connect('/app/backend/data/webui.db')
for t in db.execute('SELECT id, specs FROM tool').fetchall():
    funcs = [s['name'] for s in json.loads(t[1])] if t[1] else []
    print(f'{t[0]}: {funcs}')"
```

#### 5f. MCP label patch
```bash
kubectl exec -n miraiku deploy/openwebui -- \
  grep "server.get('name', 'MCP Tool Server')" /app/backend/open_webui/routers/tools.py
```

#### 5g. reasoning_tags disabled
```bash
kubectl exec -n miraiku deploy/openwebui -- python3 -c "
import sqlite3, json
db = sqlite3.connect('/app/backend/data/webui.db')
m = db.execute('SELECT params FROM model WHERE id=\"gpt-oss-120b\"').fetchone()
p = json.loads(m[0]) if m and m[0] else {}
print(f'reasoning_tags: {p.get(\"reasoning_tags\")}')"
# Must be False
```

### 6. Tests fonctionnels

Créer une API key pour les tests :
```bash
OWUI_POD=$(kubectl get pod -n miraiku -l app=openwebui -o jsonpath='{.items[0].metadata.name}')
API_KEY=$(kubectl exec -n miraiku "$OWUI_POD" -- python3 -c "
import sqlite3, secrets, time, json
db = sqlite3.connect('/app/backend/data/webui.db')
user_id = db.execute('SELECT id FROM user LIMIT 1').fetchone()[0]
key = 'sk-' + secrets.token_hex(24)
now = int(time.time())
db.execute('INSERT INTO api_key (id, user_id, key, data, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)',
           (secrets.token_hex(8), user_id, key, '{}', now, now))
db.commit()
print(key)")
echo "API_KEY=$API_KEY"
```

#### 6a. Dataview preview (URL)
```bash
kubectl run test-dataview --rm -i --restart=Never --namespace=miraiku --image=curlimages/curl:latest -- \
  curl -s --max-time 30 -X POST "http://data-query:8093/preview" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://www.data.gouv.fr/fr/datasets/r/008a2dda-2c60-4b63-b910-998f6f818089"}'
```
**CHECK** : Doit retourner JSON avec `filename`, `format: csv`, `rows: 39192`.

#### 6b. Dataview schema
```bash
kubectl run test-schema --rm -i --restart=Never --namespace=miraiku --image=curlimages/curl:latest -- \
  curl -s --max-time 30 -X POST "http://data-query:8093/schema" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://www.data.gouv.fr/fr/datasets/r/008a2dda-2c60-4b63-b910-998f6f818089"}'
```
**CHECK** : JSON avec `columns` et `row_count`.

#### 6c. Websnap extract
```bash
kubectl run test-websnap --rm -i --restart=Never --namespace=miraiku --image=curlimages/curl:latest -- \
  curl -s --max-time 30 -X POST "http://browser-use/extract" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com"}'
```
**CHECK** : JSON avec `ok: true` et `markdown` contenant "Example Domain".

#### 6d. Tchapreader health
```bash
kubectl run test-tchap --rm -i --restart=Never --namespace=miraiku --image=curlimages/curl:latest -- \
  curl -s --max-time 10 "http://tchap-reader:8087/healthz"
```
**CHECK** : JSON avec `status: ok`.

#### 6e. SearXNG search
```bash
kubectl run test-searxng --rm -i --restart=Never --namespace=miraiku --image=curlimages/curl:latest -- \
  curl -s --max-time 15 "http://searxng/search?q=test&format=json"
```
**CHECK** : JSON avec `results` array non-vide.

#### 6f. Tika extraction
```bash
kubectl run test-tika --rm -i --restart=Never --namespace=miraiku --image=curlimages/curl:latest -- \
  curl -s --max-time 10 -X PUT -H "Content-Type: text/plain" --data "Hello Tika" "http://tika:9998/tika"
```
**CHECK** : Réponse contenant "Hello".

#### 6g. LLM chat (via OWUI API)
```bash
curl -sk --max-time 60 -X POST "https://mychat.fake-domain.name/api/chat/completions" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-oss-120b","messages":[{"role":"user","content":"Dis PONG"}],"stream":false}'
```
**CHECK** : Réponse contenant "PONG".

### 7. Générer le rapport

Stocker le rapport dans `/tmp/k8s-deploy-report-$(date +%Y%m%d-%H%M%S).md` avec :
- Date et heure
- Version des images déployées
- Résultat de chaque check (PASS/FAIL)
- Résultat de chaque test fonctionnel (PASS/FAIL/SKIP)
- Erreurs rencontrées
- Temps total de déploiement

Aussi copier le rapport dans `~/Documents/GitHub/owuicore-main/docs/reports/`.

### 8. Problèmes connus

Lire `docs/bugs-connus.md` et `docs/deploiement-k8s.md` pour les workarounds :
- DB readonly après kubectl cp → `chmod 666`
- Valves pointent vers localhost → reconfigurer pour k8s
- reasoning_tags doit être False pour gpt-oss-120b
- MCP label patch via lifecycle.postStart
- Image upload skip via entrypoint patch
