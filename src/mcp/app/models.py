from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class NeisModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class NeisResult(NeisModel):
    CODE: str
    MESSAGE: str


class NeisSchool(NeisModel):
    ATPT_OFCDC_SC_CODE: str = Field(pattern=r"^[A-Z0-9]{3}$")
    ATPT_OFCDC_SC_NM: str
    SD_SCHUL_CODE: str = Field(pattern=r"^\d{7}$")
    SCHUL_NM: str
    SCHUL_KND_SC_NM: str
    LCTN_SC_NM: str
    ORG_RDNMA: str | None = None
    ORG_RDNDA: str | None = None


class NeisMeal(NeisModel):
    ATPT_OFCDC_SC_CODE: str = Field(pattern=r"^[A-Z0-9]{3}$")
    SD_SCHUL_CODE: str = Field(pattern=r"^\d{7}$")
    SCHUL_NM: str
    MMEAL_SC_CODE: str
    MLSV_YMD: str = Field(pattern=r"^\d{8}$")
    DDISH_NM: str | None = None
    CAL_INFO: str | None = None
    NTR_INFO: str | None = None
    ORPLC_INFO: str | None = None
    MLSV_FGR: float | None = None


def read_result(payload: Any) -> NeisResult | None:
    if not isinstance(payload, dict):
        return None
    result = payload.get("RESULT")
    if result is None:
        return None
    return NeisResult.model_validate(result)


class School(BaseModel):
    education_office_code: str
    education_office_name: str
    school_code: str
    name: str
    school_type: str
    region: str
    address: str | None


class SchoolSearchResult(BaseModel):
    query: str
    total_count: int = Field(ge=1)
    schools: list[School]


class Calorie(BaseModel):
    amount: float
    unit: Literal["kcal"] = "kcal"


class Nutrient(BaseModel):
    name: str
    amount: float
    unit: str


class IngredientOrigin(BaseModel):
    ingredient: str
    origin: str


class Meal(BaseModel):
    date: date
    dishes: list[str]
    calorie: Calorie | None
    nutrition: list[Nutrient]
    origin_info: list[IngredientOrigin]
    serving_count: float | None


class LunchSearchResult(BaseModel):
    education_office_code: str
    school_code: str
    school_name: str
    start_date: date
    end_date: date
    meal_type: Literal["LUNCH"] = "LUNCH"
    meals: list[Meal]

