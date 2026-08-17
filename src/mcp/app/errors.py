import json
from dataclasses import dataclass

from mcp.server.fastmcp.exceptions import ToolError


@dataclass(slots=True)
class AppError(Exception):
    code: str
    message: str
    retryable: bool = False
    field: str | None = None

    def as_tool_error(self) -> ToolError:
        payload: dict[str, str | bool] = {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
        }
        if self.field is not None:
            payload["field"] = self.field
        return ToolError(json.dumps(payload, ensure_ascii=False))


def invalid_input(message: str, field: str) -> AppError:
    return AppError(code="INVALID_INPUT", message=message, field=field)


def school_not_found() -> AppError:
    return AppError(
        code="SCHOOL_NOT_FOUND",
        message="검색 조건에 맞는 학교가 없습니다.",
    )


def meal_not_found() -> AppError:
    return AppError(
        code="MEAL_NOT_FOUND",
        message="선택한 학교와 기간에 등록된 중식 정보가 없습니다.",
    )


def neis_bad_response() -> AppError:
    return AppError(
        code="NEIS_BAD_RESPONSE",
        message="NEIS에서 올바른 응답을 받지 못했습니다.",
        retryable=True,
    )


def neis_unavailable() -> AppError:
    return AppError(
        code="NEIS_UNAVAILABLE",
        message="NEIS에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.",
        retryable=True,
    )


def neis_timeout() -> AppError:
    return AppError(
        code="NEIS_TIMEOUT",
        message="NEIS 응답이 지연되고 있습니다. 잠시 후 다시 시도해 주세요.",
        retryable=True,
    )


def internal_error() -> AppError:
    return AppError(
        code="INTERNAL_ERROR",
        message="요청을 처리하지 못했습니다.",
        retryable=True,
    )

