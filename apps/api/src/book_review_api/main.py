"""FastAPI app: auth, AG-UI endpoint, REST (xem docs/plan/day-03.md)."""

from typing import Annotated

from fastapi import Depends, FastAPI

from book_review_api.auth import CurrentUser, current_user
from book_review_api.errors import register_error_handlers

app = FastAPI(title="Book Review API")
register_error_handlers(app)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/me")
def me(user: Annotated[CurrentUser, Depends(current_user)]) -> CurrentUser:
    return user
