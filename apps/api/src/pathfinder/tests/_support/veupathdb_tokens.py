"""VEuPathDB bearer tokens the suites mint locally, and the JWKS that verifies them.

VEuPathDB signs its tokens with ES512 on P-521 and publishes the public half at
``<oauth url>/jwks``. A test key reproduces both halves without a network.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from http.cookies import SimpleCookie
from typing import Any

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import ec
from jwt.algorithms import ECAlgorithm
from pydantic import BaseModel, ConfigDict

OAUTH_URL = "https://oauth.test"
JWKS_URL = f"{OAUTH_URL}/jwks"
SUBJECT = "1248677203"
_AUDIENCE = "apiComponentSite"
_ALGORITHM = "ES512"


def make_signing_key() -> ec.EllipticCurvePrivateKey:
    """A fresh P-521 key, the curve the OAuth server signs with."""
    return ec.generate_private_key(ec.SECP521R1())


def jwks_body(private_key: ec.EllipticCurvePrivateKey) -> dict[str, Any]:
    """The JWKS the OAuth server publishes: one placeholder key and the EC one."""
    public = ECAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    return {
        "keys": [
            {"kid": "0", "kty": "oct", "alg": "HS512", "k": "<your_client_secret>"},
            {
                "kid": "1",
                "use": "sig",
                "kty": "EC",
                "alg": _ALGORITHM,
                "crv": public["crv"],
                "x": public["x"],
                "y": public["y"],
            },
        ],
    }


def veupathdb_token(
    private_key: ec.EllipticCurvePrivateKey,
    *,
    is_guest: bool = False,
    subject: str = SUBJECT,
) -> str:
    """A token of the shape a VEuPathDB site hands a browser session."""
    return jwt.encode(
        {
            "sub": subject,
            "is_guest": is_guest,
            "aud": _AUDIENCE,
            "exp": int(time.time()) + 3600,
        },
        private_key,
        algorithm=_ALGORITHM,
    )


class _TokenClaims(BaseModel):
    model_config = ConfigDict(extra="ignore")

    sub: str


def current_user_by_token(
    private_key: ec.EllipticCurvePrivateKey,
    emails: Mapping[str, str],
) -> Callable[[httpx.Request], httpx.Response]:
    """A site's ``GET /users/current``: a token the key signed names the
    registered account ``emails`` maps its subject to."""

    def answer(request: httpx.Request) -> httpx.Response:
        token = SimpleCookie(request.headers["cookie"])["Authorization"].value
        claims = _TokenClaims.model_validate(
            jwt.decode(
                token,
                private_key.public_key(),
                algorithms=[_ALGORITHM],
                audience=_AUDIENCE,
            ),
        )
        return httpx.Response(
            200,
            json={
                "id": int(claims.sub),
                "isGuest": False,
                "email": emails[claims.sub],
            },
        )

    return answer
