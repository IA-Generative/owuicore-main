# Open WebUI

This directory exists to hold local Open WebUI state and project-specific notes.

- `data/` is mounted into the Open WebUI container for local persistence.
- The UI is configured to reach the pipeline service at `http://pipelines:9099/v1`.
- Kubernetes configuration for OIDC and ingress lives under `k8s/base/`.

