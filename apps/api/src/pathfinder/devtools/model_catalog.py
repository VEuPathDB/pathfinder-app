"""Compare the model catalog with what each provider serves, and probe a model.

Usage::

    python -m pathfinder.devtools.model_catalog check
    python -m pathfinder.devtools.model_catalog record
    python -m pathfinder.devtools.model_catalog probe <provider:model> ...

``check`` exits 1 when the catalog names a model its provider does not serve.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import struct
import sys
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from assistant_core.models.settings import build_model_settings
from pydantic import BaseModel, ConfigDict, Field, JsonValue, SecretStr, TypeAdapter
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import (
    BinaryContent,
    BinaryImage,
    ModelRequest,
    UserPromptPart,
)
from pydantic_ai.models import Model, ModelRequestParameters, infer_model

from pathfinder.domain.provider_keys import KEYABLE_PROVIDERS, KeyableProvider
from pathfinder.platform.config import get_settings
from pathfinder.platform.key_refusals import classify_refusal
from pathfinder.platform.model_catalog import (
    PRICES_AS_OF,
    ModelEntry,
    get_model_catalog,
)
from pathfinder.platform.model_keys import build_provider

FIXTURE_DIR = (
    Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "provider_models"
)

_TIMEOUT_SECONDS = 30
_PAGE_SIZE = 1000
_SNAPSHOT = re.compile(r"-(\d{8}|\d{4}-\d{2}-\d{2})$")
# The family word, then the first version number and an optional minor of 1-2 digits.
_FAMILY = re.compile(r"^([a-z]+)-(?:[a-z]+-)*?(\d+)(?:[.-](\d{1,2})(?!\d))?")
_PDF_WORD = "PATHFINDER"
_KEYABLE: TypeAdapter[KeyableProvider] = TypeAdapter(KeyableProvider)
_PROVIDER_OWNERS = frozenset({"openai", "openai-internal", "system"})


class _Listed(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str


class OpenAIModelPage(BaseModel):
    """``GET /v1/models`` of the OpenAI API."""

    model_config = ConfigDict(extra="ignore")

    data: list[_Listed] = []

    def ids(self) -> list[str]:
        return [m.id for m in self.data]


class AnthropicModelPage(BaseModel):
    """``GET /v1/models`` of the Anthropic API."""

    model_config = ConfigDict(extra="ignore")

    data: list[_Listed] = []
    has_more: bool = False
    last_id: str | None = None

    def ids(self) -> list[str]:
        return [m.id for m in self.data]


class _GoogleModel(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    name: str
    methods: list[str] = Field(default=[], alias="supportedGenerationMethods")


class GoogleModelPage(BaseModel):
    """``GET /v1beta/models`` of the Gemini API."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    models: list[_GoogleModel] = []
    next_page_token: str | None = Field(default=None, alias="nextPageToken")

    def ids(self) -> list[str]:
        """The generation models, without the ``models/`` prefix."""
        return [
            m.name.removeprefix("models/")
            for m in self.models
            if "generateContent" in m.methods
        ]


type ModelPage = OpenAIModelPage | AnthropicModelPage | GoogleModelPage


def parse_page(provider: KeyableProvider, body: JsonValue) -> ModelPage:
    """One page of a provider's model list, typed."""
    match provider:
        case "openai":
            return OpenAIModelPage.model_validate(body)
        case "anthropic":
            return AnthropicModelPage.model_validate(body)
        case "google":
            return GoogleModelPage.model_validate(body)


async def fetch_pages(provider: KeyableProvider, key: SecretStr) -> list[JsonValue]:
    """Every page of the provider's model list, as the provider sent it."""
    secret = key.get_secret_value()
    pages: list[JsonValue] = []
    async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
        cursor: str | None = None
        while True:
            response = await _request_page(client, provider, secret, cursor)
            response.raise_for_status()
            body: JsonValue = response.json()
            pages.append(body)
            page = parse_page(provider, body)
            match page:
                case AnthropicModelPage(has_more=True, last_id=str(last)):
                    cursor = last
                case GoogleModelPage(next_page_token=str(token)) if token:
                    cursor = token
                case _:
                    return pages


async def _request_page(
    client: httpx.AsyncClient,
    provider: KeyableProvider,
    secret: str,
    cursor: str | None,
) -> httpx.Response:
    match provider:
        case "openai":
            return await client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {secret}"},
            )
        case "anthropic":
            params: dict[str, str | int] = {"limit": _PAGE_SIZE}
            if cursor is not None:
                params["after_id"] = cursor
            return await client.get(
                "https://api.anthropic.com/v1/models",
                params=params,
                headers={"x-api-key": secret, "anthropic-version": "2023-06-01"},
            )
        case "google":
            params = {"pageSize": _PAGE_SIZE}
            if cursor is not None:
                params["pageToken"] = cursor
            return await client.get(
                "https://generativelanguage.googleapis.com/v1beta/models",
                params=params,
                headers={"x-goog-api-key": secret},
            )


def _version(model_name: str) -> tuple[str, tuple[int, ...]] | None:
    """``gpt-5.6-luna`` -> ``("gpt", (5, 6))``; None for a name with no version."""
    match = _FAMILY.match(model_name)
    if match is None:
        return None
    word, major, minor = match.groups()
    return word, (int(major),) if minor is None else (int(major), int(minor))


@dataclass(frozen=True)
class CatalogDrift:
    """How one provider's served models differ from the catalog."""

    provider: KeyableProvider
    not_served: list[str]
    not_in_catalog: list[str]


def compare(
    catalog: tuple[ModelEntry, ...], provider: KeyableProvider, served: list[str]
) -> CatalogDrift:
    """A served id stands for its dated snapshots, and a family is every id of the
    catalog's family word at or above the lowest version the catalog holds."""
    names = [e.model_name for e in catalog if e.provider == provider]
    bases = {_SNAPSHOT.sub("", s) for s in served}
    floors: dict[str, tuple[int, ...]] = {}
    for name in names:
        parsed = _version(name)
        if parsed is not None:
            word, version = parsed
            floors[word] = min(floors.get(word, version), version)
    candidates = set()
    for base in bases - set(names):
        parsed = _version(base)
        if (
            parsed is not None
            and parsed[0] in floors
            and parsed[1] >= floors[parsed[0]]
        ):
            candidates.add(base)
    return CatalogDrift(
        provider=provider,
        not_served=sorted(n for n in names if n not in bases),
        not_in_catalog=sorted(candidates),
    )


def _deployment_key(provider: KeyableProvider) -> SecretStr | None:
    key = get_settings().deployment_credential(provider)
    return SecretStr(key) if key.strip() else None


def render(drifts: list[CatalogDrift], skipped: list[KeyableProvider]) -> str:
    lines: list[str] = []
    for drift in drifts:
        lines.append(f"{drift.provider}:")
        lines.append(f"  not served: {', '.join(drift.not_served) or '(none)'}")
        lines.append(
            f"  served, not in the catalog: {', '.join(drift.not_in_catalog) or '(none)'}"
        )
    lines.extend(f"{p}: no deployment key, skipped" for p in skipped)
    lines.append(f"prices as of {PRICES_AS_OF.isoformat()}")
    return "\n".join(lines)


async def check() -> int:
    drifts: list[CatalogDrift] = []
    skipped: list[KeyableProvider] = []
    for provider in KEYABLE_PROVIDERS:
        key = _deployment_key(provider)
        if key is None:
            skipped.append(provider)
            continue
        pages = await fetch_pages(provider, key)
        served = [i for body in pages for i in parse_page(provider, body).ids()]
        drifts.append(compare(get_model_catalog(), provider, served))
    print(render(drifts, skipped))
    return 1 if any(d.not_served for d in drifts) else 0


class _OpenAIRow(BaseModel):
    model_config = ConfigDict(extra="allow")

    owned_by: str = ""


class _OpenAIListing(BaseModel):
    model_config = ConfigDict(extra="allow")

    data: list[_OpenAIRow] = []


def _without_account_models(provider: KeyableProvider, body: JsonValue) -> JsonValue:
    """Drop the models an account trained, which name the account."""
    if provider != "openai":
        return body
    listing = _OpenAIListing.model_validate(body)
    listing.data = [row for row in listing.data if row.owned_by in _PROVIDER_OWNERS]
    dumped: JsonValue = listing.model_dump(mode="json")
    return dumped


async def record() -> int:
    """Write each provider's first page under the fixture directory."""
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    for provider in KEYABLE_PROVIDERS:
        key = _deployment_key(provider)
        if key is None:
            print(f"{provider}: no deployment key, skipped")
            continue
        first = (await fetch_pages(provider, key))[0]
        first = _without_account_models(provider, first)
        path = FIXTURE_DIR / f"{provider}.json"
        path.write_text(json.dumps(first, indent=2) + "\n")
        print(f"{provider}: wrote {path.name}")
    return 0


def one_pixel_png() -> bytes:
    """A 1x1 red PNG."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    header = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    pixels = zlib.compress(b"\x00\xff\x00\x00")
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", pixels)
        + chunk(b"IEND", b"")
    )


def one_word_pdf(word: str = _PDF_WORD) -> bytes:
    """A one-page PDF that prints ``word``."""
    stream = f"BT /F1 36 Tf 72 700 Td ({word}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>"
        ),
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (number, body)
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref,
    )
    return bytes(out)


@dataclass(frozen=True)
class ProbeAnswer:
    """One request of a probe: the status, and what the model answered."""

    status: int
    text: str = ""
    model_name: str = ""
    usage: str = ""
    refusal: str = ""


async def _ask(
    model: Model, model_id: str, provider: KeyableProvider, content: list[Any]
) -> ProbeAnswer:
    settings = build_model_settings(model_id, thinking="medium")
    try:
        response = await model.request(
            [ModelRequest(parts=[UserPromptPart(content=content)])],
            settings,
            ModelRequestParameters(),
        )
    except ModelHTTPError as error:
        refusal = classify_refusal(provider, error.status_code, error.body)
        return ProbeAnswer(
            status=error.status_code, refusal="" if refusal is None else refusal.value
        )
    usage = response.usage
    return ProbeAnswer(
        status=200,
        text=response.text or "",
        model_name=response.model_name or "",
        usage=f"input={usage.input_tokens} output={usage.output_tokens}",
    )


@dataclass(frozen=True)
class Probe:
    """A model's answers to a plain request, one PNG and one PDF."""

    ready: ProbeAnswer
    image: ProbeAnswer
    document: ProbeAnswer

    @property
    def reads_images(self) -> bool:
        return self.image.status == 200

    @property
    def reads_documents(self) -> bool:
        return self.document.status == 200 and _PDF_WORD in self.document.text.upper()


async def probe(model: Model, model_id: str, provider: KeyableProvider) -> Probe:
    """Send the three requests the two attachment flags are measured by."""
    png = BinaryImage(data=one_pixel_png(), media_type="image/png")
    pdf = BinaryContent(data=one_word_pdf(), media_type="application/pdf")
    async with model:
        return Probe(
            ready=await _ask(model, model_id, provider, ["Reply with the word ready"]),
            image=await _ask(
                model, model_id, provider, ["What colour is this image?", png]
            ),
            document=await _ask(
                model,
                model_id,
                provider,
                ["What single word is printed in this document?", pdf],
            ),
        )


def _render_answer(label: str, answer: ProbeAnswer) -> str:
    if answer.status != 200:
        why = f", {answer.refusal}" if answer.refusal else ""
        return f"  {label}: refused ({answer.status}{why})"
    return (
        f"  {label}: accepted (200) model={answer.model_name} {answer.usage} "
        f"answer={answer.text.strip()[:60]!r}"
    )


def _deployment_model(
    model_id: str, provider: KeyableProvider, key: SecretStr
) -> Model:
    """The model on the deployment's key, unguarded so a refusal keeps its body."""
    return infer_model(
        model_id, provider_factory=lambda _: build_provider(provider, key)
    )


async def probe_ids(model_ids: list[str]) -> int:
    for model_id in model_ids:
        provider = _KEYABLE.validate_python(model_id.partition(":")[0])
        key = _deployment_key(provider)
        if key is None:
            print(f"{model_id}: no deployment key, skipped")
            continue
        result = await probe(
            _deployment_model(model_id, provider, key), model_id, provider
        )
        print(model_id)
        print(_render_answer("ready", result.ready))
        print(_render_answer("image", result.image))
        print(_render_answer("document", result.document))
        print(
            f"  supports_images={result.reads_images} "
            f"supports_documents={result.reads_documents}"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pathfinder.devtools.model_catalog")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check", help="compare the catalog with the served models")
    commands.add_parser("record", help="write each provider's model list fixture")
    probe_parser = commands.add_parser("probe", help="measure a model's flags")
    probe_parser.add_argument("model_ids", nargs="+")
    args = parser.parse_args(argv)
    match args.command:
        case "check":
            return asyncio.run(check())
        case "record":
            return asyncio.run(record())
        case _:
            return asyncio.run(probe_ids(args.model_ids))


if __name__ == "__main__":
    sys.exit(main())
