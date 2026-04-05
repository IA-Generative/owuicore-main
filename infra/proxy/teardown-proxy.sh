#!/usr/bin/env bash
# Teardown the rotating proxy cluster on Scaleway
# Removes: VMs, flexible IPs, security groups, orphan volumes
#
# Usage:
#   ./teardown-proxy.sh              # Interactive (confirmation prompt)
#   ./teardown-proxy.sh --dry-run    # Show what would be deleted
#   ./teardown-proxy.sh --force      # Skip confirmation
set -euo pipefail

# ── Config (must match deploy-proxy.sh) ───────────
PROJECT_NAME="owui-proxy"
TAG_PROJECT="project=${PROJECT_NAME}"
ZONES=("fr-par-1" "fr-par-2")

DRY_RUN=false
FORCE=false

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
log()  { echo -e "${GREEN}[teardown]${NC} $*"; }
warn() { echo -e "${YELLOW}[teardown]${NC} $*"; }
err()  { echo -e "${RED}[teardown]${NC} $*" >&2; }
info() { echo -e "${CYAN}[teardown]${NC} $*"; }

# ── Helpers ───────────────────────────────────────

check_prereqs() {
    for cmd in scw jq; do
        command -v "$cmd" &>/dev/null || { err "Missing: $cmd"; exit 1; }
    done
}

# ── Inventory ─────────────────────────────────────

declare -a ALL_SERVERS=()
declare -a ALL_ORPHAN_IPS=()
declare -a ALL_SECURITY_GROUPS=()

collect_inventory() {
    log "Scanning resources across ${#ZONES[@]} zones..."
    echo ""

    for zone in "${ZONES[@]}"; do
        # Servers
        local servers
        servers=$(scw instance server list zone="$zone" -o json 2>/dev/null \
            | jq -c "[.[] | select(.tags[]? | contains(\"$TAG_PROJECT\"))]")
        local srv_count
        srv_count=$(echo "$servers" | jq 'length')

        if [ "$srv_count" -gt 0 ]; then
            for i in $(seq 0 $((srv_count - 1))); do
                local sid name state ip
                sid=$(echo "$servers" | jq -r ".[$i].id")
                name=$(echo "$servers" | jq -r ".[$i].name")
                state=$(echo "$servers" | jq -r ".[$i].state")
                ip=$(echo "$servers" | jq -r "(.[$i].public_ip.address // .[$i].public_ips[0].address) // \"no-ip\"")
                local ip_count
                ip_count=$(echo "$servers" | jq ".[$i].public_ips | length")
                ALL_SERVERS+=("$zone|$sid|$name|$state|$ip|$ip_count")
                info "  VM: $name ($state) — $ip (+$((ip_count - 1)) flex IPs) [$zone]"
            done
        fi

        # Orphan IPs (not attached to any server)
        local orphan_ips
        orphan_ips=$(scw instance ip list zone="$zone" -o json 2>/dev/null \
            | jq -c '[.[] | select(.server == null)]')
        local oip_count
        oip_count=$(echo "$orphan_ips" | jq 'length')

        if [ "$oip_count" -gt 0 ]; then
            for i in $(seq 0 $((oip_count - 1))); do
                local oip_id oip_addr
                oip_id=$(echo "$orphan_ips" | jq -r ".[$i].id")
                oip_addr=$(echo "$orphan_ips" | jq -r ".[$i].address // empty")
                [ -z "$oip_addr" ] && continue
                ALL_ORPHAN_IPS+=("$zone|$oip_id|$oip_addr")
                info "  Orphan IP: $oip_addr [$zone]"
            done
        fi

        # Security groups
        local sgs
        sgs=$(scw instance security-group list zone="$zone" -o json 2>/dev/null \
            | jq -c "[.[] | select(.name==\"$PROJECT_NAME\")]")
        local sg_count
        sg_count=$(echo "$sgs" | jq 'length')

        if [ "$sg_count" -gt 0 ]; then
            for i in $(seq 0 $((sg_count - 1))); do
                local sgid sgname
                sgid=$(echo "$sgs" | jq -r ".[$i].id")
                sgname=$(echo "$sgs" | jq -r ".[$i].name")
                ALL_SECURITY_GROUPS+=("$zone|$sgid|$sgname")
                info "  SG: $sgname [$zone]"
            done
        fi
    done

    echo ""
    log "Found: ${#ALL_SERVERS[@]} VMs, ${#ALL_ORPHAN_IPS[@]} orphan IPs, ${#ALL_SECURITY_GROUPS[@]} security groups"
}

# ── Destroy ───────────────────────────────────────

destroy_servers() {
    if [ ${#ALL_SERVERS[@]} -eq 0 ]; then
        log "No VMs to delete."
        return
    fi

    for entry in "${ALL_SERVERS[@]}"; do
        IFS='|' read -r zone sid name state ip ip_count <<< "$entry"

        if $DRY_RUN; then
            warn "[dry-run] Would stop & terminate $name ($sid) in $zone"
            continue
        fi

        # terminate only works on running servers; stopped servers need delete
        local cur_state
        cur_state=$(scw instance server get "$sid" zone="$zone" -o json 2>/dev/null \
            | jq -r '.state // "unknown"')

        if [ "$cur_state" = "running" ]; then
            log "[$zone] Terminating $name (running → delete with volumes/IPs)..."
            scw instance server terminate "$sid" zone="$zone" \
                with-ip=true with-block=true 2>/dev/null || true
        else
            log "[$zone] Deleting $name (state: $cur_state)..."
            # Detach and delete IPs first
            local server_ips
            server_ips=$(scw instance server get "$sid" zone="$zone" -o json 2>/dev/null \
                | jq -r '.public_ips[]?.id // empty' 2>/dev/null || true)
            for ipid in $server_ips; do
                scw instance ip detach "$ipid" zone="$zone" 2>/dev/null || true
                scw instance ip delete "$ipid" zone="$zone" 2>/dev/null || true
            done
            # Delete volumes
            local vol_ids
            vol_ids=$(scw instance server get "$sid" zone="$zone" -o json 2>/dev/null \
                | jq -r '.volumes | to_entries[]?.value.id // empty' 2>/dev/null || true)
            # Delete the server
            scw instance server delete "$sid" zone="$zone" 2>/dev/null || true
            # Delete volumes after server deletion
            for vid in $vol_ids; do
                scw block-storage volume delete "$vid" zone="$zone" 2>/dev/null || true
            done
        fi

        # Wait for server to actually disappear
        for _ in $(seq 1 20); do
            if ! scw instance server get "$sid" zone="$zone" -o json 2>/dev/null | jq -e '.id' > /dev/null 2>&1; then
                break
            fi
            sleep 3
        done
        log "[$zone] $name deleted."
    done
}

destroy_orphan_ips() {
    if [ ${#ALL_ORPHAN_IPS[@]} -eq 0 ]; then
        log "No orphan IPs to clean up."
        return
    fi

    for entry in "${ALL_ORPHAN_IPS[@]}"; do
        IFS='|' read -r zone oip_id oip_addr <<< "$entry"

        if $DRY_RUN; then
            warn "[dry-run] Would delete orphan IP $oip_addr ($oip_id) in $zone"
            continue
        fi

        log "[$zone] Deleting orphan IP $oip_addr..."
        scw instance ip delete "$oip_id" zone="$zone" 2>/dev/null || true
    done
}

destroy_security_groups() {
    if [ ${#ALL_SECURITY_GROUPS[@]} -eq 0 ]; then
        log "No security groups to delete."
        return
    fi

    for entry in "${ALL_SECURITY_GROUPS[@]}"; do
        IFS='|' read -r zone sgid sgname <<< "$entry"

        if $DRY_RUN; then
            warn "[dry-run] Would delete SG $sgname ($sgid) in $zone"
            continue
        fi

        log "[$zone] Deleting security group $sgname..."
        # Delete rules first (required before SG deletion)
        local rules
        rules=$(scw instance security-group get "$sgid" zone="$zone" -o json 2>/dev/null \
            | jq -r '.rules[]?.id // empty' 2>/dev/null || true)
        for rid in $rules; do
            scw instance security-group delete-rule \
                security-group-id="$sgid" "$rid" zone="$zone" 2>/dev/null || true
        done

        scw instance security-group delete "$sgid" zone="$zone" 2>/dev/null || true
        log "[$zone] SG $sgname deleted."
    done
}

# ── Post-check ────────────────────────────────────

verify_cleanup() {
    echo ""
    log "Verifying cleanup..."
    local remaining=0

    for zone in "${ZONES[@]}"; do
        local cnt
        cnt=$(scw instance server list zone="$zone" -o json 2>/dev/null \
            | jq "[.[] | select(.tags[]? | contains(\"$TAG_PROJECT\"))] | length")
        if [ "$cnt" -gt 0 ]; then
            err "[$zone] $cnt server(s) still present!"
            remaining=$((remaining + cnt))
        fi
    done

    if [ "$remaining" -eq 0 ]; then
        log "All $PROJECT_NAME resources cleaned up."
    else
        err "$remaining resource(s) could not be removed. Check manually with: scw instance server list"
        return 1
    fi
}

# ── Main ──────────────────────────────────────────

main() {
    check_prereqs

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --dry-run) DRY_RUN=true; shift ;;
            --force|-f) FORCE=true; shift ;;
            -h|--help)
                echo "Usage: $0 [--dry-run] [--force]"
                echo "  --dry-run  Show what would be deleted without doing it"
                echo "  --force    Skip confirmation prompt"
                exit 0 ;;
            *) err "Unknown option: $1"; exit 1 ;;
        esac
    done

    collect_inventory

    local total=$(( ${#ALL_SERVERS[@]} + ${#ALL_ORPHAN_IPS[@]} + ${#ALL_SECURITY_GROUPS[@]} ))
    if [ "$total" -eq 0 ]; then
        log "Nothing to clean up — cluster not found."
        exit 0
    fi

    if $DRY_RUN; then
        echo ""
        warn "Dry run complete. Re-run without --dry-run to execute."
        exit 0
    fi

    if ! $FORCE; then
        echo ""
        warn "This will permanently destroy ${#ALL_SERVERS[@]} VM(s) and associated resources."
        read -rp "Type 'yes' to confirm: " confirm
        if [ "$confirm" != "yes" ]; then
            err "Aborted."
            exit 1
        fi
    fi

    echo ""
    log "Starting teardown..."
    destroy_servers
    echo ""

    # Re-scan orphan IPs after server termination (terminate releases server IPs
    # but flex IPs may become orphaned)
    ALL_ORPHAN_IPS=()
    for zone in "${ZONES[@]}"; do
        local orphan_ips
        orphan_ips=$(scw instance ip list zone="$zone" -o json 2>/dev/null \
            | jq -c '[.[] | select(.server == null)]')
        local oip_count
        oip_count=$(echo "$orphan_ips" | jq 'length')
        for i in $(seq 0 $((oip_count - 1))); do
            local oip_id oip_addr
            oip_id=$(echo "$orphan_ips" | jq -r ".[$i].id")
            oip_addr=$(echo "$orphan_ips" | jq -r ".[$i].address // empty")
            [ -z "$oip_addr" ] && continue
            ALL_ORPHAN_IPS+=("$zone|$oip_id|$oip_addr")
        done
    done
    [ ${#ALL_ORPHAN_IPS[@]} -gt 0 ] && log "Found ${#ALL_ORPHAN_IPS[@]} orphan IP(s) after VM deletion"
    destroy_orphan_ips
    echo ""
    destroy_security_groups

    echo ""
    verify_cleanup
}

main "$@"
