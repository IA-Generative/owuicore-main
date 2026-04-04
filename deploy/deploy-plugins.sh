#!/usr/bin/env bash
# Deploy all discovered plugins to K8s.
#
# For each plugin with custom_image: true, runs build + push + kubectl apply.
# For plugins without K8s manifests, only registers tools/pipelines.
#
# Usage:
#   bash deploy/deploy-plugins.sh
#   bash deploy/deploy-plugins.sh --dry-run
#   PLUGIN_PATHS=../grafrag-experimentation bash deploy/deploy-plugins.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SOCLE_DIR="$(dirname "$SCRIPT_DIR")"
cd "$SOCLE_DIR"

DRY_RUN=false
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
  esac
done

# Discover plugins
PLUGINS="$(bash scripts/discover_plugins.sh)"
if [[ -z "$PLUGINS" ]]; then
  echo "No plugins found. Nothing to deploy."
  exit 0
fi

echo "=== Deploying plugins ==="
echo ""

while IFS= read -r plugin_path; do
  plugin_dir="$(cd "$SOCLE_DIR/$plugin_path" && pwd)"
  plugin_file="$plugin_dir/owui-plugin.yaml"

  if [[ ! -f "$plugin_file" ]]; then
    echo "SKIP: $plugin_path (no owui-plugin.yaml)"
    continue
  fi

  # Parse plugin metadata
  name="$(python3 -c "import yaml,sys; d=yaml.safe_load(open(sys.argv[1])); print(d.get('name','unknown'))" "$plugin_file")"
  namespace="$(python3 -c "import yaml,sys; d=yaml.safe_load(open(sys.argv[1])); print(d.get('k8s',{}).get('namespace','default'))" "$plugin_file")"
  custom_image="$(python3 -c "import yaml,sys; d=yaml.safe_load(open(sys.argv[1])); print(str(d.get('k8s',{}).get('custom_image',False)).lower())" "$plugin_file")"

  echo "--- Plugin: $name (namespace: $namespace) ---"

  if [[ "$DRY_RUN" == "true" ]]; then
    echo "  [dry-run] Would deploy $name to namespace $namespace"
    echo ""
    continue
  fi

  # Build + push if custom image
  if [[ "$custom_image" == "true" ]]; then
    if [[ -f "$plugin_dir/deploy/build-images.sh" ]]; then
      echo "  Building images..."
      (cd "$plugin_dir" && bash deploy/build-images.sh)
    elif [[ -f "$plugin_dir/Dockerfile" ]]; then
      echo "  Building image from Dockerfile..."
      registry="${REGISTRY:-rg.fr-par.scw.cloud/funcscwnspricelessmontalcinhiacgnzi}"
      tag="${IMAGE_TAG:-latest}"
      docker build -t "$registry/$name:$tag" "$plugin_dir"
      docker push "$registry/$name:$tag"
    fi
  fi

  # Apply K8s manifests if present
  if [[ -d "$plugin_dir/k8s" || -d "$plugin_dir/deploy/k8s" ]]; then
    k8s_dir="$plugin_dir/k8s"
    [[ -d "$plugin_dir/deploy/k8s" ]] && k8s_dir="$plugin_dir/deploy/k8s"

    echo "  Applying K8s manifests from $k8s_dir..."
    kubectl create namespace "$namespace" --dry-run=client -o yaml | kubectl apply -f -

    for manifest in "$k8s_dir"/*.yaml; do
      manifest_name="$(basename "$manifest")"
      # Skip templates and examples
      [[ "$manifest_name" == *"example"* || "$manifest_name" == *"template"* ]] && continue
      kubectl apply -f "$manifest" -n "$namespace"
      echo "    Applied: $manifest_name"
    done
  fi

  # Run plugin's own deploy script if it has one
  if [[ -f "$plugin_dir/deploy/deploy-k8s.sh" ]]; then
    echo "  Running plugin deploy script..."
    (cd "$plugin_dir" && bash deploy/deploy-k8s.sh)
  fi

  echo ""
done <<< "$PLUGINS"

# Register tools + pipelines into OWUI
echo "=== Registering tools and pipelines ==="
python3 scripts/register_plugins.py

echo ""
echo "=== Done ==="
