"""FastAPI app: auth, AG-UI endpoint, REST (xem docs/plan/day-03.md)."""

from fastapi import FastAPI

app = FastAPI(title="Book Review API")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
