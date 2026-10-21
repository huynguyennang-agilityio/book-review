from fastapi import FastAPI
from fastapi.testclient import TestClient

from book_review_api.errors import ERROR_SPECS, AppError, ErrorCode, register_error_handlers


def make_client() -> TestClient:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/raise/{code}")
    def raise_code(code: ErrorCode) -> None:
        raise AppError(code)

    @app.get("/custom")
    def custom() -> None:
        raise AppError(ErrorCode.BOOK_NOT_FOUND, "Không tìm thấy «Sách ma».")

    @app.get("/items/{item_id}")
    def item(item_id: int) -> dict[str, int]:
        return {"item_id": item_id}

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("secret detail")

    return TestClient(app, raise_server_exceptions=False)


def test_every_code_has_spec() -> None:
    assert set(ERROR_SPECS) == set(ErrorCode)


def test_app_error_format_for_every_code() -> None:
    client = make_client()
    for code, spec in ERROR_SPECS.items():
        resp = client.get(f"/raise/{code}")
        assert resp.status_code == spec.status_code, code
        assert resp.json() == {
            "code": code.value,
            "message_vi": spec.message_vi,
            "retryable": spec.retryable,
        }


def test_custom_message() -> None:
    resp = make_client().get("/custom")
    assert resp.status_code == 404
    assert resp.json()["message_vi"] == "Không tìm thấy «Sách ma»."


def test_unknown_route_uses_not_found() -> None:
    resp = make_client().get("/nope")
    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"


def test_validation_error() -> None:
    resp = make_client().get("/items/abc")
    assert resp.status_code == 422
    assert resp.json()["code"] == "VALIDATION_ERROR"


def test_unhandled_exception_hides_detail() -> None:
    resp = make_client().get("/boom")
    assert resp.status_code == 500
    body = resp.json()
    assert body["code"] == "INTERNAL_ERROR"
    assert body["retryable"] is True
    assert "secret" not in resp.text
