# Search Architecture

This repository deploys SearXNG inside Kubernetes, but it does not pretend that a single Scaleway Kapsule cluster can natively span several regions for egress.

For local developer testing, the repository also provides a lighter Docker Compose profile with:

- `searxng`
- `search-valkey`
- direct local egress
- limiter disabled to avoid localhost false positives
- a JSON API on `http://localhost:8083/search`

Start it with:

```bash
docker compose --profile search up -d search-valkey searxng
docker compose up -d openwebui
bash scripts/test_local_search.sh
```

Open WebUI is configured to consume this local SearXNG service through the internal Compose URL `http://searxng:8080/search` when the `search` profile is running.

## In-Cluster Components

The Kubernetes stack now includes:

- `searxng` as the search frontend
- `search-valkey` as the limiter/cache backend for multi-replica SearXNG
- an ingress on `SEARXNG_HOST`

The upstream configuration is rendered from [`k8s/base/configmap-searxng.yaml`](../k8s/base/configmap-searxng.yaml).

## Outbound Egress Design

SearXNG is configured with three outbound proxies:

- `SEARXNG_OUTBOUND_PROXY_PAR_URL`
- `SEARXNG_OUTBOUND_PROXY_AMS_URL`
- `SEARXNG_OUTBOUND_PROXY_WAW_URL`

These proxies are expected to live in different Scaleway regions, for example:

- Paris
- Amsterdam
- Warsaw

This split is deliberate. Kapsule clusters are regional, so a clean multi-region search-egress architecture keeps:

- the search pods inside one Kubernetes cluster
- the outbound proxy pools outside that cluster, one pool per target region

## Why The Initial Requirement Needed Amendment

The original request asked for three exit nodes and ten public egress IPs per node.

The practical amendment retained in this repository is:

- if ten total addresses per region is acceptable, a dual-stack design can use up to five routed IPv4 addresses plus five public IPv6 addresses on one Scaleway Instance
- if ten IPv4 addresses are strictly required in one region, use two proxy VMs per region or another regional egress pool instead of assuming one node can own ten IPv4 egress addresses by itself

## Recommended Proxy Topology

An elegant pattern is:

1. one regional proxy pool in each region
2. each regional pool rotates across its local egress addresses
3. SearXNG distributes requests across the three regional proxy endpoints

This repository leaves the regional proxy implementation open on purpose. A forward-proxy fleet based on Squid, HAProxy plus dedicated local forwarders, or another hardened proxy layer is acceptable, as long as:

- authentication is enforced between SearXNG and the proxies
- logs are minimized and retained only as needed
- TLS is used on any cross-region control path
- the egress IP rotation policy stays explicit and auditable

## Search Engine Policy

The default SearXNG profile intentionally favors engines aligned with privacy-oriented values:

- DuckDuckGo
- Brave
- Startpage
- Qwant
- Mojeek
- Wikipedia

Bing and Google are kept with lower weights. This keeps the privacy-oriented engines first while still making Google available for broader general web coverage. Google remains the least preferred mainstream engine here because it is more likely to trigger anti-bot countermeasures in self-hosted metasearch deployments.

## Reference Material

The architecture above follows these upstream references:

- Scaleway product availability and regions: https://www.scaleway.com/en/docs/account/reference-content/products-availability/
- Scaleway Kapsule API regions: https://www.scaleway.com/en/developers/api/kubernetes/
- Scaleway flexible IP usage on Instances: https://www.scaleway.com/en/docs/instances/how-to/use-flexips/
- SearXNG outgoing proxy behavior: https://docs.searxng.org/admin/settings/settings_outgoing.html
- SearXNG limiter and Valkey requirements: https://docs.searxng.org/admin/searx.limiter and https://docs.searxng.org/admin/settings/settings_valkey.html
