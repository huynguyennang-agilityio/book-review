"""Auth với khoá tự sinh trong test, không gọi Supabase thật."""

import time
from collections.abc import Iterator
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from book_review_api.auth import get_jwks_client
from book_review_api.config import Settings, get_settings
from book_review_api.main import app

SUPABASE_URL = "https://test-project.supabase.co"
ISSUER = f"{SUPABASE_URL}/auth/v1"
SECRET = "test-secret-at-least-32-bytes-long-xxxxxxxx"
USER_ID = "8f1c2a4e-1111-4222-8333-444455556666"

EC_KEY = ec.generate_private_key(ec.SECP256R1())
OTHER_EC_KEY = ec.generate_private_key(ec.SECP256R1())


class FakeJWKClient:
    """Thay PyJWKClient: trả public key theo `kid`, không gọi mạng."""

    def __init__(self, keys: dict[str, Any]) -> None:
        self.keys = keys

    def get_signing_key_from_jwt(self, token: str) -> jwt.PyJWK:
        kid = jwt.get_unverified_header(token).get("kid")
        if kid not in self.keys:
            raise jwt.PyJWKClientError(f"Unable to find a signing key that matches: {kid}")
        return jwt.PyJWK.from_dict(
            {**jwt.algorithms.ECAlgorithm.to_jwk(self.keys[kid], as_dict=True), "kid": kid},
            algorithm="ES256",
        )


def claims(**overrides: Any) -> dict[str, Any]:
    now = int(time.time())
    base: dict[str, Any] = {
        "sub": USER_ID,
        "email": "reader@example.com",
        "role": "authenticated",
        "aud": "authenticated",
        "iss": ISSUER,
        "iat": now,
        "exp": now + 3600,
    }
    base.update(overrides)
    return {k: v for k, v in base.items() if v is not None}


def hs256(**overrides: Any) -> str:
    return jwt.encode(claims(**overrides), SECRET, algorithm="HS256")


def es256(key: Any = EC_KEY, kid: str = "key-1", **overrides: Any) -> str:
    return jwt.encode(claims(**overrides), key, algorithm="ES256", headers={"kid": kid})


@pytest.fixture
def client() -> Iterator[TestClient]:
    settings = Settings(supabase_url=SUPABASE_URL, supabase_jwt_secret=SECRET, _env_file=None)  # type: ignore[call-arg]
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_jwks_client] = lambda: FakeJWKClient(
        {"key-1": EC_KEY.public_key()}
    )
    yield TestClient(app)
    app.dependency_overrides.clear()


def get_me(client: TestClient, token: str | None) -> Any:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.get("/me", headers=headers)


def assert_error(resp: Any, status: int, code: str) -> None:
    assert resp.status_code == status
    body = resp.json()
    assert set(body) == {"code", "message_vi", "retryable"}
    assert body["code"] == code
    assert body["message_vi"]
    assert body["retryable"] is False


@pytest.mark.parametrize("token_factory", [hs256, es256], ids=["hs256", "es256-jwks"])
def test_valid_token(client: TestClient, token_factory: Any) -> None:
    resp = get_me(client, token_factory())
    assert resp.status_code == 200
    assert resp.json() == {
        "user_id": USER_ID,
        "email": "reader@example.com",
        "role": "authenticated",
    }


@pytest.mark.parametrize("token_factory", [hs256, es256], ids=["hs256", "es256-jwks"])
def test_expired_token(client: TestClient, token_factory: Any) -> None:
    resp = get_me(client, token_factory(exp=int(time.time()) - 60))
    assert_error(resp, 401, "TOKEN_EXPIRED")


def test_missing_token(client: TestClient) -> None:
    resp = get_me(client, None)
    assert_error(resp, 401, "UNAUTHORIZED")
    assert resp.headers["www-authenticate"] == "Bearer"


def test_non_bearer_scheme(client: TestClient) -> None:
    resp = client.get("/me", headers={"Authorization": "Basic abc"})
    assert_error(resp, 401, "UNAUTHORIZED")


@pytest.mark.parametrize(
    "token",
    [
        pytest.param("not-a-jwt", id="garbage"),
        pytest.param(
            jwt.encode(claims(), "wrong-secret-at-least-32-bytes-long-xx", algorithm="HS256"),
            id="wrong-secret",
        ),
        pytest.param(es256(key=OTHER_EC_KEY), id="wrong-ec-key"),
        pytest.param(es256(kid="unknown"), id="unknown-kid"),
        pytest.param(hs256(aud="anon"), id="wrong-audience"),
        pytest.param(hs256(iss="https://evil.example/auth/v1"), id="wrong-issuer"),
        pytest.param(hs256(sub=None), id="missing-sub"),
        pytest.param(jwt.encode(claims(), "", algorithm="none"), id="alg-none"),
    ],
)
def test_invalid_token(client: TestClient, token: str) -> None:
    assert_error(get_me(client, token), 401, "UNAUTHORIZED")


def test_hs256_rejected_when_secret_not_configured() -> None:
    settings = Settings(supabase_url=SUPABASE_URL, supabase_jwt_secret="", _env_file=None)  # type: ignore[call-arg]
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_jwks_client] = lambda: None
    try:
        assert_error(get_me(TestClient(app), hs256()), 401, "UNAUTHORIZED")
    finally:
        app.dependency_overrides.clear()
