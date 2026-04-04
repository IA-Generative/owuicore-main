# Keycloak

The realm file in this directory is imported by:

- the optional Docker Compose Keycloak container
- the Kubernetes `keycloak` deployment after `deploy-k8s.sh` creates the `keycloak-realm` ConfigMap

Realm settings:

- Realm: `openwebui`
- Client: `openwebui`
- Redirect URI: `https://openwebui.fake-domain.change.me/*`
- Issuer: `https://openwebui-sso.fake-domain.change.me/realms/openwebui`

The client secret in the tracked local realm export is intentionally set to `CHANGE_ME`.

- Local Docker Compose therefore uses `KEYCLOAK_CLIENT_SECRET_LOCAL=CHANGE_ME` by default for the Open WebUI OIDC callback flow.
- Kubernetes can and should use a different `KEYCLOAK_CLIENT_SECRET` managed through secrets and rendered manifests.

For Kubernetes, rotated realm user passwords are kept in the ignored local file
`keycloak/realm-passwords.local.json`. The tracked realm JSON files keep the
default demo credentials so rotated secrets are not meant to be committed.

Rotate the realm user passwords on Kubernetes and keep the bootstrap files in sync:

```bash
python3 scripts/rotate_keycloak_passwords.py \
  --output /tmp/keycloak-password-rotation.json
```

By default the script:

- rotates every user declared in `realm-openwebui.k8s.json`
- updates `keycloak/realm-passwords.local.json`
- re-applies the Kubernetes `keycloak-realm` ConfigMap
- updates the live Keycloak users through `kcadm.sh`
- restarts the `keycloak` deployment so the new passwords survive the next pod recreation

Use `--users user1,user2` to limit the rotation to specific users.
The script does not rotate the technical `KEYCLOAK_ADMIN_PASSWORD` secret.
