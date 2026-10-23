"""Phân loại lỗi Fal: lỗi tài khoản (hết tiền, khoá, 429) tách khỏi lỗi của ảnh."""

import fal_client
import httpx
import pytest

from book_review_api.providers.image_fal import ImageAccountError, ImageError, _wrap


def http_error(status: int) -> fal_client.FalClientHTTPError:
    response = httpx.Response(status, request=httpx.Request("POST", "https://queue.fal.run/x"))
    return fal_client.FalClientHTTPError("Exhausted balance", status, {}, response)


@pytest.mark.parametrize("status", [401, 402, 403, 429])
def test_account_status_codes_become_account_error(status: int) -> None:
    err = _wrap(http_error(status), "Fal lỗi")
    assert isinstance(err, ImageAccountError)
    assert str(status) in str(err)


@pytest.mark.parametrize("status", [400, 422, 500, 503])
def test_other_status_codes_stay_image_error(status: int) -> None:
    err = _wrap(http_error(status), "Fal lỗi")
    assert type(err) is ImageError


def test_non_http_errors_stay_image_error() -> None:
    assert type(_wrap(RuntimeError("boom"), "Fal lỗi")) is ImageError
