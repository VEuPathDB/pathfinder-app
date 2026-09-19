# PathFinder podman quadlets

`quadlets/` holds the systemd unit files of the PathFinder deployment: seven
containers, one network and two volumes, run rootless under `systemctl --user`.

The units pull their images from `ghcr.io/veupathdb`, published by a `v*` tag of
this repository (`.github/workflows/publish-images.yml`). Each image name carries
one tag placeholder, which `deploy/cedar/install.sh` replaces with the release
the operator names in `PATHFINDER_TAG`. Nothing is built on the deployment host.

- **Deploying, updating, reading logs, the tunnel and the smoke test**:
  [deploy/cedar/README.md](deploy/cedar/README.md).
- **The variables the units read**: [deploy/cedar/env.example](deploy/cedar/env.example),
  copied to `~/.config/pathfinder/.env` on the host.
- **Why the images are pulled and not built**:
  [docs/knowledge/decisions/the-images-come-from-the-registry-and-cedar-pulls.md](docs/knowledge/decisions/the-images-come-from-the-registry-and-cedar-pulls.md).
- **Local development** runs docker compose instead:
  `docker compose --env-file .env.dev up -d --build --force-recreate api worker wdk-mcp research-mcp searxng web`.

`node scripts/check-quadlets.mjs` holds the units to the invariants the
deployment depends on: the registry image of each unit, the one tag placeholder,
the two published ports on the loopback interface and none anywhere else, the
tool-server addresses the api and the worker read, and the environment file each
unit loads.

## Local overrides

A drop-in directory overrides a unit without editing it. Create
`~/.config/containers/systemd/<unit>.container.d/override.conf`, then
`systemctl --user daemon-reload` and restart the unit. For a list directive such
as `PublishPort` or `Environment`, an override adds to the base value; clear it
first with an empty assignment to replace it.

```ini
[Container]
PublishPort=
PublishPort=127.0.0.1:8080:3000
```
