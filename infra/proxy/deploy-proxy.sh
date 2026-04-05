#!/usr/bin/env bash
# Deploy a rotating proxy cluster on Scaleway
# 2 VMs per datacenter × 2 French datacenters × 5 IPs each = 20 IPs
#
# Usage:
#   ./deploy-proxy.sh               # Deploy
#   ./deploy-proxy.sh teardown      # Destroy
#   ./deploy-proxy.sh status        # Show status + test rotation
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Config ─────────────────────────────────────────
PROJECT_NAME="owui-proxy"
INSTANCE_TYPE="DEV1-S"
IMAGE="ubuntu_noble"
SCW_PROJECT_ID="a9158aac-8404-46ea-8bf5-1ca048cd6ab4"  # EricTiquet
ZONES=("fr-par-1" "fr-par-2")
VMS_PER_ZONE=2
IPS_PER_VM=5
PROXY_PORT=3128

TAG_PROJECT="project=${PROJECT_NAME}"
TAG_ROLE="role=rotating-http-proxy-squid"
TAG_PURPOSE="purpose=anti-bot-bypass-for-websnap-and-searxng"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
log()  { echo -e "${GREEN}[proxy]${NC} $*"; }
warn() { echo -e "${YELLOW}[proxy]${NC} $*"; }
err()  { echo -e "${RED}[proxy]${NC} $*" >&2; }

# ── Security Group ─────────────────────────────────

create_security_group() {
    local zone=$1

    local existing
    existing=$(scw instance security-group list zone="$zone" -o json 2>/dev/null \
        | jq -r ".[] | select(.name==\"$PROJECT_NAME\") | .id" | head -1)
    if [ -n "$existing" ]; then
        log "[$zone] SG exists: ${existing:0:8}..." >&2
        echo "$existing"
        return
    fi

    log "[$zone] Creating security group..." >&2
    local sg_id
    sg_id=$(scw instance security-group create \
        zone="$zone" name="$PROJECT_NAME" \
        project-id="$SCW_PROJECT_ID" \
        inbound-default-policy=drop outbound-default-policy=accept \
        stateful=true -o json 2>/dev/null | jq -r '.security_group.id // .id')

    for port in 22 3128 3129 8404; do
        scw instance security-group create-rule \
            zone="$zone" security-group-id="$sg_id" \
            protocol=TCP direction=inbound action=accept \
            dest-port-from=$port 2>/dev/null > /dev/null
    done

    log "[$zone] SG created: ${sg_id:0:8}..." >&2
    echo "$sg_id"
}

# ── Create VM ──────────────────────────────────────

create_vm() {
    local zone=$1 index=$2 sg_id=$3
    local name="${PROJECT_NAME}-${zone}-${index}"

    log "[$zone] Creating $name..." >&2
    local server_json server_id
    server_json=$(scw instance server create \
        zone="$zone" name="$name" type="$INSTANCE_TYPE" image="$IMAGE" \
        project-id="$SCW_PROJECT_ID" \
        tags.0="$TAG_PROJECT" tags.1="$TAG_ROLE" tags.2="$TAG_PURPOSE" \
        tags.3="zone=$zone" tags.4="index=$index" \
        security-group-id="$sg_id" \
        cloud-init=@"$SCRIPT_DIR/cloud-init-squid.yaml" \
        -o json 2>&1)
    server_id=$(echo "$server_json" | jq -r '.id // empty')
    if [ -z "$server_id" ]; then
        err "[$zone] $name: server create failed:"
        err "$server_json"
        exit 1
    fi

    log "[$zone] $name booting (${server_id:0:8}...)..." >&2
    scw instance server wait "$server_id" zone="$zone" > /dev/null 2>&1

    local get_json primary_ip
    get_json=$(scw instance server get "$server_id" zone="$zone" -o json 2>&1)
    primary_ip=$(echo "$get_json" | jq -r '(.public_ips[0].address // .public_ip.address) // empty')
    if [ -z "$primary_ip" ]; then
        err "[$zone] $name: failed to get public IP"
        err "server get output: $(echo "$get_json" | head -3)"
        exit 1
    fi
    log "[$zone] $name IP1: $primary_ip" >&2

    for i in $(seq 2 "$IPS_PER_VM"); do
        local ip_id ip_addr
        ip_id=$(scw instance ip create zone="$zone" project-id="$SCW_PROJECT_ID" -o json 2>/dev/null | jq -r '.ip.id // .id')
        scw instance ip attach "$ip_id" zone="$zone" server-id="$server_id" 2>/dev/null > /dev/null
        ip_addr=$(scw instance ip get "$ip_id" zone="$zone" -o json 2>/dev/null | jq -r '.ip.address // .address')
        log "[$zone] $name IP${i}: $ip_addr" >&2
    done

    echo "$server_id|$zone|$primary_ip"
}

# ── Configure Squid on VM ──────────────────────────

configure_squid() {
    local ip=$1
    log "Configuring Squid on $ip..."

    # Wait SSH
    for _ in $(seq 1 40); do
        ssh -o StrictHostKeyChecking=no -o ConnectTimeout=3 -o BatchMode=yes \
            "root@${ip}" true 2>/dev/null && break
        sleep 5
    done

    ssh -o StrictHostKeyChecking=no "root@${ip}" bash <<'REMOTE'
set -e
cloud-init status --wait 2>/dev/null || sleep 45

/usr/local/bin/configure-flex-ips.sh
/usr/local/bin/configure-squid-ips.sh

# Add port 3129 for HAProxy + open access
if ! grep -q "http_port 3129" /etc/squid/squid.conf; then
    sed -i 's/http_port 3128/http_port 3128\nhttp_port 3129/' /etc/squid/squid.conf
    sed -i '/http_access deny all/i acl proxy_clients src 0.0.0.0/0\nhttp_access allow proxy_clients' /etc/squid/squid.conf
fi
systemctl restart squid

N=$(ip -4 addr show scope global | grep -c 'inet ')
echo "Squid OK — $N IPs"
REMOTE
}

# ── HAProxy on VM1 ─────────────────────────────────

configure_haproxy() {
    local vm1_ip=$1; shift
    local all_ips=("$@")

    local backends=""
    for ip in "${all_ips[@]}"; do
        [ -n "$backends" ] && backends="${backends},"
        backends="${backends}${ip}:3129"
    done

    log "HAProxy on $vm1_ip (${#all_ips[@]} backends across ${#ZONES[@]} zones)..."

    ssh -o StrictHostKeyChecking=no "root@${vm1_ip}" bash <<REMOTE
set -e
apt-get install -y -qq haproxy > /dev/null 2>&1

# On VM1, Squid must release port 3128 for HAProxy
# Keep Squid only on 3129 (backend port)
if grep -q "http_port 3128" /etc/squid/squid.conf; then
    sed -i '/^http_port 3128$/d' /etc/squid/squid.conf
    systemctl restart squid
    echo "Squid reconfigured: listening on 3129 only"
fi

cat > /etc/haproxy/haproxy.cfg <<'HAEOF'
global
  log /dev/log local0
  maxconn 2000
  daemon

defaults
  log     global
  mode    tcp
  option  tcplog
  timeout connect 10s
  timeout client  60s
  timeout server  60s
  retries 3

frontend stats
  bind *:8404
  mode http
  stats enable
  stats uri /stats
  stats refresh 10s

frontend proxy_in
  bind *:3128
  default_backend squid_pool

backend squid_pool
  balance roundrobin
HAEOF

IFS=',' read -ra HOSTS <<< "$backends"
for i in "\${!HOSTS[@]}"; do
    echo "  server squid\${i} \${HOSTS[\$i]} check inter 30s fall 3 rise 2" >> /etc/haproxy/haproxy.cfg
done

systemctl enable haproxy
systemctl restart haproxy
echo "HAProxy OK — \${#HOSTS[@]} backends"
REMOTE

    log "Proxy: http://${vm1_ip}:${PROXY_PORT}"
    log "Stats: http://${vm1_ip}:8404/stats"
}

# ── Status ─────────────────────────────────────────

show_status() {
    log "Cluster status:"
    local vm1_ip=""

    for zone in "${ZONES[@]}"; do
        local instances
        instances=$(scw instance server list zone="$zone" -o json 2>/dev/null \
            | jq "[.[] | select(.tags[]? | contains(\"$TAG_PROJECT\"))]")
        local count
        count=$(echo "$instances" | jq 'length')

        for i in $(seq 0 $((count - 1))); do
            local name ip state
            name=$(echo "$instances" | jq -r ".[$i].name")
            ip=$(echo "$instances" | jq -r ".[$i].public_ip.address")
            state=$(echo "$instances" | jq -r ".[$i].state")
            echo "  $name: $ip ($state)"
            [ -z "$vm1_ip" ] && vm1_ip="$ip"
        done
    done

    if [ -n "$vm1_ip" ]; then
        echo ""
        log "Testing rotation (6 requests):"
        for i in $(seq 1 6); do
            local out
            out=$(curl -s --proxy "http://${vm1_ip}:3128" --max-time 10 \
                "https://httpbin.org/ip" 2>/dev/null | jq -r '.origin // "error"' || echo "timeout")
            echo "  #$i → $out"
        done
        echo ""
        log "PROXY_URL=http://${vm1_ip}:${PROXY_PORT}"
    fi
}

# ── Teardown ───────────────────────────────────────

teardown() {
    warn "Destroying proxy cluster..."
    for zone in "${ZONES[@]}"; do
        local instances
        instances=$(scw instance server list zone="$zone" -o json 2>/dev/null \
            | jq "[.[] | select(.tags[]? | contains(\"$TAG_PROJECT\"))]")
        local count
        count=$(echo "$instances" | jq 'length')

        for i in $(seq 0 $((count - 1))); do
            local sid name
            sid=$(echo "$instances" | jq -r ".[$i].id")
            name=$(echo "$instances" | jq -r ".[$i].name")
            log "[$zone] Terminating $name..."
            scw instance server terminate "$sid" zone="$zone" \
                with-ip=true with-block=true 2>/dev/null || true
        done

        # Orphan IPs
        scw instance ip list zone="$zone" -o json 2>/dev/null \
            | jq -r '.[] | select(.server==null) | .id' \
            | while read -r id; do
                scw instance ip delete "$id" zone="$zone" 2>/dev/null || true
            done

        # Security group
        scw instance security-group list zone="$zone" -o json 2>/dev/null \
            | jq -r ".[] | select(.name==\"$PROJECT_NAME\") | .id" \
            | while read -r sgid; do
                scw instance security-group delete "$sgid" zone="$zone" 2>/dev/null || true
            done
    done
    log "Done"
}

# ── Main ───────────────────────────────────────────

main() {
    for cmd in scw jq ssh curl; do
        command -v "$cmd" &>/dev/null || { err "Missing: $cmd"; exit 1; }
    done

    case "${1:-deploy}" in
        deploy)
            local total_vms=$(( ${#ZONES[@]} * VMS_PER_ZONE ))
            local total_ips=$(( total_vms * IPS_PER_VM ))
            log "Plan: ${#ZONES[@]} zones × $VMS_PER_ZONE VMs × $IPS_PER_VM IPs = $total_ips IPs"
            log "Zones: ${ZONES[*]}"
            log "Cost: ~€$(( total_vms * 6 + (total_ips - total_vms) * 3 ))/month"
            echo ""

            local all_vms=()
            local all_ips=()

            for zone in "${ZONES[@]}"; do
                local sg_id
                sg_id=$(create_security_group "$zone")
                for idx in $(seq 1 $VMS_PER_ZONE); do
                    all_vms+=("$(create_vm "$zone" "$idx" "$sg_id")")
                done
            done

            echo ""
            log "VMs created. Configuring Squid on each..."

            for vm_info in "${all_vms[@]}"; do
                IFS='|' read -r _ _ ip <<< "$vm_info"
                configure_squid "$ip"
                all_ips+=("$ip")
            done

            echo ""
            configure_haproxy "${all_ips[0]}" "${all_ips[@]}"

            echo ""
            log "=== Done ==="
            show_status

            echo ""
            log "Add to .env:"
            echo "  PROXY_URL=http://${all_ips[0]}:${PROXY_PORT}"
            ;;
        teardown) teardown ;;
        status) show_status ;;
        *) echo "Usage: $0 [deploy|teardown|status]"; exit 1 ;;
    esac
}

main "$@"
