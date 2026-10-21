"""Xác thực JWT Supabase. Chỉ verify token người dùng, không dùng service key."""

from functools import lru_cache
from typing import Annotated, Any

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from book_review_api.config import Settings, get_settings
from book_review_api.errors import AppError, ErrorCode

ASYMMETRIC_ALGS = ["ES256", "RS256"]

_bearer = HTTPBearer(auto_error=False)


class CurrentUser(BaseModel):
    user_id: str
    email: str | None = None
    role: str | None = None


@lru_cache(maxsize=4)
def _jwks_client(url: str) -> jwt.PyJWKClient:
    # PyJWKClient tự cache key, tải lại khi gặp `kid` lạ (Supabase xoay khoá).
    return jwt.PyJWKClient(url, cache_keys=True, lifespan=600)


def get_jwks_client(settings: Annotated[Settings, Depends(get_settings)]) -> jwt.PyJWKClient | None:
    return _jwks_client(settings.supabase_jwks_url) if settings.supabase_url else None


def decode_token(token: str, settings: Settings, jwks: jwt.PyJWKClient | None) -> dict[str, Any]:
    try:
        alg = jwt.get_unverified_header(token).get("alg")
        options = {"require": ["exp", "sub"]}
        issuer = settings.supabase_issuer if settings.supabase_url else None
        if alg == "HS256":
            if not settings.supabase_jwt_secret:
                raise AppError(ErrorCode.UNAUTHORIZED)
            key: Any = settings.supabase_jwt_secret
            algorithms = ["HS256"]
        elif alg in ASYMMETRIC_ALGS:
            if jwks is None:
                raise AppError(ErrorCode.UNAUTHORIZED)
            key = jwks.get_signing_key_from_jwt(token).key
            algorithms = ASYMMETRIC_ALGS
        else:
            raise AppError(ErrorCode.UNAUTHORIZED)
        claims: dict[str, Any] = jwt.decode(
            token,
            key,
            algorithms=algorithms,
            audience=settings.supabase_jwt_audience,
            issuer=issuer,
            options=options,  # type: ignore[arg-type]
        )
        return claims
    except jwt.ExpiredSignatureError as exc:
        raise AppError(ErrorCode.TOKEN_EXPIRED) from exc
    except (jwt.PyJWTError, jwt.PyJWKClientError) as exc:
        raise AppError(ErrorCode.UNAUTHORIZED) from exc


def current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    settings: Annotated[Settings, Depends(get_settings)],
    jwks: Annotated[jwt.PyJWKClient | None, Depends(get_jwks_client)],
) -> CurrentUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AppError(ErrorCode.UNAUTHORIZED)
    claims = decode_token(credentials.credentials, settings, jwks)
    return CurrentUser(user_id=claims["sub"], email=claims.get("email"), role=claims.get("role"))
