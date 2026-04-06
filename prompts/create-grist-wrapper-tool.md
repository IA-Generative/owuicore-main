Tu dois créer un wrapper tool OWUI pour l'API Grist (grist.numerique.gouv.fr), le déployer sur Docker et k8s, et produire un rapport.

## Contexte
- Le MCP Grist (owuitools-gristmcp) tourne mais OWUI v0.8.12 ne pré-charge pas les specs MCP → le LLM ne peut pas appeler les tools (bug #15 dans docs/bugs-connus.md)
- Le workaround : un wrapper tool OWUI qui appelle l'API REST Grist directement via httpx
- L'API REST Grist fonctionne : `curl -H "Authorization: Bearer KEY" https://grist.numerique.gouv.fr/api/orgs`
- Repos dans ~/Documents/GitHub/ : owuicore-main, owuitools-gristmcp
- Le pattern de tool OWUI est dans owuitools-dataview/openwebui/dataview_tool.py (HTMLResponse + context)

## Ce qu'il faut faire

### 1. Créer le wrapper tool
Fichier : `~/Documents/GitHub/owuitools-gristmcp/openwebui/grist_tool.py`

Le tool doit :
- Avoir des Valves : `grist_api_url` (default: https://grist.numerique.gouv.fr/api), `grist_api_key` (default: ""), `timeout` (default: 60)
- La clé API Grist est dans la Valve `grist_api_key` (configurable par l'admin dans l'UI OWUI)
- Exposer ces fonctions :
  - `grist_navigate(org_name="", workspace_name="", doc_name="")` — navigation : liste les orgs, ou les workspaces d'un org, ou les docs d'un workspace. Retourne HTMLResponse + context.
  - `grist_read_table(doc_id, table_id, limit=50)` — lit les records d'une table. Retourne HTMLResponse + context.
  - `grist_query(doc_id, sql)` — exécute un SELECT SQL. Retourne HTMLResponse + context.
  - `grist_schema(doc_id, table_id="")` — liste les tables d'un doc, ou les colonnes d'une table.
  - `grist_export(doc_id, table_id, format="csv")` — exporte une table.

Pattern HTMLResponse (comme dataview) :
```python
from fastapi.responses import HTMLResponse
return (
    HTMLResponse(content=html_table, headers={"Content-Disposition": "inline"}),
    {"summary": "...", "_instructions": "..."},
)
```

API Grist REST :
- `GET /api/orgs` — liste les organisations
- `GET /api/orgs/{org_id}/workspaces` — liste les workspaces (inclut les docs)
- `GET /api/docs/{doc_id}/tables` — liste les tables
- `GET /api/docs/{doc_id}/tables/{table_id}/columns` — colonnes
- `GET /api/docs/{doc_id}/tables/{table_id}/records` — records
- `GET /api/docs/{doc_id}/sql?q=SELECT...` — requête SQL
- `GET /api/docs/{doc_id}/download/csv?tableId={table_id}` — export CSV
- Header auth : `Authorization: Bearer {api_key}`

### 2. Créer owui-plugin.yaml
Pour que ensure-tools découvre et enregistre le tool :
```yaml
name: gristmcp
version: "1.0.0"
tools:
  entries:
    - id: grist
      source_file: openwebui/grist_tool.py
      service_name: grist-mcp
      service_port: 8000
```

### 3. Ajouter dans PLUGIN_PATHS
Dans owuicore-main/.env, ajouter `../owuitools-gristmcp` à PLUGIN_PATHS.
Dans owuicore-main/.env.example aussi.

### 4. Mettre à jour le system prompt
Dans owuicore-main/scripts/ensure_tools.py, remplacer les instructions Grist MCP par :
```
"Si l'utilisateur parle de Grist, de tableaux collaboratifs, ou de donnees internes :\n"
"- `grist_navigate()` → lister les organisations, workspaces et documents\n"
"- `grist_navigate(org_name='SDID')` → lister les workspaces d'une organisation\n"
"- `grist_schema(doc_id)` → lister les tables d'un document\n"
"- `grist_read_table(doc_id, table_id)` → lire le contenu d'une table\n"
"- `grist_query(doc_id, sql)` → requete SQL sur un document\n"
"- `grist_export(doc_id, table_id)` → exporter en CSV\n\n"
```

### 5. Ajouter les tests dans le cahier de tests
Dans owuicore-main/docs/cahier-de-tests.md, section 11 (Grist), mettre à jour les tests T11.1-T11.5 pour utiliser le wrapper tool au lieu du MCP.

### 6. Mettre à jour deploy-plugins-docker.sh
Vérifier que owuitools-gristmcp est dans la liste PLUGINS du script.

### 7. Déployer sur Docker
```bash
cd ~/Documents/GitHub/owuicore-main
./deploy/deploy-plugins-docker.sh
```

### 8. Configurer les valves Grist
La clé API Grist : `b399debefbfe0490e8b187fe2295db66c64eccbb`
L'URL : `https://grist.numerique.gouv.fr/api`
Configurer via la DB :
```bash
docker exec owuicore-openwebui-1 python3 -c "
import sqlite3, json
db = sqlite3.connect('/app/backend/data/webui.db')
db.execute('UPDATE tool SET valves=? WHERE id=\"grist\"', (json.dumps({
    'grist_api_url': 'https://grist.numerique.gouv.fr/api',
    'grist_api_key': 'b399debefbfe0490e8b187fe2295db66c64eccbb',
    'timeout': 60,
}),))
db.commit()
"
```

### 9. Tester
- T11.1 : `grist_navigate()` → liste les 3 orgs (Personal, SDID, templates)
- T11.2 : `grist_navigate(org_name="SDID")` → liste les docs (Gestion PI SDID, etc.)
- T11.3 : `grist_read_table("qXWzdtyGgNh2T64Ti1SQfc", "Epics")` → affiche les epics
- T11.4 : `grist_query("qXWzdtyGgNh2T64Ti1SQfc", "SELECT * FROM Epics LIMIT 5")`
- T11.5 : `grist_export("qXWzdtyGgNh2T64Ti1SQfc", "Epics")` → CSV

### 10. Build et deploy k8s
Le wrapper tool est dans le même repo que grist-mcp. Le Dockerfile reste le même (MCP server). Le tool OWUI est enregistré par ensure-tools via owui-plugin.yaml.

### 11. Rapport
Stocker dans `~/Documents/GitHub/owuicore-main/docs/reports/grist-wrapper-YYYYMMDD.md` :
- Date, heure
- Fichiers créés/modifiés
- Résultats des tests (PASS/FAIL)
- Erreurs rencontrées
- Commits et push

### Fichiers de référence
- Pattern tool : ~/Documents/GitHub/owuitools-dataview/openwebui/dataview_tool.py
- Pattern plugin : ~/Documents/GitHub/owuitools-dataview/owui-plugin.yaml
- Ensure tools : ~/Documents/GitHub/owuicore-main/scripts/ensure_tools.py
- Bugs connus : ~/Documents/GitHub/owuicore-main/docs/bugs-connus.md
- Deploy plugins : ~/Documents/GitHub/owuicore-main/deploy/deploy-plugins-docker.sh
