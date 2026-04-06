# Bugs connus et workarounds

## 1. NoneType is not iterable sur les tool calls (OWUI v0.8.12)

**Symptome** : Le LLM appelle un tool (ex: `data_search`) mais l'UI affiche `'NoneType' object is not iterable`. Aucune erreur dans les logs serveur.

**Cause racine** : Bug dans le middleware Open WebUI v0.8.12 (`utils/middleware.py`). Quand le LLM Scaleway retourne un `tool_calls` avec des arguments vides (`"arguments": "{\"query\": \"\"}"`), OWUI crashe en iterant un champ `None` lors du processing du resultat du tool. L'erreur est dans le stream SSE, pas dans les logs serveur — invisible cote backend.

**Comment diagnostiquer** :
1. Les logs serveur montrent `POST /api/chat/completions 200` (pas d'erreur)
2. Le chat history en DB montre un assistant vide (pas de contenu, pas de tool_calls)
3. Tester l'API Scaleway directement pour voir ce que le LLM envoie :
```bash
SCW_URL=$(grep "^SCW_LLM_BASE_URL=" .env | cut -d= -f2)
SCW_KEY=$(grep "^SCW_SECRET_KEY_LLM=" .env | cut -d= -f2)
curl -s -X POST "${SCW_URL}/chat/completions" \
  -H "Authorization: Bearer $SCW_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-oss-120b",
    "messages": [{"role": "user", "content": "Peux-tu lister les données open data ?"}],
    "tools": [{"type":"function","function":{"name":"data_search","parameters":{"type":"object","properties":{"query":{"type":"string"}}}}}]
  }' | jq '.choices[0].message.tool_calls'
```
Si le LLM retourne `"arguments": "{\"query\": \"\"}"` → c'est le bug.

**Workarounds appliques** :
- System prompt avec instruction explicite : `"query ne doit JAMAIS etre vide, utilise les mots-cles de l'utilisateur ou 'donnees ouvertes' par defaut"`
- Fallback dans le tool : si `query` est vide, utilise `"données ouvertes"` par defaut

**Fix definitif** : Mettre a jour Open WebUI vers une version > 0.8.12.

---

## 2. Embeddings Scaleway — rate limit 429

**Symptome** : Upload de fichiers echoue avec `Unexpected token '<'` ou `429 Too Many Requests`. Le parsing JSON echoue car Scaleway retourne une page HTML d'erreur.

**Cause racine** : OWUI traite automatiquement chaque fichier uploade via RAG (Tika extraction → embeddings API). Avec l'API Scaleway pour les embeddings (`bge-multilingual-gemma2`), le rate limit est atteint rapidement, surtout avec des fichiers volumineux qui generent beaucoup de chunks.

**Comment diagnostiquer** :
```bash
docker logs owuicore-openwebui-1 2>&1 | grep "429"
# → 429, message='Too Many Requests', url='.../embeddings'
```

**Workaround applique** : Utiliser un modele d'embeddings local :
```yaml
RAG_EMBEDDING_ENGINE: ""
RAG_EMBEDDING_MODEL: sentence-transformers/all-MiniLM-L6-v2
```
Plus lent (~3s par fichier) mais sans limite de debit.

**Alternative** : Verifier l'identite du compte Scaleway (`console.scaleway.com` → Settings → Identity verification) pour augmenter les quotas, puis repasser sur l'API distante avec un batch_size reduit :
```yaml
RAG_EMBEDDING_ENGINE: openai
RAG_EMBEDDING_MODEL: bge-multilingual-gemma2
RAG_EMBEDDING_BATCH_SIZE: "4"
```

---

## 3. DB SQLite readonly apres kubectl cp

**Symptome** : Les chats retournent 400, les logs affichent `attempt to write a readonly database`.

**Cause racine** : `kubectl cp` cree les fichiers avec uid 501 (macOS) et permissions 644. Le process OWUI ne peut pas ecrire.

**Comment diagnostiquer** :
```bash
kubectl exec -n miraiku deploy/openwebui -- ls -la /app/backend/data/webui.db
# → -rw-r--r-- 1 501 root ... (pas de write pour group/others)
```

**Fix** :
```bash
kubectl exec -n miraiku deploy/openwebui -- chmod 666 /app/backend/data/webui.db
kubectl delete pod -n miraiku -l app=openwebui  # restart necessaire
```

---

## 4. DIRECT_TOOL_CALLING absent — tools silencieusement ignores

**Symptome** : Les tools sont enregistres, le system prompt est correct, mais le LLM ne les appelle jamais. Repond en texte simple.

**Cause racine** : Sans `DIRECT_TOOL_CALLING=true`, Open WebUI n'envoie pas les `tools` dans la requete au provider LLM. Le LLM ne sait meme pas que les tools existent.

**Comment diagnostiquer** :
```bash
# Docker
docker exec owuicore-openwebui-1 printenv DIRECT_TOOL_CALLING
# K8s
kubectl exec -n miraiku deploy/openwebui -- printenv DIRECT_TOOL_CALLING
# Doit afficher "true"
```

**Fix** : Ajouter dans le deployment :
```yaml
- name: DIRECT_TOOL_CALLING
  value: "true"
```

---

## 5. Tool valves pointent vers localhost (k8s)

**Symptome** : Les tools sont appeles par le LLM mais retournent des erreurs de connexion.

**Cause racine** : Les valves (URLs des backends) utilisent les defauts Docker (`http://host.docker.internal:8086`) qui n'existent pas en k8s.

**Comment diagnostiquer** :
```bash
kubectl exec -n miraiku deploy/openwebui -- python3 -c "
import sqlite3, json
db = sqlite3.connect('/app/backend/data/webui.db')
for row in db.execute('SELECT id, valves FROM tool').fetchall():
    v = json.loads(row[1]) if row[1] else {}
    print(f'{row[0]}: {v or \"EMPTY (docker defaults)\"}')
"
```

**Fix** : Mettre a jour les valves avec les noms de services k8s. Voir `docs/deploiement-k8s.md` section 5.

---

## 6. MCP server data.gouv.fr — NoneType crash (PARTIELLEMENT RESOLU)

**Symptome** : Le MCP `data-gouv-fr` est active, le LLM l'appelle, mais ca crashe avec `NoneType is not iterable`.

**Cause racine trouvee** : Ce n'etait PAS un bug MCP. C'etait notre filter `dataview_auto_preview` qui crashait car OWUI passe `files: null` (pas `[]`) dans `body.metadata`. Le crash dans `_find_all_tabular_files` se produisait a chaque requete chat, **avant** que le MCP soit appele.

L'erreur etait masquee par un `log.debug` dans `main.py` ligne 1816 — invisible en log level INFO. Le patch `log.debug` → `log.exception` a revele le vrai traceback.

**Fix applique** : `.get("files") or []` au lieu de `.get("files", [])` dans le filter.

**Etat actuel** : MCP desactive dans `ensure_tools.py`, remplace par le tool `data_search` (v1.4.0) qui utilise l'API REST de data.gouv.fr :
- `data_search(query, organization, tag, page)` — recherche avec filtres et pagination
- `data_list_popular(theme, page)` — datasets les plus consultes par theme

**Prochaine etape** : Le MCP officiel (https://github.com/datagouv/datagouv-mcp) est plus riche que notre tool :
- 9 fonctions vs 5 (search, list_resources, query_resource_data, get_metrics, etc.)
- Pagination, filtrage et tri natifs cote serveur
- Acces direct aux donnees sans telecharger le fichier entier

Maintenant que le crash du filter est corrige, le MCP pourrait fonctionner a nouveau.
A tester : reactiver le MCP + garder nos tools pour l'upload/preview de fichiers locaux.
Le MCP gererait la recherche/exploration, nos tools gereraient les fichiers uploades.

---

## 7. Fichiers fantomes dans les nouvelles conversations

**Symptome** : Les fichiers uploades dans les conversations precedentes apparaissent dans les nouvelles conversations.

**Cause racine** : OWUI stocke les fichiers dans la table `file` et les lie aux chats via `chat_file`. Les fichiers persistent entre les conversations. Peut aussi venir du cache du navigateur ou du drag & drop macOS (qui envoie tous les fichiers selectionnes dans le Finder).

**Workaround** :
- Utiliser le bouton "+" dans l'UI au lieu du drag & drop
- Nettoyer les fichiers :
```bash
docker exec owuicore-openwebui-1 python3 -c "
import sqlite3
db = sqlite3.connect('/app/backend/data/webui.db')
db.execute('DELETE FROM chat_file')
db.execute('DELETE FROM file')
db.commit()
"
```
- En dernier recours : supprimer le volume et repartir a zero :
```bash
docker compose down
docker volume rm owui-socle-openwebui-data
docker compose up -d
```

---

## 8. data_schema 500 — numpy.int64 serialization

**Symptome** : `data_schema` retourne une erreur 500 Internal Server Error.

**Cause racine** : Pydantic ne peut pas serialiser `numpy.int64` en JSON. Les colonnes numeriques retournent `min`/`max` comme `numpy.int64` au lieu de `int` Python natif.

**Fix applique** : Utiliser `.item()` pour convertir les valeurs numpy en types Python natifs dans `api.py`.

---

## 9. data_query crash sur colonnes non-numeriques

**Symptome** : `data_query` avec une question de tri alphabetique crashe avec `TypeError: cannot use method 'nlargest' with dtype str`.

**Cause racine** : Les operations `top_n` et `bottom_n` utilisent `df.nlargest()` / `df.nsmallest()` qui ne fonctionnent que sur les colonnes numeriques.

**Fix applique** : Fallback sur `sort_values().head()` quand la colonne n'est pas numerique.

---

## 10. Filter dataview_auto_preview — fichier non detecte (401)

**Symptome** : Le filter detecte le fichier (`detected tabular file xxx.xlsx`) mais echoue avec `could not fetch file (401)`.

**Cause racine** : Le filter faisait un appel HTTP a OWUI (`/api/v1/files/{id}/content`) pour recuperer le fichier. Le token user n'est pas transmis correctement aux filters.

**Fix applique** : Le filter lit maintenant les fichiers directement depuis le disque (`/app/backend/data/uploads/`) au lieu de passer par l'API HTTP. Plus besoin d'authentification.

**Note** : Les fichiers sont stockes sous le format `{file_id}_{filename}` dans le repertoire uploads.
