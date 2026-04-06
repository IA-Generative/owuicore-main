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

### 6. NoneType is not iterable sur les tool calls

**Symptome** : Le LLM appelle un tool (ex: `data_search`) mais l'UI affiche `'NoneType' object is not iterable`. Aucune erreur dans les logs serveur.

**Cause** : Bug dans le middleware OWUI v0.8.12 (`utils/middleware.py`). Quand le LLM Scaleway retourne un `tool_calls` avec des arguments vides (`"arguments": "{\"query\": \"\"}"`), OWUI crashe en iterant un champ `None` lors du processing du resultat du tool. L'erreur est dans le stream SSE, pas dans les logs serveur — ce qui la rend invisible cote backend.

**Diagnostic** :
- Les logs serveur montrent `POST /api/chat/completions 200` (pas d'erreur)
- Le chat history montre un assistant vide (pas de contenu, pas de tool_calls sauvegardés)
- En testant l'API Scaleway directement, on voit que le LLM envoie `query: ""` quand le prompt est generique

**Workaround applique** : Le system prompt contient une instruction explicite pour ne jamais envoyer de parametres vides aux tools :
```
data_search(query) — IMPORTANT : query ne doit JAMAIS etre vide,
utilise les mots-cles de l'utilisateur ou 'donnees ouvertes' par defaut
```

En complement, le tool `data_search` a un fallback : si `query` est vide, il utilise `"données ouvertes"` par defaut au lieu de crasher.

**Fix definitif** : Mettre a jour Open WebUI vers une version > 0.8.12 qui corrige l'iteration de `tool_calls` avec des valeurs `None`.

### 7. Embeddings Scaleway — rate limit 429

**Symptome** : Upload de fichiers echoue avec `Unexpected token '<'` ou `429 Too Many Requests`.

**Cause** : OWUI traite automatiquement chaque fichier uploade via RAG (Tika extraction → embeddings). Avec l'API Scaleway pour les embeddings (`bge-multilingual-gemma2`), le rate limit est vite atteint, surtout avec des fichiers volumineux.

**Workaround applique** : Utiliser un modele d'embeddings local au lieu de l'API Scaleway :
```yaml
RAG_EMBEDDING_ENGINE: ""
RAG_EMBEDDING_MODEL: sentence-transformers/all-MiniLM-L6-v2
```
C'est plus lent (~3s par fichier au lieu de <1s) mais sans limite de debit.

**Alternative** : Verifier l'identite du compte Scaleway (Settings → Identity verification) pour augmenter les quotas, puis repasser sur l'API distante avec un batch_size reduit (`RAG_EMBEDDING_BATCH_SIZE: "4"`).

## Architecture des fichiers de config

```
scripts/
  owui-state.json       # Etat de reference (tools, prompts, models, config MCP)
                        # Exporte depuis Docker local (source de verite)
  sync_owui_state.py    # Applique owui-state.json dans une DB OWUI
  ensure_tools.py       # Decouvre les plugins, genere tools/prompts, ecrit en DB

k8s/base/
  deployment-openwebui.yaml  # Inclut lifecycle.postStart pour les patches
  deployment-tika.yaml       # Extraction de contenu (PDF, DOCX, etc.)

docs/
  bugs-connus.md        # 13 bugs documentes + guide de debug OWUI
  deploiement-k8s.md    # Ce fichier
  cahier-de-tests.md    # 12 tests T4 (dataview) + autres sections
```

## Valves des tools (URLs k8s)

Apres chaque sync, les valves des tools doivent pointer vers les services k8s :

| Tool | Valve | Valeur k8s |
|------|-------|-----------|
| dataview | dataview_api_url | http://data-query:8093 |
| dataview | openwebui_url | http://openwebui:80 |
| websnap | websnap_base_url | http://browser-use:80 |
| tchapreader | tchap_api_url | http://tchap-reader:8087 |
| vision_image_filter | llm_api_url | https://api.scaleway.ai/.../v1 |
| vision_image_filter | llm_api_key | (cle Scaleway) |

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
