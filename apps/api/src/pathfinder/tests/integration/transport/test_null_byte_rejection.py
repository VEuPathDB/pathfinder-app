import httpx
import pytest

_SITE_ID_LIST_PATHS = [
    "/api/v1/conversations",
    "/api/v1/conversations/dismissed",
    "/api/v1/gene-sets",
]


@pytest.mark.parametrize("path", _SITE_ID_LIST_PATHS)
async def test_site_id_null_byte_returns_422(
    authed_client: httpx.AsyncClient, path: str
) -> None:
    response = await authed_client.get(path, params={"siteId": "\x00"})
    assert response.status_code == 422, (path, response.status_code, response.text)


@pytest.mark.parametrize("path", _SITE_ID_LIST_PATHS)
async def test_site_id_valid_value_is_accepted(
    authed_client: httpx.AsyncClient, path: str
) -> None:
    response = await authed_client.get(path, params={"siteId": "plasmodb"})
    assert response.status_code == 200, (path, response.status_code, response.text)


_NULL_BYTE_QUERY_CASES = [
    ("/api/v1/gene-sets", {"search": "\x00", "siteId": "plasmodb"}),
    ("/api/v1/conversations", {"search": "\x00"}),
]


@pytest.mark.parametrize(("path", "params"), _NULL_BYTE_QUERY_CASES)
async def test_null_byte_in_any_query_param_returns_422(
    authed_client: httpx.AsyncClient,
    path: str,
    params: dict[str, str],
) -> None:
    """PostgreSQL text cannot hold NUL, so it must never reach a query.

    Guarding one parameter at a time left every other free-text filter able
    to crash the request with asyncpg's CharacterNotInRepertoireError, which
    surfaces to the caller as a 500.
    """
    response = await authed_client.get(path, params=params)
    assert response.status_code == 422, (path, response.status_code, response.text)
    assert response.headers["content-type"].startswith("application/problem+json")


_NULL_BYTE_BODY_CASES = [
    (
        "/api/v1/gene-sets/import",
        {
            "name": "a" + chr(0) + "b",
            "siteId": "plasmodb",
            "rawText": "PF3D7_0100100",
        },
    ),
    (
        "/api/v1/conversations/step-counts",
        {
            "siteId": "plasmodb",
            "strategyAst": {
                "recordType": "gene" + chr(0),
                "root": {"searchName": "GenesByTaxon"},
            },
        },
    ),
]


@pytest.mark.parametrize(("path", "body"), _NULL_BYTE_BODY_CASES)
async def test_null_byte_in_request_body_is_422_not_500(
    authed_client: httpx.AsyncClient,
    path: str,
    body: dict[str, object],
) -> None:
    """A NUL that arrives in a JSON body must not reach Postgres as a crash.

    The URL guard cannot see body content, so asyncpg raised
    CharacterNotInRepertoireError mid-INSERT and the caller got a 500 for
    what is unstorable input.
    """
    response = await authed_client.post(path, json=body)
    assert response.status_code == 422, (path, response.status_code, response.text)
    assert response.headers["content-type"].startswith("application/problem+json")


async def test_escaped_backslash_before_u0000_is_not_rejected(
    authed_client: httpx.AsyncClient,
) -> None:
    """``\\u0000`` in a body is a backslash then "u0000", not a NUL.

    The body guard prefilters on those six bytes, so without confirming
    against the parsed value it would 422 a name a researcher can legally
    type.
    """
    response = await authed_client.post(
        "/api/v1/gene-sets/import",
        json={
            "name": "path" + chr(92) + chr(92) + "u0000",
            "siteId": "plasmodb",
            "rawText": "PF3D7_0100100",
        },
    )
    assert response.status_code != 422, response.text
