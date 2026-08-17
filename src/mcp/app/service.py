import html
import re
from datetime import date, datetime

from app.errors import (
    invalid_input,
    meal_not_found,
    neis_bad_response,
    school_not_found,
)
from app.models import (
    Calorie,
    IngredientOrigin,
    LunchSearchResult,
    Meal,
    NeisMeal,
    NeisSchool,
    Nutrient,
    School,
    SchoolSearchResult,
)
from app.neis import NeisClient

_BR = re.compile(r"<\s*br\s*/?\s*>", re.IGNORECASE)
_TAG = re.compile(r"<[^>]*>")
_CALORIE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*kcal\s*$", re.IGNORECASE)
_NUTRIENT = re.compile(
    r"^\s*(?P<name>[^:()]+?)\s*\((?P<unit>[^()]+)\)\s*:\s*"
    r"(?P<amount>\d+(?:\.\d+)?)\s*$"
)


class MealService:
    def __init__(self, neis: NeisClient) -> None:
        self._neis = neis

    async def search_schools(
        self, query: str, max_results: int
    ) -> SchoolSearchResult:
        cleaned = query.strip()
        if not 2 <= len(cleaned) <= 100:
            raise invalid_input(
                "검색어는 앞뒤 공백을 제거한 뒤 2자 이상 100자 이하여야 합니다.",
                "query",
            )
        if not 1 <= max_results <= 100:
            raise invalid_input("max_results는 1 이상 100 이하여야 합니다.", "max_results")
        rows, total_count = await self._neis.search_schools(cleaned, max_results)
        if not rows:
            raise school_not_found()
        return SchoolSearchResult(
            query=cleaned,
            total_count=total_count,
            schools=[map_school(row) for row in rows],
        )

    async def get_lunches(
        self,
        education_office_code: str,
        school_code: str,
        start_date: date,
        end_date: date,
    ) -> LunchSearchResult:
        if not re.fullmatch(r"[A-Z0-9]{3}", education_office_code):
            raise invalid_input(
                "education_office_code는 영문 대문자 또는 숫자 3자리여야 합니다.",
                "education_office_code",
            )
        if not re.fullmatch(r"\d{7}", school_code):
            raise invalid_input(
                "school_code는 숫자 7자리여야 합니다.",
                "school_code",
            )
        if end_date < start_date:
            raise invalid_input(
                "end_date는 start_date보다 빠를 수 없습니다.",
                "end_date",
            )

        rows = await self._neis.get_lunches(
            education_office_code,
            school_code,
            start_date.strftime("%Y%m%d"),
            end_date.strftime("%Y%m%d"),
        )
        if not rows:
            raise meal_not_found()
        for row in rows:
            if (
                row.ATPT_OFCDC_SC_CODE != education_office_code
                or row.SD_SCHUL_CODE != school_code
                or row.MMEAL_SC_CODE != "2"
            ):
                raise neis_bad_response()
        meals = sorted((map_meal(row) for row in rows), key=lambda meal: meal.date)
        if any(not start_date <= meal.date <= end_date for meal in meals):
            raise neis_bad_response()
        return LunchSearchResult(
            education_office_code=education_office_code,
            school_code=school_code,
            school_name=rows[0].SCHUL_NM,
            start_date=start_date,
            end_date=end_date,
            meals=meals,
        )


def map_school(row: NeisSchool) -> School:
    address = " ".join(
        part.strip()
        for part in (row.ORG_RDNMA, row.ORG_RDNDA)
        if part and part.strip()
    )
    return School(
        education_office_code=row.ATPT_OFCDC_SC_CODE,
        education_office_name=row.ATPT_OFCDC_SC_NM,
        school_code=row.SD_SCHUL_CODE,
        name=row.SCHUL_NM,
        school_type=row.SCHUL_KND_SC_NM,
        region=row.LCTN_SC_NM,
        address=address or None,
    )


def map_meal(row: NeisMeal) -> Meal:
    try:
        meal_date = datetime.strptime(row.MLSV_YMD, "%Y%m%d").date()
    except ValueError as error:
        raise neis_bad_response() from error
    return Meal(
        date=meal_date,
        dishes=split_lines(row.DDISH_NM),
        calorie=parse_calorie(row.CAL_INFO),
        nutrition=parse_nutrition(row.NTR_INFO),
        origin_info=parse_origins(row.ORPLC_INFO),
        serving_count=row.MLSV_FGR,
    )


def split_lines(value: str | None) -> list[str]:
    if not value:
        return []
    values = []
    for part in _BR.split(value):
        unescaped = html.unescape(_TAG.sub("", part))
        cleaned = _TAG.sub("", unescaped).replace("<", "").replace(">", "").strip()
        if cleaned:
            values.append(cleaned)
    return values


def parse_calorie(value: str | None) -> Calorie | None:
    if not value or (match := _CALORIE.fullmatch(value)) is None:
        return None
    return Calorie(amount=float(match.group(1)))


def parse_nutrition(value: str | None) -> list[Nutrient]:
    nutrients = []
    for line in split_lines(value):
        if (match := _NUTRIENT.fullmatch(line)) is not None:
            nutrients.append(
                Nutrient(
                    name=match.group("name").strip(),
                    amount=float(match.group("amount")),
                    unit=match.group("unit").strip(),
                )
            )
    return nutrients


def parse_origins(value: str | None) -> list[IngredientOrigin]:
    origins = []
    for line in split_lines(value):
        ingredient, separator, origin = line.partition(":")
        if separator and ingredient.strip() and origin.strip():
            origins.append(
                IngredientOrigin(
                    ingredient=ingredient.strip(),
                    origin=origin.strip(),
                )
            )
    return origins

