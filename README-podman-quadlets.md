# Pathfinder — Podman Quadlet Deployment

Deploy the Pathfinder stack as rootless Podman containers managed by
`systemctl --user`.

## Prerequisites

- **Podman 4.4+** (quadlet support)
- **systemd user session** active
- **loginctl enable-linger** (for services to survive logout / start at boot)

```bash
# Check Podman version
podman --version

# Enable linger so user services persist after logout
loginctl enable-linger $USER
```

## 1. Build the application images

From the project root:

```bash
# Podman's Buildah doesn't support Docker-style glob COPY fallbacks,
# so ensure this optional config file exists (empty is fine)
touch ollama_models.yaml

podman build -t pathfinder-api:latest -f apps/api/Dockerfile .

podman build -t veupathdb-mcp:latest https://github.com/VEuPathDB/ai-wdk-mcp.git#<commit>

podman build -t pathfinder-web:latest -f apps/web/Dockerfile \
  --build-arg NEXT_PUBLIC_API_URL=http://pathfinder-api:8000 .
```

## 2. Set up the environment file

The API container loads API keys and settings from
`~/.config/pathfinder/.env`. Copy the project `.env` (or `.env.example`)
there:

```bash
mkdir -p ~/.config/pathfinder
cp .env ~/.config/pathfinder/.env
# Edit as needed — at minimum set an LLM provider API key
```

## 3. Install the quadlet files

Symlink the quadlet files (and any local drop-in directories) into the
systemd user directory:

```bash
mkdir -p ~/.config/containers/systemd
ln -sf "$PWD"/quadlets/*.{container,volume,network} ~/.config/containers/systemd/

# Also link any drop-in override directories you've created (see §8)
for d in quadlets/*.d; do
  [ -d "$d" ] && ln -sfn "$PWD/$d" ~/.config/containers/systemd/
done

systemctl --user daemon-reload
```

## 4. Start the stack

Kill the docker compose stack if it's running.

Starting the web service pulls in all its dependencies automatically:

```bash
systemctl --user start pathfinder-web
```

Or start everything explicitly:

```bash
systemctl --user start pathfinder-db pathfinder-api pathfinder-web
```

## 5. Check status

```bash
systemctl --user status pathfinder-db pathfinder-api pathfinder-web
```

## 6. View logs

```bash
# Follow API logs
journalctl --user -u pathfinder-api -f

# Last 100 lines from all Pathfinder services
journalctl --user -u 'pathfinder-*' -n 100
```

## 7. Enable on boot

With linger enabled, services with `WantedBy=default.target` start at boot:

```bash
systemctl --user enable pathfinder-db pathfinder-api pathfinder-web
```

## 8. Local overrides (drop-in directories)

Use systemd-style drop-in directories to override settings without editing
the version-controlled quadlet files. Create a `.d` directory named after
the quadlet file, with a `.conf` file inside:

```bash
# Example: change the web published port to 8080
mkdir -p quadlets/pathfinder-web.container.d
cat > quadlets/pathfinder-web.container.d/override.conf << 'EOF'
[Container]
PublishPort=
PublishPort=8080:3000
EOF
```

```bash
# Example: change the API published port to 9000
mkdir -p quadlets/pathfinder-api.container.d
cat > quadlets/pathfinder-api.container.d/override.conf << 'EOF'
[Container]
PublishPort=
PublishPort=9000:8000
EOF
```

Then link the drop-in directories and reload:

```bash
for d in quadlets/*.d; do
  [ -d "$d" ] && ln -sfn "$PWD/$d" ~/.config/containers/systemd/
done
systemctl --user daemon-reload
systemctl --user restart pathfinder-web pathfinder-api
```

The drop-in `.d` directories are gitignored, so overrides stay local to
each deployment. Any `[Container]`, `[Service]`, or `[Unit]` directive can
be overridden this way.

**Note:** For list-type directives like `PublishPort` or `Environment`, the
override *adds* to the base values. To replace a value, first clear it with
an empty assignment (`PublishPort=`), then set the new value on the next
line.

## 9. Rebuild images after code changes

```bash
podman build -t pathfinder-api:latest -f apps/api/Dockerfile .
systemctl --user restart pathfinder-api

podman build -t veupathdb-mcp:latest https://github.com/VEuPathDB/ai-wdk-mcp.git#<commit>
systemctl --user restart pathfinder-wdk-mcp

podman build -t pathfinder-web:latest -f apps/web/Dockerfile \
  --build-arg NEXT_PUBLIC_API_URL=http://pathfinder-api:8000 .
systemctl --user restart pathfinder-web
```

## 10. Stop everything

```bash
systemctl --user stop pathfinder-web pathfinder-api pathfinder-db
```

## 11. Remove persistent data

```bash
podman volume rm pathfinder-postgres-data pathfinder-catalogs
```

## Services overview

| Service | Image | Published port | Depends on |
|---------|-------|---------------|------------|
| pathfinder-db | pgvector/pgvector:pg16 | — (internal) | — |
| pathfinder-api | localhost/pathfinder-api:latest | 8000 | db |
| pathfinder-worker | localhost/pathfinder-api:latest | — (internal) | db |
| pathfinder-wdk-mcp | localhost/veupathdb-mcp:latest | 8100 | db |
| pathfinder-web | localhost/pathfinder-web:latest | 3000 | api |
