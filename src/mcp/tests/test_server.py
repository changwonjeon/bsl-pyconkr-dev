import json

import httpx
import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from pydantic import SecretStr

from app.server import create_server
from app.settings import Settings
from tests.conftest import neis_list


def settings() -> Settings:
    return Settings(neis_api_key=SecretStr("secret"))


@pytest.mark.anyio
async def test_client_lists_tools():
    server = create_server(settings())
    async with create_connected_server_and_client_session(server) as session:
        result = await session.list_tools()

    assert {tool.name for tool in result.tools} == {
        "search_schools",
        "get_school_lunches",
    }
    assert result.tools[0].inputSchema["type"] == "object"


@pytest.mark.anyio
async def test_client_calls_tools_with_structured_output(school_row, meal_row):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/hub/schoolInfo":
            return httpx.Response(
                200, json=neis_list("schoolInfo", [school_row])
            )
        return httpx.Response(
            200, json=neis_list("mealServiceDietInfo", [meal_row])
        )

    server = create_server(settings(), httpx.MockTransport(handler))
    async with create_connected_server_and_client_session(server) as session:
        schools = await session.call_tool(
            "search_schools", {"query": "서울", "max_results": 10}
        )
        lunches = await session.call_tool(
            "get_school_lunches",
            {
                "education_office_code": "B10",
                "school_code": "7010569",
                "start_date": "2026-08-17",
                "end_date": "2026-08-17",
            },
        )

    assert schools.isError is False
    assert schools.structuredContent["schools"][0]["school_code"] == "7010569"
    assert lunches.isError is False
    assert lunches.structuredContent["meal_type"] == "LUNCH"
    assert lunches.structuredContent["meals"][0]["date"] == "2026-08-17"


@pytest.mark.anyio
async def test_tool_returns_standard_error_result_for_empty_search():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={"RESULT": {"CODE": "INFO-200", "MESSAGE": "데이터 없음"}},
        )
    )
    server = create_server(settings(), transport)
    async with create_connected_server_and_client_session(server) as session:
        result = await session.call_tool(
            "search_schools", {"query": "없는학교"}
        )

    assert result.isError is True
    _, separator, payload = result.content[0].text.partition(": ")
    assert separator
    error = json.loads(payload)
    assert error == {
        "code": "SCHOOL_NOT_FOUND",
        "message": "검색 조건에 맞는 학교가 없습니다.",
        "retryable": False,
    }
