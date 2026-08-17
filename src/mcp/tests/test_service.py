from datetime import date

import httpx
import pytest

from app.errors import AppError
from app.neis import NeisClient
from app.service import MealService
from tests.conftest import neis_list


@pytest.mark.anyio
async def test_search_schools_maps_identifiers_and_address(school_row):
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200, json=neis_list("schoolInfo", [school_row])
        )
    )
    async with httpx.AsyncClient(
        base_url="https://open.neis.go.kr", transport=transport
    ) as http:
        result = await MealService(NeisClient(http, "secret")).search_schools(
            " 서울 ", 20
        )

    assert result.query == "서울"
    assert result.schools[0].education_office_code == "B10"
    assert result.schools[0].school_code == "7010569"
    assert result.schools[0].address == "서울특별시 서초구 효령로 197"


@pytest.mark.anyio
async def test_get_lunches_forces_lunch_and_maps_details(meal_row):
    seen_params = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_params
        seen_params = request.url.params
        return httpx.Response(
            200, json=neis_list("mealServiceDietInfo", [meal_row])
        )

    async with httpx.AsyncClient(
        base_url="https://open.neis.go.kr",
        transport=httpx.MockTransport(handler),
    ) as http:
        result = await MealService(NeisClient(http, "secret")).get_lunches(
            "B10",
            "7010569",
            date(2026, 8, 17),
            date(2026, 8, 17),
        )

    assert seen_params["MMEAL_SC_CODE"] == "2"
    assert seen_params["MLSV_FROM_YMD"] == "20260817"
    assert result.meals[0].dishes == ["현미밥", "된장국"]
    assert result.meals[0].calorie.amount == 742.3
    assert result.meals[0].nutrition[0].unit == "g"
    assert result.meals[0].origin_info[0].origin == "국내산"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("method", "arguments", "code"),
    [
        ("search_schools", ("가", 20), "INVALID_INPUT"),
        (
            "get_lunches",
            ("B10", "7010569", date(2026, 8, 18), date(2026, 8, 17)),
            "INVALID_INPUT",
        ),
    ],
)
async def test_service_rejects_invalid_input(method, arguments, code):
    service = MealService(None)
    with pytest.raises(AppError) as raised:
        await getattr(service, method)(*arguments)
    assert raised.value.code == code


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("method", "arguments", "code"),
    [
        ("search_schools", ("없는학교", 20), "SCHOOL_NOT_FOUND"),
        (
            "get_lunches",
            ("B10", "7010569", date(2026, 8, 17), date(2026, 8, 17)),
            "MEAL_NOT_FOUND",
        ),
    ],
)
async def test_service_distinguishes_empty_results(method, arguments, code):
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={"RESULT": {"CODE": "INFO-200", "MESSAGE": "데이터 없음"}},
        )
    )
    async with httpx.AsyncClient(
        base_url="https://open.neis.go.kr", transport=transport
    ) as http:
        service = MealService(NeisClient(http, "secret"))
        with pytest.raises(AppError) as raised:
            await getattr(service, method)(*arguments)
    assert raised.value.code == code


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("handler", "code"),
    [
        (
            lambda request: (_ for _ in ()).throw(
                httpx.ReadTimeout("slow", request=request)
            ),
            "NEIS_TIMEOUT",
        ),
        (
            lambda request: (_ for _ in ()).throw(
                httpx.ConnectError("down", request=request)
            ),
            "NEIS_UNAVAILABLE",
        ),
        (lambda request: httpx.Response(200, content=b"not-json"), "NEIS_BAD_RESPONSE"),
    ],
)
async def test_neis_failures_are_sanitized(handler, code):
    async with httpx.AsyncClient(
        base_url="https://open.neis.go.kr",
        transport=httpx.MockTransport(handler),
    ) as http:
        with pytest.raises(AppError) as raised:
            await MealService(NeisClient(http, "super-secret")).search_schools(
                "서울", 20
            )

    assert raised.value.code == code
    assert "super-secret" not in raised.value.message

