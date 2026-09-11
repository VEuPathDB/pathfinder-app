import asyncio
import contextlib
import os
import tempfile
from collections.abc import AsyncGenerator, Callable, Coroutine, Generator
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID, uuid4

# The scanner names its model directory at import, so the PIGuard model must
# be on disk before the first pathfinder import.

if "PIGUARD_MODEL_DIR" not in os.environ:
    from huggingface_hub import hf_hub_download

    _piguard_cache = Path.home() / ".cache" / "pathfinder" / "piguard"
    _piguard_cache.mkdir(parents=True, exist_ok=True)
    for _fname in ("model.onnx", "tokenizer.json"):
        hf_hub_download(
            repo_id="ahmedomuharram/piguard-onnx",
            filename=_fname,
            local_dir=str(_piguard_cache),
        )
    os.environ["PIGUARD_MODEL_DIR"] = str(_piguard_cache)

# The suite has no API key, so every embedding call is the deterministic one.
os.environ["EMBEDDING_BACKEND"] = "fake"

# A catalog snapshot the live lane builds stays out of the source tree.
os.environ.setdefault(
    "CATALOG_CACHE_DIR", tempfile.mkdtemp(prefix="pathfinder-catalogs-")
)

os.environ.setdefault("API_ENV", "test")
os.environ.setdefault("API_SECRET_KEY", "test-secret-key-test-secret-key-test")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/pathfinder_test",
)
# No test feeds a real message through the injection model, so the suite
# screens nothing and the model stays unloaded. A test about screening takes
# the `piguard_enabled` fixture.
os.environ.setdefault("PIGUARD_ENABLED", "false")
os.environ.setdefault("PATHFINDER_CHAT_PROVIDER", "mock")
os.environ.setdefault("OPENAI_API_KEY", "")
os.environ.setdefault("ANTHROPIC_API_KEY", "")
os.environ.setdefault("GEMINI_API_KEY", "")

import httpx
import procrastinate
import psycopg
import pydantic_ai.models
import pytest
import structlog
from assistant_core.conversation.checkpointer import to_psycopg_url
from assistant_core.memory.lifespan import lifespan_memory_store
from assistant_core.memory.store import MemoryStore
from assistant_core.persistence.models import Base
from assistant_core.platform import db
from assistant_core.spec import AssistantSpec
from fastapi import Depends, FastAPI
from procrastinate.testing import InMemoryConnector
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool
from testcontainers.community.postgres import PostgresContainer
from veupathdb.eda.factory import close_all_eda_clients
from veupathdb.testing.wdk_credentials import (
    NO_CREDENTIALS_REASON,
    registered_wdk_token,
)
from veupathdb.wdk import auth_login
from veupathdb.wdk.site_router import get_site_router
from veupathdb_mcp.embeddings import (
    EmbeddingBase,
    FakeEmbedder,
    get_embedder,
    use_embedding_session_factory,
)

from pathfinder.ai.capabilities.security import warm_up_scanner
from pathfinder.ai.conversation.assistant_routing import resolve_turn_assistant
from pathfinder.ai.conversation.request_body import ChatRequestBody
from pathfinder.assistants.registry import get_assistant_registry
from pathfinder.jobs.app import procrastinate_app
from pathfinder.jobs.tasks import ensure_registered
from pathfinder.main import create_app
from pathfinder.persistence.models import User
from pathfinder.platform.config import get_settings
from pathfinder.platform.security import create_user_token, limiter
from pathfinder.services import wdk_identity
from pathfinder.services.eda import catalog
from pathfinder.tests._support.database import can_connect
from pathfinder.transport.http.deps import (
    get_current_user_with_db_row,
    require_registered_wdk_identity,
)
from pathfinder.transport.http.routers.chat import resolve_chat_assistant

# A test must never send a request to a real model.
pydantic_ai.models.ALLOW_MODEL_REQUESTS = False


def _get_test_database_url() -> str:
    url = (
        os.environ.get("DATABASE_URL")
        or "postgresql+asyncpg://postgres:postgres@localhost:5432/pathfinder_test"
    )
    if not url.startswith("postgresql"):
        msg = f"Tests require PostgreSQL DATABASE_URL, got: {url!r}."
        raise RuntimeError(msg)

    # Tests refuse to run against a database that is not a test database.
    allow = os.environ.get("ALLOW_NONTEST_DATABASE") == "1"
    if not allow and "pathfinder_test" not in url:
        msg = (
            "Refusing to run tests against a non-test database. "
            "Set DATABASE_URL to a test DB (suggested db name: 'pathfinder_test'), "
            "or set ALLOW_NONTEST_DATABASE=1 to override."
        )
        raise RuntimeError(msg)
    return url


# PostgreSQL.


@pytest.fixture(scope="session")
def database_url() -> str:
    # An empty result makes the session start a disposable Postgres.
    return os.environ.get("DATABASE_URL", "").strip()


@pytest.fixture(scope="session")
def postgres_container(
    database_url: str,
) -> Generator[PostgresContainer | None]:
    url = database_url or os.environ.get("DATABASE_URL", "").strip()
    # Another server can hold the port, so the URL counts only when it answers.
    if url and "postgresql" in url and not asyncio.run(can_connect(url)):
        url = ""
        os.environ.pop("DATABASE_URL", None)

    if url:
        yield None
        return

    # This requires Docker
    container = PostgresContainer(
        "pgvector/pgvector:pg16",
        username="postgres",
        password="postgres",
        dbname="pathfinder_test",
    )
    try:
        container.start()
    except Exception as exc:
        msg = (
            "DATABASE_URL was not set and Postgres could not be started via Docker. "
            "Fix by either:\n"
            "- setting DATABASE_URL to a test database URL, or\n"
            "- installing/running Docker so testcontainers can start Postgres.\n"
            f"Underlying error: {exc}"
        )
        raise RuntimeError(msg) from exc

    url_obj = make_url(container.get_connection_url()).set(
        drivername="postgresql+asyncpg"
    )
    os.environ["DATABASE_URL"] = url_obj.render_as_string(hide_password=False)
    yield container
    container.stop()


_PROCRASTINATE_SCHEMA_SQL = (
    Path(__file__).resolve().parents[3]
    / "alembic"
    / "versions"
    / "procrastinate_schema.sql"
).read_text()


def _apply_procrastinate_schema_sync(database_url: str) -> None:
    """Applies the Procrastinate schema through psycopg.

    Asyncpg rejects multi-statement SQL, and this schema is multi-statement.
    The call is idempotent, because it runs only when the tables are absent.
    """
    psycopg_url = database_url.replace("postgresql+asyncpg://", "postgresql://")
    with (
        psycopg.connect(psycopg_url, autocommit=True) as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_name = 'procrastinate_jobs'"
        )
        if cursor.fetchone() is not None:
            return
        cursor.execute(_PROCRASTINATE_SCHEMA_SQL.encode())


@pytest.fixture(scope="session")
async def db_engine(
    database_url: str, postgres_container: PostgresContainer | None
) -> AsyncGenerator[AsyncEngine]:
    del postgres_container
    database_url = _get_test_database_url()
    # An asyncpg connection belongs to the event loop that created it, and
    # tests run on different loops. NullPool prevents reuse across loops.
    engine = create_async_engine(database_url, poolclass=NullPool)

    async with engine.begin() as conn:
        await conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(EmbeddingBase.metadata.create_all)

    _apply_procrastinate_schema_sync(database_url)

    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture(scope="session")
def session_maker(db_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


@pytest.fixture(scope="session")
def patch_app_db_engine(
    db_engine: AsyncEngine, session_maker: async_sessionmaker[AsyncSession]
) -> None:
    """Points the global engine, session maker and job connector at the test database.

    The job connector is built at import time, which can happen before the
    test database is known, so this rebuilds it.
    """
    db._engine = db_engine
    db._session_factory_instance = session_maker
    use_embedding_session_factory(db.async_session_factory)

    get_settings.cache_clear()
    test_connector = procrastinate.PsycopgConnector(
        conninfo=to_psycopg_url(get_settings().database_url),
    )
    procrastinate_app.connector = test_connector
    procrastinate_app.job_manager.connector = test_connector


@pytest.fixture(autouse=True)
def _restored_logger_config() -> Generator[None]:
    """Puts back the structlog configuration a test replaced.

    The configuration is process-wide, so a test must not inherit one.
    """
    was_configured = structlog.is_configured()
    saved = structlog.get_config()
    yield
    structlog.reset_defaults()
    if was_configured:
        structlog.configure(**saved)


@pytest.fixture(autouse=True)
def fake_embedder() -> FakeEmbedder:
    """The embedder in force is the deterministic fake, never a live API."""
    built = get_embedder()
    assert isinstance(built, FakeEmbedder)
    return built


@pytest.fixture
async def db_cleaner(
    db_engine: AsyncEngine,
    _eager_spawn: _SpawnedTasks,
) -> AsyncGenerator[None]:
    yield
    # A task still writing rows would hit a foreign key that the truncate
    # below has already removed, so the turn is settled first.
    await _eager_spawn.drain()
    # Truncate after each test so committed rows do not leak into the next one.
    async with db_engine.begin() as conn:
        await conn.exec_driver_sql(
            "TRUNCATE TABLE "
            "messages, conversations, exports, "
            "experiments, gene_sets, control_sets, users "
            "RESTART IDENTITY CASCADE"
        )
        # The store tables exist only after a memory test creates them.
        await conn.exec_driver_sql(
            "DO $$ BEGIN "
            "IF to_regclass('public.store') IS NOT NULL THEN "
            "TRUNCATE TABLE store, store_vectors RESTART IDENTITY CASCADE; "
            "END IF; END $$"
        )


@pytest.fixture
async def in_memory_jobs() -> AsyncGenerator[InMemoryConnector]:
    """Route deferred jobs to an in-memory connector, so a test decides when
    a job runs. The teardown restores the original connector.
    """
    original_connector = procrastinate_app.connector
    original_jm_connector = procrastinate_app.job_manager.connector
    connector = InMemoryConnector()
    procrastinate_app.connector = connector
    procrastinate_app.job_manager.connector = connector
    ensure_registered()
    try:
        yield connector
    finally:
        procrastinate_app.connector = original_connector
        procrastinate_app.job_manager.connector = original_jm_connector


# Environment and app.


@pytest.fixture(scope="session", autouse=True)
def _test_env_defaults() -> None:
    # The rate limiter stays off, because a test can exceed the request rate.
    limiter.enabled = False


@pytest.fixture(scope="session", autouse=True)
def _warm_the_input_scanner() -> None:
    """Load the injection model once, the way readiness loads it in production.

    The call returns without loading while screening is off. Where it is on,
    the first chat POST of the process would otherwise build the ONNX session
    inside the enqueue wait.
    """
    warm_up_scanner()


@pytest.fixture
def app() -> FastAPI:
    # Settings must read the current environment, not a cached value.
    get_settings.cache_clear()
    return create_app()


@pytest.fixture
async def client(
    app: FastAPI,
    patch_app_db_engine: None,
    db_cleaner: None,
) -> AsyncGenerator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"X-Requested-With": "XMLHttpRequest"},
    ) as c:
        yield c


@pytest.fixture
async def authed_user_id(
    patch_app_db_engine: None,
    db_cleaner: None,
) -> UUID:
    """Creates an anonymous user row and returns its id.

    The authenticated client fixture shares this user row.
    """
    del patch_app_db_engine, db_cleaner
    user_id = uuid4()
    async with db.async_session_factory() as session:
        session.add(User(id=user_id))
        await session.commit()
    return user_id


@pytest.fixture
def signed_in_to_veupathdb(app: FastAPI) -> Generator[None]:
    """Let the WDK-backed routes run as a user who holds a VEuPathDB session.

    The gate itself is covered by ``test_wdk_login_required``; a suite about
    what a route does once past it states that it is past it. Chat resolves
    its gate from the assistant, so that route drops the requirement instead
    of the dependency, and still routes and refuses as it does in production.
    """

    async def _identity(
        user_id: Annotated[UUID, Depends(get_current_user_with_db_row)],
    ) -> UUID:
        return user_id

    async def _assistant_without_identity(body: ChatRequestBody) -> AssistantSpec:
        return await resolve_turn_assistant(
            registry=get_assistant_registry(),
            conversation_id=body.conversation_id,
            requested_id=body.assistant_id,
        )

    app.dependency_overrides[require_registered_wdk_identity] = _identity
    app.dependency_overrides[resolve_chat_assistant] = _assistant_without_identity
    yield
    app.dependency_overrides.pop(require_registered_wdk_identity, None)
    app.dependency_overrides.pop(resolve_chat_assistant, None)


@pytest.fixture
async def authed_client(
    client: httpx.AsyncClient,
    authed_user_id: UUID,
    signed_in_to_veupathdb: None,
) -> httpx.AsyncClient:
    """Returns a client that carries a valid authentication cookie."""
    del signed_in_to_veupathdb
    token = create_user_token(authed_user_id)
    client.cookies.set("pathfinder-auth", token)
    return client


@pytest.fixture
async def app_memory_store(
    app: FastAPI,
    patch_app_db_engine: None,
    db_cleaner: None,
) -> AsyncGenerator[Any]:
    """Attaches a memory store to the application state.

    The test transport skips the lifespan that normally opens it.
    """
    del patch_app_db_engine, db_cleaner
    database_url = os.environ["DATABASE_URL"]
    async with lifespan_memory_store(database_url) as raw:
        store = MemoryStore(store=raw)
        app.state.memory_store = raw
        yield store


@pytest.fixture(scope="session")
async def wdk_registered_token() -> str | None:
    """The WDK token of the registered test account, or None when unconfigured.

    Resolved once for the whole session.
    """
    return await registered_wdk_token()


@pytest.fixture
def require_wdk_creds(wdk_registered_token: str | None) -> str:
    """The registered WDK token, or a skip naming the credentials to set."""
    if wdk_registered_token is None:
        pytest.skip(NO_CREDENTIALS_REASON)
    return wdk_registered_token


@pytest.fixture(autouse=True)
async def _close_wdk_clients_after_test() -> AsyncGenerator[None]:
    """Closes the shared WDK clients after a test.

    The clients are process-wide, so a test must not inherit an open one.
    """
    yield
    try:
        router = get_site_router()
        await router.close_all()
    except RuntimeError, OSError:
        pass  # The client is closed or the event loop is gone.


def _drop_identity_caches() -> None:
    auth_login._signing_keys.clear()
    wdk_identity._identities.clear()


@pytest.fixture(autouse=True)
def _clear_identity_caches() -> Generator[None]:
    """Drops the OAuth signing key and token-to-user caches around a test.

    Both are process-wide, so a test must not inherit one.
    """
    _drop_identity_caches()
    yield
    _drop_identity_caches()


def _drop_eda_study_caches() -> None:
    catalog._studies.clear()
    catalog._permission_maps.clear()
    catalog._details.clear()
    catalog._entity_totals.clear()


@pytest.fixture
def drop_eda_study_caches() -> Callable[[], None]:
    """Drop the process-wide EDA catalog reads part way through a test."""
    return _drop_eda_study_caches


@pytest.fixture(autouse=True)
def _clear_eda_study_caches() -> Generator[None]:
    """Drops the per-site EDA catalog reads around a test.

    The cache is process-wide, so a test must not inherit one.
    """
    _drop_eda_study_caches()
    yield
    _drop_eda_study_caches()


@pytest.fixture(autouse=True)
async def _close_eda_clients_after_test() -> AsyncGenerator[None]:
    """Closes the shared EDA clients after a test.

    The cache is process-wide, so a test must not inherit it.
    """
    yield
    # The client is closed or the event loop is gone.
    with contextlib.suppress(RuntimeError, OSError):
        await close_all_eda_clients()


# Background task control.

# A ceiling on a deadlock, not a budget for the work: an in-process turn
# settles in under a second on an idle machine, and a loaded one may take
# two orders of magnitude longer without being broken.
_SPAWN_DRAIN_CEILING_SECONDS = 120.0


@dataclass(frozen=True)
class _SpawnedTasks:
    """The tasks one test spawned, and the wait that settles them."""

    pending: set[asyncio.Task[Any]]

    async def drain(self) -> None:
        if not self.pending:
            return
        _done, timed_out = await asyncio.wait(
            set(self.pending),
            timeout=_SPAWN_DRAIN_CEILING_SECONDS,
        )
        for task in timed_out:
            task.cancel()
        if timed_out:
            await asyncio.gather(*timed_out, return_exceptions=True)


@pytest.fixture(autouse=True)
async def _eager_spawn(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncGenerator[_SpawnedTasks]:
    """Tracks every spawned task and awaits it during teardown.

    The tasks still run, but none of them outlives the test that started it.
    """
    spawned = _SpawnedTasks(pending=set())

    def _tracked_spawn(
        coro: Coroutine[Any, Any, Any], *, name: str | None = None
    ) -> asyncio.Task[Any] | None:
        try:
            task = asyncio.create_task(coro, name=name)
        except RuntimeError:
            coro.close()
            return None
        spawned.pending.add(task)
        task.add_done_callback(spawned.pending.discard)
        return task

    # Several modules import spawn by name, so patch every binding site.
    monkeypatch.setattr("pathfinder.platform.tasks.spawn", _tracked_spawn)
    monkeypatch.setattr("pathfinder.platform.store.spawn", _tracked_spawn)

    yield spawned

    await spawned.drain()
