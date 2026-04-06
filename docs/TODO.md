# TODO — Évolutions planifiées

## Priorité haute

### Recherche web enrichie avec sources structurées
**Objectif** : Produire des réponses web structurées avec tableau, citations sourcées `【1†L0-L4】`, et résumé — comme les outils de recherche avancés (Perplexity, etc.).

**Option A — System prompt** (rapide, 1h)
- Ajouter des instructions dans le system prompt pour que le LLM structure ses réponses web avec :
  - Un tableau synthétique (Aspect / Situation / Sources)
  - Des citations numérotées renvoyant aux sources SearXNG
  - Un résumé en bullet points
- Avantage : pas de code, juste du prompt engineering
- Limite : dépend de la qualité du LLM, pas de contrôle sur les sources

**Option B — Tool `web_research`** (complet, 1-2j)
- Nouveau tool qui :
  1. Appelle SearXNG pour les top 5-10 résultats
  2. Appelle websnap sur chaque URL pour extraire le contenu complet
  3. Retourne un HTMLResponse avec les sources en iframe scrollable
  4. Envoie un context riche au LLM avec le contenu extrait et les instructions de citation
- Avantage : contrôle total, contenu extrait réel (pas juste les snippets SearXNG)
- Complexité : orchestration multi-tool, gestion du timeout, pagination

### HTMLResponse pour Tchap (en cours)
- `tchap_rooms`, `tchap_search_rooms`, `tchap_analyze` retournent déjà des HTMLResponse
- Reste à tester en conditions réelles avec des salons actifs
- Améliorer la pseudonymisation dans l'iframe HTML

### Vision filter — images volumineuses
- Le filter v3.0 fonctionne en isolation mais peut timeout sur de grosses images (>1Mo)
- Ajouter un redimensionnement automatique avant l'envoi à pixtral
- Compresser en JPEG qualité 80 si l'image dépasse 500Ko en base64

## Priorité moyenne

### Séparer le filter vision de websnap
- Le filter vision (`openwebui_vision_filter.py`) est dans le repo websnap
- Devrait être dans son propre repo ou dans owuicore (c'est indépendant de websnap)
- Le filter appelle Scaleway pixtral directement, aucune dépendance websnap

### Déployer dataview + vision + tchap sur k8s
- Rebuilder les images amd64 pour k8s
- Sync owui-state.json + valves k8s
- Appliquer les patches OWUI (MCP label, image upload skip)
- Tester les tools de bout en bout sur Scaleway

### Désactiver le RAG sur les fichiers tabulaires
- OWUI fait du RAG (embeddings) sur chaque fichier uploadé, même les CSV/XLSX
- Le filter dataview_auto_preview s'en occupe déjà
- Double traitement inutile qui consomme du quota embeddings
- Investiguer s'il y a un moyen de skip le RAG pour certains content types

### Améliorer le query engine dataview
- Le LLM traduit parfois mal les questions en opérations pandas
- Ajouter plus d'exemples dans le prompt du query engine
- Supporter les opérations de jointure entre fichiers
- Ajouter des opérations de date (filtrer par période)

## Priorité basse

### Upgrade OWUI > 0.8.12
- Résoudrait les workarounds :
  - Bug #10 : reasoning_tags=false (champ reasoning séparé)
  - iframe height fixe (DOMPurify supprime les scripts)
- Tester d'abord en local avant de déployer en k8s
- Risque de régression sur les patches existants

### Mutualiser les helpers HTML
- `_render_table_html` est dupliqué entre dataview et tchapreader
- Créer un package `owui-html-helpers` réutilisable
- Ou un fichier partagé dans owuicore

### MCP data.gouv.fr vs data_search
- Le MCP est réactivé et cohabite avec nos tools REST
- Évaluer si le MCP apporte une vraie valeur ajoutée vs data_search
- Si oui : garder les deux (MCP pour exploration, REST pour upload/preview)
- Si non : désactiver le MCP et simplifier

### Monitoring SearXNG
- Script `check-search-engines.sh` existe
- Ajouter un cron ou un healthcheck qui alerte si un moteur tombe
- Intégrer dans le smoke test
