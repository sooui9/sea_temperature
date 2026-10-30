"""Contracts matching the existing customer_service schema."""
from datetime import date, datetime, timedelta, timezone
import re
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

PositiveID = Annotated[int, Field(gt=0)]
FarmingMethod = Literal["cage", "land_based"]
InsuranceStatus = Literal["insured", "uninsured", "unknown"]


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, hide_input_in_errors=True)


class FarmInput(InputModel):
    region_id: PositiveID
    farming_method: FarmingMethod
    insurance_status: InsuranceStatus
    species_ids: list[PositiveID] = Field(min_length=1, max_length=50)

    @field_validator("species_ids")
    @classmethod
    def unique_species(cls, value):
        if len(set(value)) != len(value):
            raise ValueError("품종 ID는 중복될 수 없습니다.")
        return value


class FarmPatch(InputModel):
    region_id: PositiveID | None = None
    farming_method: FarmingMethod | None = None
    insurance_status: InsuranceStatus | None = None
    species_ids: list[PositiveID] | None = Field(default=None, min_length=1, max_length=50)

    @field_validator("species_ids")
    @classmethod
    def unique_species(cls, value):
        if value is not None and len(set(value)) != len(value):
            raise ValueError("품종 ID는 중복될 수 없습니다.")
        return value


class LoginInput(InputModel):
    phone_number: str = Field(max_length=20)
    password: SecretStr

    @field_validator("phone_number")
    @classmethod
    def phone(cls, value):
        value = re.sub(r"[\s-]", "", value)
        if not re.fullmatch(r"010[0-9]{8}", value):
            raise ValueError("010으로 시작하는 휴대전화 번호를 입력하세요.")
        return value

    @field_validator("password")
    @classmethod
    def password_length(cls, value):
        if not 8 <= len(value.get_secret_value()) <= 128 or not value.get_secret_value().strip():
            raise ValueError("비밀번호는 8~128자로 입력하세요.")
        return value


class SignupInput(LoginInput):
    name: str = Field(min_length=1, max_length=100)
    birth_date: date

    @field_validator("birth_date")
    @classmethod
    def birth(cls, value):
        today = datetime.now(timezone(timedelta(hours=9))).date()
        if not date(1900, 1, 1) <= value <= today:
            raise ValueError("생년월일을 확인하세요.")
        return value


class Customer(BaseModel):
    customer_id: str
    membership_status: Literal["guest", "member"]
    name: str | None
    birth_date: date | None
    phone_number: str | None
    phone_verified_at: datetime | None


class Species(BaseModel):
    species_id: int
    species_name: str


class Region(BaseModel):
    region_id: int
    sigungu_name: str
    area_name: str
    latitude: float
    longitude: float


class RegionCoordinates(Region):
    coordinate_type: str | None = None
    source_url: str | None = None
    aquaculture_coordinate_verification: str | None = None


class Farm(BaseModel):
    farm_id: UUID
    customer_id: str
    region_id: int | None
    sigungu_name: str
    town_name: str
    farming_method: FarmingMethod
    insurance_status: InsuranceStatus
    species_ids: list[int]


class SessionResult(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime
    customer: Customer


class GuestRegistration(SessionResult):
    farm: Farm
