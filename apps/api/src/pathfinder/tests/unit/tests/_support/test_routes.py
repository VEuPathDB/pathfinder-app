"""The record a route-table test reads one API route through."""

from __future__ import annotations

from fastapi import APIRouter, FastAPI
from pydantic import BaseModel

from pathfinder.tests._support.routes import api_routes


class _Body(BaseModel):
    site_id: str


def _app() -> FastAPI:
    router = APIRouter(prefix="/api", tags=["probe"])

    @router.get("/things/{thing_id}", name="read_thing")
    async def read_thing(thing_id: str) -> str:
        return thing_id

    @router.post("/things")
    async def make_thing(body: _Body) -> str:
        return body.site_id

    app = FastAPI()
    app.include_router(router)
    return app


def test_it_binds_the_path_the_verbs_and_the_name() -> None:
    read = api_routes(_app().routes)[0]

    assert read.path == "/api/things/{thing_id}"
    assert "GET" in read.methods
    assert read.name == "read_thing"


def test_the_pairs_drop_the_verbs_the_framework_answers() -> None:
    """HEAD and OPTIONS answer no route this application declares."""
    read = api_routes(_app().routes)[0]

    assert read.pairs == [("GET", "/api/things/{thing_id}")]


def test_it_carries_the_tags_the_router_sets() -> None:
    assert api_routes(_app().routes)[0].tags == ("probe",)


def test_the_body_model_is_the_model_the_route_takes_and_nothing_otherwise() -> None:
    read, make = api_routes(_app().routes)

    assert (read.body_model, make.body_model) == (None, _Body)


def test_it_carries_the_endpoint_and_the_dependant() -> None:
    read = api_routes(_app().routes)[0]

    assert read.endpoint.__name__ == "read_thing"
    assert [param.name for param in read.dependant.path_params] == ["thing_id"]
