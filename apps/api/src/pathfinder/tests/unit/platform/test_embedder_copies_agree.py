"""The drift gate over the two installed copies of the embedder.

This application is the only process that installs both distributions, so it
is the only one that can compare them.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import assistant_core.embeddings.embedder
import assistant_core.embeddings.fake
import pytest
import veupathdb_mcp
import veupathdb_mcp.embeddings
import veupathdb_mcp.embeddings.embedder
from assistant_core.platform.config import RuntimeSettings
from veupathdb_mcp.embeddings import EmbeddingSettings

MODULES = ("embedder.py", "fake.py", "openai_embedder.py")
SETTINGS_FIELDS = (
    "embedding_model",
    "embedding_batch_size",
    "embedding_input_char_limit",
    "embedding_request_concurrency",
)
# The distribution-specific names the two copies are allowed to differ in.
# Both copies render them to the same placeholder before the compare.
SUBSTITUTIONS = {
    "assistant_core": "distribution",
    "veupathdb_mcp": "distribution",
    "get_runtime_settings": "settings_source",
    "get_embedding_settings": "settings_source",
    "RuntimeSettings": "settings_type",
    "EmbeddingSettings": "settings_type",
    "RuntimeError": "error_base",
    "SemanticIndexUnavailableError": "error_base",
}
STORED_WIDTH = re.compile(r"^_EMBEDDING_DIMENSIONS = (\d+)$", re.MULTILINE)

RUNTIME_ROOT = Path(assistant_core.embeddings.embedder.__file__).resolve().parent
TOOL_SERVER_ROOT = Path(veupathdb_mcp.embeddings.embedder.__file__).resolve().parent
REVISION = "alembic/versions/2026_08_29_0001_add_embedding_record_manager.py"
APPLICATION_REVISION = Path(__file__).resolve().parents[5] / REVISION
TOOL_SERVER_REVISION = Path(veupathdb_mcp.__file__).resolve().parent / REVISION


def _normalized(path: Path) -> str:
    """The module's statements, with the distribution-specific names replaced.

    The module docstring and the top-level imports name the distribution and
    its settings source, which the decision page records as free to differ.
    """
    tree = ast.parse(path.read_text())
    body = tree.body[1:] if ast.get_docstring(tree) is not None else tree.body
    tree.body = [
        statement
        for statement in body
        if not isinstance(statement, ast.Import | ast.ImportFrom)
    ]
    source = ast.unparse(tree)
    for name, placeholder in SUBSTITUTIONS.items():
        source = source.replace(name, placeholder)
    return source


def _stored_width(path: Path) -> int:
    match = STORED_WIDTH.search(path.read_text())
    assert match is not None, f"{path} declares no _EMBEDDING_DIMENSIONS"
    return int(match.group(1))


@pytest.mark.parametrize("module", MODULES)
def test_the_two_copies_of_a_module_are_the_same_code(module: str) -> None:
    """A change to one copy that the other does not take fails here."""
    assert _normalized(RUNTIME_ROOT / module) == _normalized(TOOL_SERVER_ROOT / module)


def test_both_copies_embed_at_the_same_width() -> None:
    """The width every vector this system stores is one number."""
    assert assistant_core.embeddings.embedder.EMBEDDING_DIMENSIONS == 1024
    assert (
        veupathdb_mcp.embeddings.embedder.EMBEDDING_DIMENSIONS
        == assistant_core.embeddings.embedder.EMBEDDING_DIMENSIONS
    )


def test_both_chains_build_the_vector_column_at_that_width() -> None:
    """A column built at one width and an embedder at another fails on insert."""
    assert _stored_width(APPLICATION_REVISION) == 1024
    assert _stored_width(TOOL_SERVER_REVISION) == 1024


async def test_both_copies_seed_the_fake_embedder_the_same_way() -> None:
    """The offline embedder answers the same vector in both distributions."""
    text = "PF3D7_1133400 apical membrane antigen 1"
    runtime = await assistant_core.embeddings.fake.FakeEmbedder().embed_query(text)
    tool_server = await veupathdb_mcp.embeddings.FakeEmbedder().embed_query(text)

    assert len(runtime) == 1024
    assert runtime == tool_server


@pytest.mark.parametrize("field", SETTINGS_FIELDS)
def test_the_two_settings_sources_default_the_field_the_same_way(field: str) -> None:
    """One copy that moves a default alone splits the two indexes."""
    assert (
        RuntimeSettings.model_fields[field].default
        == EmbeddingSettings.model_fields[field].default
    )
