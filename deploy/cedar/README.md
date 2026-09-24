# PathFinder on cedar

`cedar.penn.apidb.org` runs PathFinder for internal testers as rootless podman
containers under one user account. The images come from the registry: a release
tag of this repository publishes them (`.github/workflows/publish-images.yml`),
and the host only pulls. Nothing is built on cedar, and there is no sudo.

Seven units make the stack: `pathfinder-db`, `pathfinder-wdk-mcp`,
`pathfinder-searxng`, `pathfinder-research-mcp`, `pathfinder-api`,
`pathfinder-worker` and `pathfinder-web`. Only the web and the api publish a
port, both on the loopback interface (3010 and 8010); the rest are reached by
container name on the `pathfinder` network.

## First install

On a workstation, with a release tag published:

```bash
ssh -p 2112 amuharram@cedar.penn.apidb.org
```

On the host:

```bash
git clone https://github.com/VEuPathDB/pathfinder-app.git ~/pathfinder
mkdir -p ~/.config/pathfinder
```

The host reads only `quadlets/` and `deploy/` out of that checkout; copying the two
directories over with `rsync -e 'ssh -p 2112'` does the same job.

### Registry access

The four images are published by CI to `ghcr.io/veupathdb` as private packages: a container
package a workflow creates is private by default, and the organization's policy does not
allow a package to be made public. The host therefore logs in once, into a file that outlives
a reboot (the default login lives under `$XDG_RUNTIME_DIR`, which a reboot clears):

```bash
mkdir -p ~/.config/environment.d ~/.config/pathfinder
printf 'REGISTRY_AUTH_FILE=%s/.config/pathfinder/ghcr-auth.json\n' "$HOME" > ~/.config/environment.d/pathfinder.conf
systemctl --user set-environment "REGISTRY_AUTH_FILE=$HOME/.config/pathfinder/ghcr-auth.json"
podman login --authfile ~/.config/pathfinder/ghcr-auth.json ghcr.io -u <github-username>
```

The password is a personal access token carrying only `read:packages`. `environment.d` hands
the variable to the systemd user manager at every login, so every unit's pull reads that
file; `set-environment` applies it to the session that is already running. `install.sh`
exports the same variable for its own pulls.

Write the environment file. `deploy/cedar/env.example` names every variable the
units read and nothing else; fill the values in on the host, and keep the file
private:

```bash
cp ~/pathfinder/deploy/cedar/env.example ~/.config/pathfinder/.env
chmod 600 ~/.config/pathfinder/.env
$EDITOR ~/.config/pathfinder/.env
```

Install and start the stack. `PATHFINDER_TAG` is the release the units pull:

```bash
cd ~/pathfinder
PATHFINDER_TAG=v0.2.0a2 ./deploy/cedar/install.sh
```

The installer copies the units, the network and the volumes to
`~/.config/containers/systemd/`, substitutes the tag, copies the metasearch
settings to `~/.config/pathfinder/searxng/settings.yml`, enables linger so the
stack survives a logout, reloads systemd and starts the seven units. It is
idempotent: a second run with the same tag writes nothing, restarts nothing and
prints `systemctl --user status` for the seven units.

The first start pulls about 3.7 GB of images and the api applies the database
migrations, so give it several minutes before the smoke test.

## A tag bump

```bash
cd ~/pathfinder && git pull
PATHFINDER_TAG=v0.2.0a3 ./deploy/cedar/install.sh
```

The five units whose image name carries the tag restart; the postgres and searxng
units are only started. The postgres volume and the catalog volume are not touched.

**Before bumping to a release that changes a durable job payload, drain the
queue first.** The job names do not change, so an in-flight job reaches the new
worker and fails on its keyword arguments.

**v0.2.0a15 removes the `geneset_enrichment` durable tool.** A job of it that is
still queued reaches a worker with no body for it. Before the bump, check that none
is waiting or running, and wait until the count is 0:

```bash
podman exec pathfinder-db psql -U postgres -d pathfinder -c \
  "SELECT status, count(*) FROM procrastinate_jobs
   WHERE queue_name = 'verification' AND task_name = 'durable:geneset_enrichment'
     AND status IN ('todo', 'doing') GROUP BY status;"
```

To go back, run the installer again with the previous tag.

## Logs and state

```bash
systemctl --user status pathfinder-api.service
journalctl --user -u pathfinder-api.service -f
journalctl --user -u 'pathfinder-*' -n 200
podman ps
podman images
```

A unit that fails to pull reports it in its own journal. A unit that starts and
then exits is usually missing a variable in `~/.config/pathfinder/.env`.

## Reaching the deployment

Until the vhost exists, tunnel both ports from a workstation:

```bash
ssh -p 2112 -L 3010:localhost:3010 -L 8010:localhost:8010 amuharram@cedar.penn.apidb.org
```

The app is then `http://localhost:3010` and the api `http://localhost:8010`.
The browser talks to the web origin only: the server rewrites `/api/...` and
`/health/...` to `http://pathfinder-api:8000` on the container network, which is
the address baked into the image at build time. The api port is published for
the smoke test and for the vhost.

## Smoke test

Through the tunnel, after the first start:

```bash
curl -s http://localhost:8010/health/ready | python3 -m json.tool
```

Every subsystem reads ready and at least one site catalog is loaded. Then, in a
browser on `http://localhost:3010`:

1. Sign in against a VEuPathDB site and confirm the site menu reports it
   available.
2. Send one chat turn and confirm it streams and completes. The provider is the
   real one; the mock provider is a test stack only.
3. Confirm a durable task (a control test, an enrichment, a parameter sweep)
   reaches a result, which proves the worker picked it up.

## The tester URL

EBRC owns Apache on this host. Per-app vhosts live in
`/etc/httpd/conf/enabled_sites/` and only EBRC adds them. What PathFinder needs
at `pathfinder-testing.penn.apidb.org`:

- TLS terminated by EBRC.
- `/api/v1/` proxied to `127.0.0.1:8010`, and everything else to
  `127.0.0.1:3010`. One `ProxyPass /` to the web port also works: the web server
  rewrites the api calls itself, and the only cost is one extra hop for the
  event stream.
- No response buffering on `/api/v1/chat`, which is a Server-Sent Events stream.
- The forwarded headers Apache sets by default. The api trusts them from any
  address (`FORWARDED_ALLOW_IPS=*` in `quadlets/pathfinder-api.container`): its port is
  bound to the host's loopback, so only the proxy or a tunnel can reach it.

Add the tester URL to `CORS_ORIGINS` in `~/.config/pathfinder/.env` and restart
the api once the vhost is live.

## Stopping

```bash
systemctl --user stop pathfinder-web.service pathfinder-worker.service \
  pathfinder-api.service pathfinder-research-mcp.service \
  pathfinder-searxng.service pathfinder-wdk-mcp.service pathfinder-db.service
```

The volumes `pathfinder-postgres-data` and `pathfinder-catalogs` outlive the
containers. Removing them discards every conversation, strategy and gene set
this deployment holds.
