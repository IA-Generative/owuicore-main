# Bugs connus et workarounds

## 1. NoneType is not iterable sur les tool calls (RESOLU)

**Symptome** : Le LLM appelle un tool mais l'UI affiche `'NoneType' object is not iterable`. Aucune erreur dans les logs serveur.

**Cause racine trouvee** : C'etait notre filter `dataview_auto_preview` qui crashait, PAS un bug OWUI. Le filter iterait `body["metadata"]["files"]` qui peut etre `null` (pas `[]`). L'erreur etait masquee par `log.debug` dans `main.py` (voir section Debug).

**Resolution** : `.get("files") or []` au lieu de `.get("files", [])` dans le filter dataview_auto_preview. Voir bug #6 pour le detail complet.

**Note** : Le MCP data.gouv.fr ("Open Data (mcp)") a ete reactive apres ce fix. Le crash n'etait pas lie au MCP.

---

## 2. Embeddings Scaleway — rate limit 429 (WORKAROUND)

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

## 3. DB SQLite readonly apres kubectl cp (K8S ONLY)

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

## 4. DIRECT_TOOL_CALLING absent — tools silencieusement ignores (RESOLU)

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

## 5. Tool valves pointent vers localhost (K8S ONLY)

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

## 6. MCP server data.gouv.fr — NoneType crash (RESOLU)

**Symptome** : Le MCP `data-gouv-fr` etait active, le LLM l'appelait, crash `NoneType is not iterable`.

**Cause racine** : Notre filter `dataview_auto_preview` crashait car OWUI passe `files: null` (pas `[]`) dans `body.metadata`. Le crash se produisait a chaque requete chat, **avant** que le MCP soit appele. L'erreur etait masquee par `log.debug` dans `main.py`.

**Fix applique** : `.get("files") or []` au lieu de `.get("files", [])` dans le filter.

**Etat actuel** : MCP reactived ("Open Data (mcp)") + nos tools REST (`data_search`, `data_list_popular`) cohabitent :
- MCP data.gouv.fr : 9 fonctions natives (search, list_resources, query_resource_data, etc.)
- Nos tools REST : data_search (filtres org/tag, pagination), data_list_popular, data_preview, data_schema, data_query
- Les deux approches se completent : MCP pour l'exploration, nos tools pour l'upload/preview de fichiers locaux

---

## 7. Contexte RAG pollue entre conversations (CONNU)

**Symptome** : Les fichiers uploades dans les conversations precedentes influencent les reponses du LLM dans les nouvelles conversations. Par exemple, un CV uploade dans un chat precedent apparait dans les resultats GraphRAG d'un autre chat.

**Cause racine** : Deux phenomenes :
1. Le drag & drop macOS peut envoyer plusieurs fichiers involontairement (utiliser le bouton "+" a la place)
2. Le RAG OWUI indexe les fichiers uploades et les injecte dans le contexte du LLM via les embeddings. Si le meme utilisateur a uploade des fichiers dans d'autres conversations, le RAG peut les retrouver par similarite.

**Workaround** : Pour les tests pipeline (GraphRAG, ANEF), toujours ouvrir une **nouvelle conversation vierge** sans fichiers uploades. Cela evite la pollution du contexte RAG.

---

## 8. data_schema 500 — numpy.int64 serialization (RESOLU)

**Symptome** : `data_schema` retourne une erreur 500 Internal Server Error.

**Cause racine** : Pydantic ne peut pas serialiser `numpy.int64` en JSON. Les colonnes numeriques retournent `min`/`max` comme `numpy.int64` au lieu de `int` Python natif.

**Fix applique** : Utiliser `.item()` pour convertir les valeurs numpy en types Python natifs dans `api.py`.

---

## 9. data_query crash sur colonnes non-numeriques (RESOLU)

**Symptome** : `data_query` avec une question de tri alphabetique crashe avec `TypeError: cannot use method 'nlargest' with dtype str`.

**Cause racine** : Les operations `top_n` et `bottom_n` utilisent `df.nlargest()` / `df.nsmallest()` qui ne fonctionnent que sur les colonnes numeriques.

**Fix applique** : Fallback sur `sort_values().head()` quand la colonne n'est pas numerique.

---

## 10. gpt-oss-120b reasoning fuit dans l'affichage apres tool call (WORKAROUND)

**Symptome** : Apres un tool call (websnap, data_query, etc.), le LLM affiche son raisonnement brut en anglais ("The user asks...") au lieu de la reponse synthetisee. Le contenu est vide ou contient le texte du reasoning.

**Cause racine** : gpt-oss-120b retourne un champ `reasoning` separe dans la reponse API (pas des tags inline `<think>`). OWUI v0.8.12 gere mal ce format apres un tool call — il affiche le reasoning comme du contenu.

**Comment diagnostiquer** :
```bash
# Tester directement l'API Scaleway
curl -s -X POST "${SCW_URL}/chat/completions" \
  -H "Authorization: Bearer $SCW_KEY" \
  -d '{"model":"gpt-oss-120b","messages":[{"role":"user","content":"test"}],"stream":false}' | \
  jq '.choices[0].message | {content: .content[:100], reasoning: .reasoning[:100]}'
# Si les deux sont presents → le modele retourne du reasoning separe
```

**Workaround applique** : Desactiver la detection reasoning dans les params du modele :
```python
# Dans ensure_tools.py ou via DB directe
params["reasoning_tags"] = False
```
On perd l'affichage "Reflexion pendant X secondes" (cosmetique) mais le contenu s'affiche correctement.

**Alternatives** :
- Utiliser un modele sans reasoning (mistral-small) — moins bon en tool calling
- Attendre OWUI > 0.8.12 qui gere le champ `reasoning` separe
- Passer à un modele qui utilise des tags inline (`<think>`) au lieu d'un champ separe

---

## 11. Filter dataview_auto_preview — fichier non detecte (401) (RESOLU)

**Symptome** : Le filter detecte le fichier (`detected tabular file xxx.xlsx`) mais echoue avec `could not fetch file (401)`.

**Cause racine** : Le filter faisait un appel HTTP a OWUI (`/api/v1/files/{id}/content`) pour recuperer le fichier. Le token user n'est pas transmis correctement aux filters.

**Fix applique** : Le filter lit maintenant les fichiers directement depuis le disque (`/app/backend/data/uploads/`) au lieu de passer par l'API HTTP. Plus besoin d'authentification.

**Note** : Les fichiers sont stockes sous le format `{file_id}_{filename}` dans le repertoire uploads.

---

## 12. Tchapreader UserValves has no attribute 'get' (RESOLU)

**Symptome** : `tchap_connect` retourne `'UserValves' object has no attribute 'get'`.

**Cause racine** : OWUI passe les UserValves comme un objet Pydantic, pas un dict. Le code faisait `user.get("valves", {}).get("tchap_email")` qui echoue car l'objet Pydantic n'a pas de methode `.get()`.

**Fix applique** : `_get_user_valves()` convertit l'objet Pydantic en dict via `model_dump()` avant d'acceder aux valeurs.

---

## 13. Upload d'image crashe avec "Unexpected token <" (RESOLU)

**Symptome** : L'upload d'une image (jpeg, png) echoue immediatement avec `Unexpected token '<', "<html> <h"... is not valid JSON`.

**Cause racine** : OWUI tente de traiter (RAG/embeddings) chaque fichier uploade. Pour les images, le code leve `Exception('File type image/jpeg is not supported for processing')`. Le frontend recoit une page HTML d'erreur au lieu de JSON.

**Fix applique** : Patch dans l'entrypoint docker-compose qui remplace le `raise Exception` par un `log.info` (skip silencieux). Les images sont gerees par le filter vision, pas par le RAG.

```yaml
# docker-compose.yml entrypoint
python3 -c "
c = open('/app/backend/open_webui/routers/files.py').read()
old = \"raise Exception(f'File type {content_type} is not supported for processing')\"
new = \"__import__('logging').getLogger(__name__).info(f'Skip processing {content_type}')\"
open('/app/backend/open_webui/routers/files.py','w').write(c.replace(old, new))
"
```

---

## 13. Vision filter "returned no results" — image non detectee (RESOLU)

**Symptome** : Le filter vision s'execute (status "Analyzing 1 image(s)") mais retourne "no results" immediatement.

**Cause racine** : OWUI met les images uploadees dans `body["metadata"]["files"]`, pas dans le content multimodal `image_url`. Le filter v2.0 ne cherchait que dans `content` (format OpenAI).

**Fix applique** : Filter vision v3.0 cherche les images dans 3 sources :
1. `body["metadata"]["files"]` — fichiers uploades (format OWUI)
2. `body["files"]` — parfois utilise
3. `messages[-1]["content"]` — format multimodal (image_url inline)

Pour les fichiers uploades, le filter lit l'image depuis `/app/backend/data/uploads/` et la convertit en base64 data URI pour l'envoyer a pixtral.

**Comment debugger** : Tester le filter en isolation :
```bash
docker exec owuicore-openwebui-1 python3 -c "
import asyncio, sqlite3, json, os
db = sqlite3.connect('/app/backend/data/webui.db')
content = db.execute('SELECT content FROM function WHERE id=\"vision_image_filter\"').fetchone()[0]
valves_str = db.execute('SELECT valves FROM function WHERE id=\"vision_image_filter\"').fetchone()[0]
exec(content)
f = Filter()
for k, v in json.loads(valves_str).items(): setattr(f.valves, k, v)
body = {'messages': [{'role': 'user', 'content': 'Que contient cette image ?'}],
  'metadata': {'files': [{'type': 'file', 'id': 'FILE_ID_HERE', 'file': {'id': 'FILE_ID_HERE', 'filename': 'test.jpg', 'meta': {'content_type': 'image/jpeg'}}}]}}
result = asyncio.run(f.inlet(body))
print('OK' if 'image_analysis' in result['messages'][-1]['content'] else 'FAIL')
"
```

---

## 14. Plusieurs MCPs — doublon d'ID server:mcp:None (CONNU)

**Symptome** : Quand plusieurs MCP servers sont configurés (ex: Open Data + Grist), un seul apparaît dans le sélecteur d'outils. L'API `/api/v1/tools/` montre les deux mais avec le même ID `server:mcp:None`.

**Cause racine** : OWUI v0.8.12 génère l'ID du MCP tool à partir de `server.info.name` retourné lors de la connexion `initialize`. Si le serveur ne retourne pas cette info (connexion paresseuse, timeout, ou protocole incompatible), l'ID est `None`. Deux MCPs avec le même ID = un seul affiché (dédup).

**Workaround possible** : Utiliser un **agrégateur MCP** — un seul service qui proxifie les requêtes vers plusieurs MCPs backend. OWUI ne voit qu'un seul MCP avec un ID unique, et l'agrégateur route vers le bon backend selon le tool appelé.

**Alternative** : Attendre OWUI > 0.8.12 qui gère mieux les IDs de MCP servers multiples.

**Note** : Les MCPs fonctionnent quand même — le LLM peut les appeler. C'est juste l'affichage dans le sélecteur d'outils qui est affecté. Activer le MCP visible et le LLM aura accès aux tools des deux serveurs.

---

# Guide de debug OWUI

## Erreurs invisibles dans les logs

OWUI masque les erreurs de streaming/filters derriere `log.debug` dans `main.py` ligne ~1816. Pour les voir :

```bash
docker exec owuicore-openwebui-1 python3 -c "
c = open('/app/backend/open_webui/main.py').read()
c = c.replace(
    \"log.debug(f'Error processing chat payload: {e}')\",
    \"log.exception(f'Error processing chat payload: {e}')\"
)
open('/app/backend/open_webui/main.py', 'w').write(c)
"
docker restart owuicore-openwebui-1
```

Cela transforme les erreurs silencieuses en tracebacks complets dans les logs.

## Ou sont les fichiers uploades

```
/app/backend/data/uploads/{file_id}_{filename}
```

## Ou sont les valves des tools/filters

```sql
-- Tools
SELECT id, valves FROM tool;
-- Filters
SELECT id, valves FROM function;
```

Les valves sont appliquees au runtime via `Functions.get_function_valves_by_id()`. Elles survivent aux restarts mais sont ecrasees par `ensure-tools` si le tool est re-enregistre avec des valves vides.

## Comment OWUI passe les fichiers aux filters

Les fichiers uploades sont dans `body["metadata"]["files"]`, PAS dans `messages[-1]["files"]`. Structure :

```json
{
  "type": "file",
  "id": "uuid",
  "file": {
    "id": "uuid",
    "filename": "photo.jpg",
    "meta": {
      "content_type": "image/jpeg",
      "name": "photo.jpg",
      "size": 1864952
    }
  }
}
```

**Attention** : `body["metadata"]["files"]` peut etre `null` (pas `[]`). Toujours utiliser `or []`.

## DOMPurify supprime les scripts dans les iframes

Les HTMLResponse des tools sont affichees dans des iframes sandboxees. DOMPurify supprime tous les `<script>` tags. Impossible d'utiliser postMessage ou ResizeObserver pour redimensionner l'iframe. Utiliser `min-height` CSS comme workaround.

Ref : https://github.com/open-webui/open-webui/discussions/17802

## Tester un filter en isolation

```bash
docker exec owuicore-openwebui-1 python3 -c "
import asyncio, sqlite3, json
db = sqlite3.connect('/app/backend/data/webui.db')
content = db.execute('SELECT content FROM function WHERE id=\"FILTER_ID\"').fetchone()[0]
valves_str = db.execute('SELECT valves FROM function WHERE id=\"FILTER_ID\"').fetchone()[0]
exec(content)
f = Filter()
if valves_str:
    for k, v in json.loads(valves_str).items(): setattr(f.valves, k, v)
body = {'messages': [{'role': 'user', 'content': 'test'}], 'metadata': {'files': []}}
result = asyncio.run(f.inlet(body))
print(result['messages'][-1]['content'][:200])
"
```

## Patches OWUI appliques au demarrage

Les patches sont dans l'entrypoint `docker-compose.yml` (Docker) et `lifecycle.postStart` (k8s) :

1. **MCP label** : `server.get('name', 'MCP Tool Server')` → utilise le nom de la connexion
2. **Image upload** : skip le processing RAG pour les images (gerees par le filter vision)
3. **Error visibility** (optionnel) : `log.debug` → `log.exception` dans main.py
