"""Mã lỗi ổn định trả về cho frontend dưới dạng {code, message_vi, retryable}."""

from enum import StrEnum

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException


class ErrorCode(StrEnum):
    # Nghiệp vụ
    BOOK_NOT_FOUND = "BOOK_NOT_FOUND"
    GENRE_EXCLUDED = "GENRE_EXCLUDED"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    PROVIDER_QUOTA = "PROVIDER_QUOTA"
    LOW_FAITHFULNESS = "LOW_FAITHFULNESS"
    RENDER_FAILED = "RENDER_FAILED"
    CANCELLED = "CANCELLED"
    INVALID_STATE = "INVALID_STATE"
    UNSUPPORTED_IMAGE = "UNSUPPORTED_IMAGE"
    IMAGE_TOO_LARGE = "IMAGE_TOO_LARGE"
    INVALID_IMAGE = "INVALID_IMAGE"
    UPLOAD_LIMIT = "UPLOAD_LIMIT"
    REVIEW_TOO_SHORT = "REVIEW_TOO_SHORT"
    REVIEW_TOO_LONG = "REVIEW_TOO_LONG"
    # Chung
    UNAUTHORIZED = "UNAUTHORIZED"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ErrorSpec(BaseModel):
    status_code: int
    message_vi: str
    retryable: bool


ERROR_SPECS: dict[ErrorCode, ErrorSpec] = {
    ErrorCode.BOOK_NOT_FOUND: ErrorSpec(
        status_code=404,
        message_vi="Không tìm thấy thông tin về cuốn sách này.",
        retryable=False,
    ),
    ErrorCode.GENRE_EXCLUDED: ErrorSpec(
        status_code=422,
        message_vi="Thể loại sách này chưa được hỗ trợ.",
        retryable=False,
    ),
    ErrorCode.BUDGET_EXCEEDED: ErrorSpec(
        status_code=402,
        message_vi="Đã vượt hạn mức chi phí cho phép.",
        retryable=False,
    ),
    ErrorCode.PROVIDER_UNAVAILABLE: ErrorSpec(
        status_code=503,
        message_vi="Dịch vụ AI tạm thời không phản hồi, vui lòng thử lại sau.",
        retryable=True,
    ),
    ErrorCode.PROVIDER_QUOTA: ErrorSpec(
        status_code=402,
        message_vi=(
            "Tài khoản tạo ảnh (Fal) hết tiền hoặc đang bị giới hạn. "
            "Nạp thêm hoặc đợi vài phút rồi bấm Thử lại."
        ),
        retryable=True,
    ),
    ErrorCode.LOW_FAITHFULNESS: ErrorSpec(
        status_code=422,
        message_vi="Kịch bản chưa bám sát nguồn, cần tạo lại.",
        retryable=True,
    ),
    ErrorCode.RENDER_FAILED: ErrorSpec(
        status_code=500,
        message_vi="Dựng video thất bại.",
        retryable=True,
    ),
    ErrorCode.CANCELLED: ErrorSpec(
        status_code=409,
        message_vi="Yêu cầu đã bị huỷ.",
        retryable=False,
    ),
    ErrorCode.INVALID_STATE: ErrorSpec(
        status_code=409,
        message_vi="Project không ở trạng thái cho phép thao tác này.",
        retryable=False,
    ),
    ErrorCode.UNSUPPORTED_IMAGE: ErrorSpec(
        status_code=415,
        message_vi="Chỉ nhận ảnh JPEG, PNG hoặc WebP.",
        retryable=False,
    ),
    ErrorCode.IMAGE_TOO_LARGE: ErrorSpec(
        status_code=413,
        message_vi="Ảnh quá nặng, tối đa 10 MB.",
        retryable=False,
    ),
    ErrorCode.INVALID_IMAGE: ErrorSpec(
        status_code=422,
        message_vi="Không mở được ảnh, file có thể bị hỏng.",
        retryable=False,
    ),
    ErrorCode.UPLOAD_LIMIT: ErrorSpec(
        status_code=409,
        message_vi="Project đã có đủ số ảnh tải lên tối đa.",
        retryable=False,
    ),
    ErrorCode.REVIEW_TOO_SHORT: ErrorSpec(
        status_code=422,
        message_vi="Phần ý chính của bài review quá ngắn, cần ít nhất 100 từ.",
        retryable=False,
    ),
    ErrorCode.REVIEW_TOO_LONG: ErrorSpec(
        status_code=422,
        message_vi="Bài review đọc dài hơn 5 phút, hãy cắt bớt.",
        retryable=False,
    ),
    ErrorCode.UNAUTHORIZED: ErrorSpec(
        status_code=401,
        message_vi="Bạn cần đăng nhập để tiếp tục.",
        retryable=False,
    ),
    ErrorCode.TOKEN_EXPIRED: ErrorSpec(
        status_code=401,
        message_vi="Phiên đăng nhập đã hết hạn, vui lòng đăng nhập lại.",
        retryable=False,
    ),
    ErrorCode.FORBIDDEN: ErrorSpec(
        status_code=403,
        message_vi="Bạn không có quyền thực hiện thao tác này.",
        retryable=False,
    ),
    ErrorCode.NOT_FOUND: ErrorSpec(
        status_code=404,
        message_vi="Không tìm thấy tài nguyên.",
        retryable=False,
    ),
    ErrorCode.VALIDATION_ERROR: ErrorSpec(
        status_code=422,
        message_vi="Dữ liệu gửi lên không hợp lệ.",
        retryable=False,
    ),
    ErrorCode.RATE_LIMITED: ErrorSpec(
        status_code=429,
        message_vi="Bạn thao tác quá nhanh, vui lòng thử lại sau ít phút.",
        retryable=True,
    ),
    ErrorCode.INTERNAL_ERROR: ErrorSpec(
        status_code=500,
        message_vi="Đã có lỗi xảy ra, vui lòng thử lại.",
        retryable=True,
    ),
}

_HTTP_STATUS_TO_CODE: dict[int, ErrorCode] = {
    401: ErrorCode.UNAUTHORIZED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.NOT_FOUND,
    422: ErrorCode.VALIDATION_ERROR,
    429: ErrorCode.RATE_LIMITED,
}


class ErrorResponse(BaseModel):
    code: ErrorCode
    message_vi: str
    retryable: bool


class AppError(Exception):
    """Lỗi có mã ổn định. `message_vi` để trống thì dùng câu mặc định của mã."""

    def __init__(self, code: ErrorCode, message_vi: str | None = None) -> None:
        self.code = code
        self.spec = ERROR_SPECS[code]
        self.message_vi = message_vi or self.spec.message_vi
        super().__init__(f"{code}: {self.message_vi}")

    def to_response(self) -> ErrorResponse:
        return ErrorResponse(
            code=self.code, message_vi=self.message_vi, retryable=self.spec.retryable
        )


def _json(err: AppError) -> JSONResponse:
    headers = {"WWW-Authenticate": "Bearer"} if err.spec.status_code == 401 else None
    return JSONResponse(
        status_code=err.spec.status_code,
        content=err.to_response().model_dump(mode="json"),
        headers=headers,
    )


async def _app_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    return _json(exc)


async def _http_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    code = _HTTP_STATUS_TO_CODE.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
    err = AppError(code)
    response = _json(err)
    # Giữ status gốc (vd 405) nếu không có mã riêng.
    response.status_code = exc.status_code
    return response


async def _validation_error_handler(_: Request, exc: Exception) -> JSONResponse:
    return _json(AppError(ErrorCode.VALIDATION_ERROR))


async def _unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
    return _json(AppError(ErrorCode.INTERNAL_ERROR))


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.add_exception_handler(Exception, _unhandled_error_handler)
