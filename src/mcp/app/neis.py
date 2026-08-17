from collections.abc import Mapping
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.errors import neis_bad_response, neis_timeout, neis_unavailable
from app.models import NeisMeal, NeisResult, NeisSchool, read_result

Row = TypeVar("Row", bound=BaseModel)


class NeisClient:
    def __init__(self, http_client: httpx.AsyncClient, api_key: str) -> None:
        self._http = http_client
        self._api_key = api_key

    async def search_schools(
        self, query: str, limit: int
    ) -> tuple[list[NeisSchool], int]:
        payload = await self._get(
            "/hub/schoolInfo",
            {"SCHUL_NM": query, "pIndex": 1, "pSize": limit},
        )
        return self._parse_list(payload, "schoolInfo", NeisSchool)

    async def get_lunches(
        self,
        education_office_code: str,
        school_code: str,
        start_date: str,
        end_date: str,
    ) -> list[NeisMeal]:
        page = 1
        rows: list[NeisMeal] = []
        while True:
            payload = await self._get(
                "/hub/mealServiceDietInfo",
                {
                    "ATPT_OFCDC_SC_CODE": education_office_code,
                    "SD_SCHUL_CODE": school_code,
                    "MMEAL_SC_CODE": "2",
                    "MLSV_FROM_YMD": start_date,
                    "MLSV_TO_YMD": end_date,
                    "pIndex": page,
                    "pSize": 100,
                },
            )
            page_rows, total_count = self._parse_list(
                payload, "mealServiceDietInfo", NeisMeal
            )
            rows.extend(page_rows)
            if len(rows) >= total_count:
                return rows
            if not page_rows:
                raise neis_bad_response()
            page += 1

    async def _get(
        self, path: str, parameters: Mapping[str, str | int]
    ) -> Any:
        try:
            response = await self._http.get(
                path,
                params={"Key": self._api_key, "Type": "json", **parameters},
            )
        except httpx.TimeoutException as error:
            raise neis_timeout() from error
        except httpx.RequestError as error:
            raise neis_unavailable() from error

        if response.status_code == 429 or response.status_code >= 500:
            raise neis_unavailable()
        if not 200 <= response.status_code < 300:
            raise neis_bad_response()
        try:
            return response.json()
        except ValueError as error:
            raise neis_bad_response() from error

    @staticmethod
    def _parse_list(
        payload: Any, resource: str, row_model: type[Row]
    ) -> tuple[list[Row], int]:
        try:
            top_result = read_result(payload)
        except ValidationError as error:
            raise neis_bad_response() from error
        if top_result is not None:
            if top_result.CODE == "INFO-200":
                return [], 0
            raise neis_bad_response()
        if not isinstance(payload, dict):
            raise neis_bad_response()
        sections = payload.get(resource)
        if not isinstance(sections, list):
            raise neis_bad_response()

        head: list[Any] | None = None
        raw_rows: list[Any] | None = None
        for section in sections:
            if not isinstance(section, dict):
                raise neis_bad_response()
            if "head" in section:
                head = section["head"]
            if "row" in section:
                raw_rows = section["row"]

        result, total_count = NeisClient._parse_head(head)
        if result.CODE == "INFO-200":
            return [], 0
        if result.CODE != "INFO-000" or not isinstance(raw_rows, list):
            raise neis_bad_response()
        try:
            return [row_model.model_validate(row) for row in raw_rows], total_count
        except ValidationError as error:
            raise neis_bad_response() from error

    @staticmethod
    def _parse_head(head: Any) -> tuple[NeisResult, int]:
        if not isinstance(head, list):
            raise neis_bad_response()
        result: NeisResult | None = None
        total_count: int | None = None
        for item in head:
            if not isinstance(item, dict):
                raise neis_bad_response()
            if "RESULT" in item:
                try:
                    result = NeisResult.model_validate(item["RESULT"])
                except ValidationError as error:
                    raise neis_bad_response() from error
            if "list_total_count" in item:
                count = item["list_total_count"]
                if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                    raise neis_bad_response()
                total_count = count
        if result is None or total_count is None:
            raise neis_bad_response()
        return result, total_count

