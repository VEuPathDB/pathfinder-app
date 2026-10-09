# Operating PathFinder

This runbook is for the PathFinder estate stack: the `pathfinder` folder of
`VEuPathDB/webservices-quadlets`. The units are root templated podman quadlets. The instance
name `%i` is the stage (`dev` today, `qa` next), so `pathfinder-api@dev.service` runs the
container `pathfinder-api-dev`. Puppet decides which stage runs on which host.

The stack reads its environment in this order, a later file overriding an earlier one:
`env/00-pathfinder_defaults.env`, `env/10-pathfinder_override_<stage>.env`,
`env/20-pathfinder_override_<host FQDN>.env`, `env/30-pathfinder_override_<stage>_<host FQDN>.env`.
The repository's own README explains the layering. Secrets are podman secrets named
`pathfinder_<NAME>_<stage>`, which puppet creates.

Every command below runs as root on the host that runs the stage. Replace `dev` with the stage.

## What runs

| unit | image | what it does | waits for |
|---|---|---|---|
| `pathfinder-db@` | `docker.io/pgvector/pgvector:pg16` | Postgres with pgvector: every stored record, the job queue, the embedding index | nothing |
| `pathfinder-api@` | `docker.io/veupathdb/pathfinder-api` | The HTTP API on 8000. Migrates the database at start, loads the site catalogs, writes the embedding index | db (and pulls in the worker) |
| `pathfinder-worker@` | `pathfinder-api`, `Exec=... -m pathfinder.jobs.worker` | Runs every chat turn and every background task (control tests, optimization, EDA compute) | db, api, wdk-mcp, research-mcp |
| `pathfinder-wdk-mcp@` | `pathfinder-api`, `Exec=... -m veupathdb_mcp` | The WDK catalog tools over MCP on 8100, for the site help assistant | db |
| `pathfinder-research-mcp@` | `pathfinder-api`, `Exec=... -m veupathdb_mcp.research` | Literature and web search over MCP on 8110 | searxng |
| `pathfinder-searxng@` | `docker.io/searxng/searxng` | The web search engine research-mcp asks first, on 8080 | nothing |
| `pathfinder-service@` | `docker.io/veupathdb/pathfinder-web` | The Next.js site on 3000. Forwards `/pathfinder/api/*` and `/pathfinder/health/*` to the api | api |

Two volumes: `pathfinder-db-data-<stage>` (the database) and `pathfinder-catalogs-<stage>`
(catalog snapshots, shared by api, worker and wdk-mcp). One network, `pathfinder-internal-<stage>`;
containers reach each other by alias (`pathfinder-db`, `pathfinder-api`, `pathfinder-wdk-mcp`,
`pathfinder-research-mcp`, `pathfinder-searxng`). The api and the worker also join `monitoring`.

Only the web container is on Traefik, at `pathfinder-<stage>.local.apidb.org` on the `local`
entrypoint (8443). Apache on the website's vhost proxies `/pathfinder` to
`https://pathfinder-<stage>.local.apidb.org:8443/pathfinder` (`set_pathfinder_proxy` in
`Containers.pm` of `puppet-ebrc_httpd_setup`, the same shape as `set_jbrowse2_proxy`). The dev
stage is served at `https://muharram.veupathdb.org/pathfinder`, qa at
`https://qa.veupathdb.org/pathfinder` (`PUBLIC_BASE_URL` in each stage override).

Restarting one unit alone:

- web, searxng, research-mcp and wdk-mcp hold no state; restart them at any time. While
  research-mcp is down the assistant has no literature search; while wdk-mcp is down the site
  help assistant has no catalog tools.
- worker: a restart stops the turns and background tasks it is running. Check the queue first
  (see [Releases](#releases)).
- api: researchers lose the page until it binds again, then catalogs reload behind it.
- db: every other unit except searxng and research-mcp fails until it is back. Restart it alone,
  when no turn is running.

## First start

1. Puppet creates the twelve secrets (see [Secrets](#secrets)) and installs the units.
2. The first start of each container pulls its image; the units allow 900 s for that.
3. The db initializes the empty volume with `POSTGRES_USER`, `POSTGRES_DB` and the password secret.
4. The api migrates the database to the latest revision of three Alembic chains: PathFinder's
   own, then the tool server's (`veupathdb_mcp.migrate.OWNED_TABLES`: the embedding tables),
   then the runtime's (`assistant_core.migrate.OWNED_TABLES`: conversations, messages, events,
   tasks and usage). The worker does not migrate. The graph checkpointer and the memory store
   create their own tables when the api opens them.
5. The api starts serving. It then reaches the embedding backend, loads one catalog per site in
   the stage's sites file (`deploy/sites/<stage>.yml` in this repository, baked into the image at
   `/app/config/sites/<stage>.yml`), and writes the embedding index. A site has 30 s
   (`SITE_PRELOAD_TIMEOUT_SECONDS`) to answer; one that does not is degraded and retried every
   60 s (`SITE_RETRY_INTERVAL_SECONDS`).

The api health check probes `/health` with a 600 s start period. It passes once the server binds,
which is after the migrations. Catalogs keep loading behind it, so the stack is healthy for
researchers when `/health/ready` answers 200 and `/health/system` reports `"ready": true`:

```bash
podman ps --filter name=pathfinder- --format '{{.Names}}  {{.Status}}'
podman exec pathfinder-api-dev curl -sS http://localhost:8000/health/system
```

Only the api refreshes catalogs and writes the embedding index. The worker and wdk-mcp run with
`CATALOG_REFRESH_ENABLED=false` and `EMBEDDING_INDEX_SYNC_ENABLED=false` and read what the api
saved in the catalogs volume and the database.

## Releases

Jenkins builds both images from this repository's `Jenkinsfile`: `:latest` on every push to
`main`, and `:<semver>` on a tag `v<semver>` (`v0.2.0-b7` publishes `:0.2.0-b7`). The two MCP
units run the api image, so a release moves all three together.

- **dev** runs `PATHFINDER_TAG=latest` (`00-pathfinder_defaults.env`). Every unit carries
  `AutoUpdate=registry`, so `podman-auto-update` pulls a moved tag and restarts the unit. A push
  to `main` reaches dev without anyone acting.
- **qa** runs `PATHFINDER_TAG=qa` (`10-pathfinder_override_qa.env`). The `VEuPathDB/tagger`
  repository moves `:qa`: a pull request to its `qa` branch adds `pathfinder-api: <version>` and
  `pathfinder-web: <version>` to `versions.yml`, and its job retags those images as `:qa`. The
  version must already be on Docker Hub.

To see what a stage runs:

```bash
podman exec pathfinder-api-dev curl -fsS http://localhost:8000/health
podman exec pathfinder-wdk-mcp-dev curl -fsS http://localhost:8100/health
```

The first prints the api version. The second prints the tool server version, which must equal
the `veupathdb-mcp` the api imports:
`podman exec pathfinder-api-dev .venv/bin/python -c "import importlib.metadata as m; print(m.version('veupathdb-mcp'))"`.

**Pin a stage to one version.** Put `PATHFINDER_TAG=<version>` (for example `0.2.0-b7`) in
`env/30-pathfinder_override_<stage>_<host FQDN>.env`, or in `env/20-pathfinder_override_<host FQDN>.env`
to pin every stage on that host. Either is a pull request to `webservices-quadlets`; a merged
change reaches the servers within an hour and restarts the stack (prod needs a manual restart).
A version tag never moves, so auto-update leaves a pinned stage alone. Delete the file to follow
the stage tag again.

**Roll back** by pinning the previous version, or, on qa, by retagging the previous version in
`tagger`. A rollback across a release that added a database migration fails at api start: the
older image does not know the newer revision. That case needs the database restored from the
dump taken before the release (see [Backups](#backups-and-restore)). Take a dump before every
qa release.

**Drain the queue before a release that changes a durable job's arguments.** The release notes
say when. A job queued by the old code reaches the new worker under the same name and fails on
its arguments. Before the new tag lands, stop the api so no new turn starts, then wait until the
worker has nothing queued or running:

```bash
systemctl stop pathfinder-api@dev
podman exec pathfinder-db-dev psql -U pathfinder -d pathfinder -c \
  "SELECT queue_name, status, count(*) FROM procrastinate_jobs WHERE status IN ('todo','doing') GROUP BY 1, 2"
```

The worker deletes a job when it ends, so `procrastinate_jobs` holds only queued and running
jobs, each with its request and the researcher's sign-in token. When the query returns no rows,
take the release and start the api. On dev, which follows
`:latest`, pin the current version first so the new image does not arrive mid-drain.

## Secrets

Each is the podman secret `pathfinder_<NAME>_<stage>`. A container reads a secret when it
starts, so a rotation is: change the value, then restart every unit in "used by". Values that
need randomness: `openssl rand -hex 32`.

| name | used by | what it does | rotating it |
|---|---|---|---|
| `POSTGRES_PASSWORD` | db | Password of the `pathfinder` role. The image applies it only when it initializes an empty volume. | Changing the secret alone does nothing on an existing volume. Run `podman exec pathfinder-db-dev psql -U pathfinder -d pathfinder -c "ALTER ROLE pathfinder PASSWORD '<new>'"`, then change this secret and `DATABASE_URL` together, and restart api, worker and wdk-mcp. |
| `DATABASE_URL` | api, worker, wdk-mcp | `postgresql+asyncpg://pathfinder:<password>@pathfinder-db:5432/pathfinder`. Must hold the same password as `POSTGRES_PASSWORD`. | See the row above. A mismatch stops the api at its migration step. |
| `API_SECRET_KEY` | api, worker | Signs the `pathfinder-auth` session cookie (HS256, valid 24 h). At least 32 characters; the api and the worker refuse to start on a shorter value or one containing `example`, `placeholder` or `change-me`. | Every PathFinder session stops verifying. A researcher still signed in to the website gets a new session on the next page load (`POST /api/v1/veupathdb/auth/refresh`); nothing stored is lost. |
| `OPENAI_API_KEY` | api, worker, wdk-mcp | The deployment's OpenAI account: the default chat models, the injection judge and every embedding (memories and the catalog index). | Restart all three. Without it the worker refuses to start, because it cannot build the injection judge, and the api reports `embedding_backend` not ready. |
| `ANTHROPIC_API_KEY` | api, worker | Lets the deployment pay for Claude Haiku 5.5. Sonnet 5.5 and Opus 5.5 run only on a researcher's own key. | Restart api and worker. Without it, Claude models need a researcher's key. |
| `PROVIDER_KEY_ENCRYPTION_KEY` | api, worker | Seals the model keys researchers store in Settings (AES-256-GCM). The base64url encoding of 32 random bytes: `python3 -c 'import base64,os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())'`. Empty turns the feature off. A malformed value stops both processes. | Every stored key stops opening. At the researcher's next turn the worker marks the key unreadable and refuses a turn that needs it; the deployment's key never stands in. Each researcher enters the key again in Settings. Keep this secret with the database backups. |
| `VEUPATHDB_AUTH_TOKEN` | api, worker, wdk-mcp | A registered VEuPathDB service account's token for reads that name no user: record types, searches, parameters. Everything a researcher does runs under the researcher's own website login. | Restart all three. If the sites refuse it, catalogs do not load and every site shows as unavailable. |
| `WDK_MCP_SERVICE_TOKENS` | wdk-mcp | The applications wdk-mcp admits, as `app_id:secret[,app_id:secret...]`. Each secret is at least 32 characters; application ids are unique. | Add a second entry under a new id, move `WDK_MCP_TOKEN` to its secret, restart wdk-mcp then the worker, then remove the old entry. |
| `WDK_MCP_TOKEN` | worker (as `PATHFINDER_WDK_MCP_TOKEN`) | The secret the worker presents to wdk-mcp. Must equal the secret half of one `WDK_MCP_SERVICE_TOKENS` entry. | A mismatch makes wdk-mcp answer 401 and counts in `pathfinder_tool_source_errors_total{source="veupathdb-wdk-mcp"}`. |
| `RESEARCH_MCP_SERVICE_TOKENS` | research-mcp | The same form as `WDK_MCP_SERVICE_TOKENS`, for research-mcp. | As for wdk-mcp. |
| `RESEARCH_MCP_TOKEN` | worker (as `PATHFINDER_RESEARCH_MCP_TOKEN`) | The secret the worker presents to research-mcp. Must equal the secret half of one `RESEARCH_MCP_SERVICE_TOKENS` entry. | A mismatch ends literature and web search; the error counts under `source="veupathdb-research-mcp"`. |
| `SEARXNG_SECRET` | searxng | SearXNG's server secret. The stack's `config/searxng-settings.yml` turns the limiter and the image proxy off. | Restart searxng. Nothing else reads it. |

Optional secrets, each a commented `#Secret=` line in its unit: create the secret, then
uncomment the line (a pull request to `webservices-quadlets`).

| name | used by | what it does |
|---|---|---|
| `GEMINI_API_KEY` | api, worker | Lets the deployment pay for Gemini models. |
| `SERVICE_TOKENS` (as `PATHFINDER_SERVICE_TOKENS`) | api | Applications that call the api in the `X-PathFinder-Service-Token` header, as `app_id:secret[,...]`. Rotating one breaks only that caller. |
| `S2_API_KEY` (as `RESEARCH_MCP_S2_API_KEY`) | research-mcp | Raises the Semantic Scholar rate limit. |

## Routine checks

| endpoint (api, port 8000) | answers |
|---|---|
| `/health` | Liveness: `{"status": "healthy", "version", "timestamp"}`. The unit's health check. |
| `/health/ready` | 200 when the database, the embedding backend, the graph checkpointer and input screening are ready and at least one site catalog is loaded; 503 otherwise. `notReady` names what is missing, `degraded` the sites not loaded. |
| `/health/system` | Always 200. `ready`, `apiReady`, `workerAlive` (a worker heartbeat within 30 s), `notReady`, `degraded`. The page's startup gate reads it. |
| `/health/config` | The providers the deployment pays for, the site, and the sign-in address. |

```bash
podman exec pathfinder-api-dev curl -sS http://localhost:8000/health/ready
podman exec pathfinder-research-mcp-dev curl -fsS http://localhost:8110/health
curl -sS https://muharram.veupathdb.org/pathfinder/health/system   # through Apache and the web container
```

Logs are JSON lines on stdout, kept by journald. A line made inside a request or a turn carries
the researcher's account ID. A queue line names a job by its name, id, queue and status, never
its arguments or its result.

```bash
journalctl -u pathfinder-api@dev --since -1h
journalctl -u pathfinder-worker@dev -f
journalctl -u pathfinder-api@dev | grep '"level": "error"'
```

## Metrics

The api and the worker each serve Prometheus series at `GET /metrics` on port 9100 inside the
container (`METRICS_PORT`; 0 serves none). The port is not published. Both units join the
`monitoring` network with the label `prometheus.scrape_enabled=true`, so the estate's Prometheus
scrapes them. To read them by hand:

```bash
podman exec pathfinder-api-dev curl -s http://localhost:9100/metrics | grep '^pathfinder_'
```

| series | process | labels |
|---|---|---|
| `pathfinder_http_requests_total` | api | method, route template, status class |
| `pathfinder_http_request_duration_seconds` | api | method, route template |
| `pathfinder_chat_turns_started_total` | api | assistant |
| `pathfinder_chat_turns_finished_total` | worker | assistant, outcome, model |
| `pathfinder_chat_turn_duration_seconds` | worker | assistant, outcome |
| `pathfinder_model_tokens_total`, `pathfinder_model_cost_usd_total` | worker | model, payer |
| `pathfinder_tool_source_errors_total` | worker | source, stage |

Started turns that never finish point at the worker. The reasoning is in
[docs/knowledge/decisions/metrics-go-to-the-estate-prometheus.md](knowledge/decisions/metrics-go-to-the-estate-prometheus.md).

## Backups and restore

The db volume holds everything researchers made: conversations and their events, strategies,
saved gene sets, memories, usage and the sealed provider keys. Back it up with `pg_dump`:

```bash
podman exec pathfinder-db-dev pg_dump -U pathfinder -d pathfinder -Fc > pathfinder-dev-$(date +%F).dump
```

The catalogs volume is a cache. The api rebuilds it from the sites, so it needs no backup.

The sealed keys open only under the same `PROVIDER_KEY_ENCRYPTION_KEY`. A restore under another
value loses them (see [Secrets](#secrets)).

Restore into the running db with the api, worker and wdk-mcp stopped:

```bash
systemctl stop pathfinder-service@dev pathfinder-worker@dev pathfinder-api@dev pathfinder-wdk-mcp@dev
podman exec -i pathfinder-db-dev pg_restore -U pathfinder -d pathfinder --clean --if-exists < pathfinder-dev-2026-10-09.dump
systemctl start pathfinder-api@dev pathfinder-wdk-mcp@dev pathfinder-worker@dev pathfinder-service@dev
```

Start the image version that wrote the dump, or a newer one: the api migrates forward at start,
never back.

## Troubleshooting

**A site shows as unavailable** ("Couldn't reach" in the site menu, 503 `SITE_UNAVAILABLE` on its
routes). Its catalog did not load inside its 30 s budget. `/health/ready` lists it under
`degraded`, and the api retries it every 60 s with no action needed. The api log names it:
`journalctl -u pathfinder-api@dev | grep 'Site catalog did not load'`. If every site is degraded,
check `VEUPATHDB_AUTH_TOKEN` and that the host reaches the URLs in the stage's sites file.

**Chat hangs.** Check the worker first; the api never runs a turn.

```bash
podman exec pathfinder-api-dev curl -sS http://localhost:8000/health/system   # "workerAlive": false?
systemctl status pathfinder-worker@dev
journalctl -u pathfinder-worker@dev --since -15m
```

A worker that logs "the injection judge did not build" cannot reach its model; check
`OPENAI_API_KEY`. If the worker runs but turns stay queued, look at the queue with the
`procrastinate_jobs` query under [Releases](#releases). A tool server that refuses the worker
shows in `pathfinder_tool_source_errors_total`; check its token pair.

**The page answers 404.**

- From Traefik (a plain `404 page not found`): the web container is not running or not on the
  `traefik` network, or `TRAEFIK_DOMAIN` does not match the host Apache proxies to.
  `systemctl status pathfinder-service@dev`.
- From Apache: the vhost has no `set_pathfinder_proxy('<stage>')` call. That is a systems change
  in `puppet-ebrc_httpd_setup`.
- Test each hop: `curl -sk https://pathfinder-dev.local.apidb.org:8443/pathfinder/health` from
  the web host, then the public URL.

**Sign-in fails.** PathFinder has no login of its own. It reads the website's `Authorization`
cookie, which the browser sends only to the website's own host, so PathFinder must be opened at
`https://<website>/pathfinder`, never at the Traefik host. The researcher signs in on the website
with a registered account; a guest is refused (401 `WDK_LOGIN_REQUIRED`). If
`/api/v1/veupathdb/auth/status` answers 503, the website's service did not answer the identity
check. Check that `PUBLIC_BASE_URL` in the stage override is the address researchers open.
