# Rotating Proxy Cluster

Cluster de proxys HTTP rotatifs sur Scaleway pour anonymiser les requetes sortantes (SearXNG, websnap, etc.).

## Architecture

```
Client (SearXNG pod / curl)
    |
    v
HAProxy :3128  (VM1, round-robin TCP)
    |
    +---> Squid :3129 (VM1, 5 IPs)
    +---> Squid :3129 (VM2, 5 IPs)
    +---> Squid :3129 (VM3, 5 IPs)
    +---> Squid :3129 (VM4, 5 IPs)
```

- **4 VMs** : 2 zones FR (fr-par-1, fr-par-2) x 2 VMs
- **20 IPs rotatives** : 5 IPs par VM, rotation round-robin via Squid
- **HAProxy** sur VM1 : load-balance entre les 4 Squid backends
- **Authentification** : Basic Auth requise (user + API key)

## Deploiement

```bash
# Deployer le cluster
./deploy-proxy.sh deploy

# Voir le statut + tester la rotation
./deploy-proxy.sh status

# Supprimer toutes les ressources
./teardown-proxy.sh              # interactif
./teardown-proxy.sh --dry-run    # apercu sans suppression
./teardown-proxy.sh --force      # sans confirmation
```

## Configuration

### Kubernetes (namespace miraiku)

Un service `rotating-proxy` pointe vers le HAProxy. Les pods utilisent :

```yaml
env:
  - name: HTTP_PROXY
    value: "http://owui:<API_KEY>@rotating-proxy:3128"
  - name: HTTPS_PROXY
    value: "http://owui:<API_KEY>@rotating-proxy:3128"
  - name: NO_PROXY
    value: "localhost,127.0.0.1,keycloak,openwebui,pipelines,search-valkey"
```

### Docker Compose (dev local)

Ajouter dans `.env` :

```
PROXY_URL=http://owui:<API_KEY>@163.172.132.16:3128
```

SearXNG utilisera automatiquement le proxy via `HTTP_PROXY` / `HTTPS_PROXY`.
Si `PROXY_URL` est vide, SearXNG fonctionne sans proxy.

## Monitoring

- **HAProxy stats** : `http://<VM1_IP>:8404/stats`
- **Test rapide** :
  ```bash
  # Doit retourner une IP differente a chaque appel
  curl --proxy "http://owui:<KEY>@<VM1_IP>:3128" https://httpbin.org/ip
  ```

## Securite

- Port 3128 ouvert mais protege par Basic Auth (Squid `proxy_auth`)
- Sans credentials valides : HTTP 407
- Le fichier htpasswd est sur chaque VM dans `/etc/squid/proxy_users`
- La cle API est dans les env vars des deployments k8s et dans le `.env` local

## Cout

~72 EUR/mois (4 x DEV1-S + 16 IPs flexibles).
