# Synthèse d'apprentissage — Restructuration Miraiku

> Session du 4-5 avril 2026. Ce document capture les enseignements techniques
> tirés de la restructuration du monorepo grafrag-experimentation en architecture
> modulaire, du déploiement K8s sur Scaleway, et de l'intégration MCP.

---

## 1. Architecture modulaire (socle + features)

### Ce qui a marché
- **Réseau Docker `owui-net`** (external) : simple, efficace. Le socle le crée, les features le rejoignent. Connectivité cross-repo validée.
- **Profils Docker Compose** pour la coexistence : `legacy` pour le monorepo, défaut pour le mode modulaire. Chemin de retour simple.
- **`owui-plugin.yaml`** comme contrat unique entre feature et socle. Chaque feature reste autonome.
- **Volume nommé persistant** (`owui-socle-openwebui-data`) pour la DB OpenWebUI — survit aux `down/up`.

### Pièges rencontrés
- **`PersistentConfig` d'OpenWebUI** : les env vars ne sont lues qu'au premier boot. Si la DB a déjà stocké une valeur, l'env var est ignorée. Solution : soit `ENABLE_PERSISTENT_CONFIG=false`, soit passer par l'API REST admin.
- **Custom `index.html`** : monter un index.html custom via bind mount casse l'UI après un upgrade de version (les hashes JS changent). Ne pas monter l'index.html, utiliser uniquement le CSS custom.
- **`ENABLE_API_KEYS`** (avec un S) : le nom exact de la variable compte. `ENABLE_API_KEY` (sans S) est ignoré silencieusement.

---

## 2. Déploiement K8s sur Scaleway

### Ce qui a marché
- Migration big-bang du namespace `grafrag` vers `miraiku` en ~15 minutes.
- Copie des secrets entre namespaces via `kubectl get secret -o json | jq | kubectl apply`.
- Rendu des manifests via `sed` sur les fichiers rendered existants.
- Tous les services (14 pods) ont démarré correctement.

### Pièges rencontrés
- **SearXNG `SEARXNG_PORT` collision** : Kubernetes injecte automatiquement `<SERVICE_NAME>_PORT=tcp://10.x.x.x:80` pour chaque service. Si le service s'appelle `searxng`, la variable `SEARXNG_PORT` est écrasée et Granian (le serveur WSGI) crash avec `invalid integer`. Solution : renommer le service (`search-engine` au lieu de `searxng`).
- **Namespace dans les YAML avec guillemets** : `namespace: "grafrag"` vs `namespace: grafrag`. Le `sed 's/namespace: grafrag/...'` ne matche pas la version avec guillemets. Toujours inclure les deux patterns.
- **PVC RWO (ReadWriteOnce)** : un PVC RWO ne peut être attaché qu'à un seul node. Le rolling update crée le nouveau pod avant de supprimer l'ancien → `Multi-Attach error`. Solution : `scale --replicas=0` puis `scale --replicas=1`.
- **Images ARM vs AMD64** : les images buildées sur macOS M-series sont ARM. Le cluster K8s Scaleway est AMD64. Erreur : `exec format error`. Solution : `docker buildx build --platform linux/amd64 --push`.
- **`runAsNonRoot` + PVC** : le volume est monté en root, l'app tourne en UID 1000 → `unable to open database file`. Solution : fixer le UID dans le Dockerfile (`useradd -u 1000`) + `fsGroup: 1000` dans le pod securityContext.
- **Espace disque** : les images Docker s'accumulent. Keycloak a crashé avec `No space left on device` sur `/tmp/vertx-cache`. Solution : `docker system prune` régulier.

---

## 3. Génération d'images (HuggingFace)

### Ce qui a marché
- **Proxy FastAPI** (`image-gen/app.py`) qui traduit OpenAI `/v1/images/generations` vers l'API HuggingFace Inference. Simple et efficace.
- **FLUX.1-schnell** et **SDXL** fonctionnent via l'API Inference gratuite.
- OpenWebUI se connecte au proxy comme un backend "OpenAI" pour la génération d'images.

### Pièges rencontrés
- **URL API HuggingFace changée** : `api-inference.huggingface.co` → `router.huggingface.co/hf-inference/models`. L'ancienne URL retourne un redirect permanent.
- **SD 3.5 Large** nécessite une licence acceptée sur HuggingFace + crédits prépayés (provider fal-ai). Pas disponible en gratuit.
- **FLUX.1-dev** deprecated sur HF Inference.
- **Config image gen dans OWUI** : même problème de `PersistentConfig`. La config est sauvée en DB au premier boot. Il faut pousser via l'API admin (`/api/v1/images/config/update`) avec TOUS les champs (le body doit être complet, pas un patch partiel).
- **Crash DB** : insérer un `int` epoch dans `created_at` au lieu d'un ISO datetime string → crash au boot d'OWUI (`fromisoformat: argument must be str`). Solution : supprimer la ligne corrompue via un container temporaire monté sur le volume.

---

## 4. Moteurs de recherche (SearXNG)

### Ce qui a marché
- **Qwant** : meilleur moteur pour les résultats français et sites gouv.fr. Poids 1.6.
- **Brave Search API** (`braveapi` engine) : avec API key, pas de rate limit. Le seul moteur qui ne se fait pas bloquer.
- **Startpage** : bon fallback, proxy Google sans tracking.

### Pièges rencontrés
- **Rate limiting agressif** : DuckDuckGo (CAPTCHA), Google (403), Brave scraping (429). Tous suspendus après ~10 requêtes en séquence rapide. Solution : réduire le nombre d'engines actifs, utiliser les API keys quand disponibles.
- **Engines custom xpath/json** : les engines `xpath` et `json_engine` de SearXNG nécessitent un `search_url` obligatoire. Sans ce champ → engine désactivé silencieusement au boot. Erreur visible uniquement dans les logs.
- **Google `extra_params` + `as_sitesearch`** : ne fonctionne pas pour restreindre les résultats à un domaine. Google bloque les requêtes non-standard de SearXNG.
- **Brave `goggles_id` hack** : ne fonctionne pas pour le filtrage par site.
- **`braveapi` vs `brave`** : ce sont deux engines distincts. `brave` = scraping (rate limited), `braveapi` = API key (fiable). La clé doit être en clair dans `settings.yml` (SearXNG ne fait pas d'interpolation `${VAR}`).
- **`settings.yml` avec secrets** : gitignore le fichier et fournir un `.example`.

---

## 5. Intégration MCP (Model Context Protocol)

### Ce qui n'a pas marché (et pourquoi)

L'intégration MCP entre les services feature (tchap-reader, browser-skill) et OpenWebUI a été la partie la plus complexe et n'est pas encore fonctionnelle. Voici les problèmes empilés :

1. **Transport protocol mismatch** : OWUI v0.8.12 (MCP SDK 1.26) utilise le **Streamable HTTP** transport (`streamablehttp_client`). Nos premiers serveurs MCP exposaient du SSE → incompatible (POST sur GET endpoint = 405).

2. **`streamable_http_app()` + FastAPI sub-mount** : la Starlette app retournée par `streamable_http_app()` a besoin de son propre lifespan pour initialiser un `TaskGroup`. Montée comme sub-app dans FastAPI, le lifespan n'est pas propagé → `RuntimeError: Task group is not initialized`.

3. **Solution : process séparé** : lancer le MCP server sur un port dédié (8088) via `multiprocessing.Process` dans un `entrypoint.py`. Le container expose deux ports : 8087/8000 (API) + 8088 (MCP).

4. **DNS rebinding protection** : le MCP SDK (v1.26+) valide le header `Host` par défaut. En interne K8s, les requêtes arrivent avec `Host: browser-use:8088` qui n'est pas dans la whitelist (`localhost`, `127.0.0.1`). → `421 Invalid Host header`. Solution : monkey-patch du `TransportSecurityMiddleware.__init__` pour forcer `enable_dns_rebinding_protection=False`.

5. **`transport_security` kwarg** : ajouté dans une version plus récente du SDK (>1.27). Les versions 1.26 et 1.27 de `streamable_http_app()` n'acceptent que `self` → `TypeError: unexpected keyword argument`.

6. **Accept header** : le Streamable HTTP requiert `Accept: application/json, text/event-stream`. Sans ce header → `406 Not Acceptable`.

7. **Client OWUI `connect()` retourne `None`** : même quand le serveur répond correctement au handshake, le client OWUI ne parse pas les tools. Probablement une incompatibilité subtile dans la négociation de protocole.

### État actuel MCP
- Les endpoints MCP sont **accessibles** (`http://browser-use:8088/mcp` répond au POST)
- La **DNS rebinding protection est désactivée** via monkey-patch
- Le **handshake initialize** fonctionne partiellement (406 → résolu, 421 → résolu)
- Le **client OWUI ne parse pas les tools** correctement → `Initialized 0 tool server(s)`

### Recommandation MCP
- Attendre une version d'OWUI (0.9+) qui expose un meilleur support MCP serveur-à-serveur en HTTP interne
- En attendant, les **tools OWUI injectés en DB** fonctionnent pour le tool calling classique
- Le **modèle Scaleway branché directement** dans OWUI (pas via pipeline) permettra le tool calling natif avec ces tools DB

---

## 6. OpenWebUI — Modèles et Tools

### Architecture modèles
- **Modèle générique** (Scaleway direct via connexion OpenAI dans OWUI) : supporte tool calling natif + futur MCP
- **Pipelines spécialisées** (graphrag, anef) : logique métier custom, pas de tool calling OWUI

### Tools OWUI en DB
- Les tools sont injectés dans la table `tool` de la DB SQLite d'OWUI
- Les filters dans la table `function` (type=filter)
- Le `user_id` peut être vide pour les tools auto-registered
- Les URLs dans le code source des tools doivent correspondre aux noms de services K8s (`http://tchap-reader:8087` et non `http://host.docker.internal:8087`)
- Les tools doivent être **associés au modèle** via la table `model` (champ `meta.toolIds`) pour que le LLM les utilise automatiquement
- Alternative : l'utilisateur active manuellement les tools dans l'interface chat

---

## 7. Checkliste déploiement

Pour chaque nouveau déploiement K8s :

- [ ] Build `--platform linux/amd64` (pas ARM)
- [ ] Push vers le registry Scaleway
- [ ] Vérifier que les secrets existent dans le namespace cible
- [ ] Vérifier que le registry secret existe dans le namespace
- [ ] Pour les PVC RWO : scale à 0 avant de changer l'image, puis scale à 1
- [ ] Vérifier les logs après démarrage (`kubectl logs`)
- [ ] Tester le healthcheck depuis un autre pod (`kubectl exec`)
- [ ] Vérifier la connectivité cross-service
- [ ] Ne pas nommer les services comme des variables d'env K8s connues

---

## 8. Tokens et secrets exposés dans cette session

**À révoquer immédiatement :**
- Token HuggingFace : `hf_REVOKED_rotate_this_token`
- Clé API Brave Search : `REVOKED_rotate_this_key`
- API keys OWUI créées dans la session (dans la DB K8s)

---

## 9. Fichiers clés modifiés

| Repo | Fichiers | Changement |
|------|----------|------------|
| **experimentation-owui** (nouveau) | tout | Socle OWUI complet |
| **grafrag-experimentation** | `docker-compose.yml`, `deploy-k8s.sh`, `kustomization.yaml`, `owui-plugin.yaml` | Feature mode + legacy fallback |
| **tchap-reader** | `Dockerfile`, `app/main.py`, `app/mcp_server.py`, `app/mcp_app.py`, `entrypoint.py`, `owui-plugin.yaml`, `docker-compose.yaml` | MCP server + owui-net |
| **browser-skill-owui** | `docker/Dockerfile`, `app/main.py`, `app/mcp_server.py`, `app/mcp_app.py`, `entrypoint.py`, `owui-plugin.yaml`, `docker-compose.yaml` | MCP server + owui-net |
| **anef-knowledge-assistant** | `owui-plugin.yaml`, `docker-compose.yml` | owui-net |
