import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date

import httpx
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.errors import AppError, internal_error
from app.models import LunchSearchResult, SchoolSearchResult
from app.neis import NeisClient
from app.service import MealService
from app.settings import Settings

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AppContext:
    service: MealService


McpContext = Context[ServerSession, AppContext]


def create_server(
    settings: Settings | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> FastMCP[AppContext]:
    configured = settings or Settings()

    @asynccontextmanager
    async def lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
        timeout = httpx.Timeout(
            connect=configured.neis_connect_timeout,
            read=configured.neis_read_timeout,
            write=configured.neis_read_timeout,
            pool=configured.neis_connect_timeout,
        )
        http_client = httpx.AsyncClient(
            base_url=str(configured.neis_base_url).rstrip("/"),
            timeout=timeout,
            transport=transport
            or httpx.AsyncHTTPTransport(local_address="0.0.0.0"),
        )
        try:
            yield AppContext(
                service=MealService(
                    NeisClient(http_client, configured.api_key())
                )
            )
        finally:
            await http_client.aclose()

    server = FastMCP(
        "급식 배틀 MCP",
        instructions=(
            "학교 이름으로 NEIS 식별자를 찾은 뒤 선택한 학교의 날짜별 중식을 "
            "조회합니다."
        ),
        host=configured.mcp_host,
        port=configured.mcp_port,
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
        lifespan=lifespan,
    )

    @server.tool(name="search_schools", structured_output=True)
    async def search_schools(
        query: str,
        ctx: McpContext,
        max_results: int = 20,
    ) -> SchoolSearchResult:
        """학교 이름 일부로 학교와 교육청·학교 식별 코드를 검색합니다."""
        service = ctx.request_context.lifespan_context.service
        try:
            return await service.search_schools(query, max_results)
        except AppError as error:
            raise error.as_tool_error() from error
        except Exception as error:
            logger.exception("Unexpected search_schools failure")
            raise internal_error().as_tool_error() from error

    @server.tool(name="get_school_lunches", structured_output=True)
    async def get_school_lunches(
        education_office_code: str,
        school_code: str,
        start_date: date,
        end_date: date,
        ctx: McpContext,
    ) -> LunchSearchResult:
        """교육청·학교 코드와 시작일·종료일로 날짜별 중식을 조회합니다."""
        service = ctx.request_context.lifespan_context.service
        try:
            return await service.get_lunches(
                education_office_code,
                school_code,
                start_date,
                end_date,
            )
        except AppError as error:
            raise error.as_tool_error() from error
        except Exception as error:
            logger.exception("Unexpected get_school_lunches failure")
            raise internal_error().as_tool_error() from error

    @server.custom_route("/health", methods=["GET"], include_in_schema=False)
    async def health(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    return server


mcp = create_server()
