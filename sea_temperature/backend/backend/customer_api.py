"""Customer APIs; all ownership comes from a validated session, never client IDs."""
from datetime import datetime, timedelta, timezone
import secrets
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Request, Response
from fastapi.security import HTTPBearer
from psycopg import Connection

from backend.config import get_settings
from backend.customer_schemas import (
    Customer, Farm, FarmInput, FarmPatch, GuestRegistration, LoginInput,
    Region, RegionCoordinates, SessionResult, SignupInput, Species,
)
from backend.customer_security import hash_password, login_limiter, token_hash, verify_password
from backend.db import get_customer_db
from backend.species_catalog import ABALONE_METHODS

COOKIE = "nifs_session"
DB = Annotated[Connection, Depends(get_customer_db, scope="function")]
CUSTOMER_FIELDS = "customer_id, membership_status, name, birth_date, phone_number, phone_verified_at"


def request_protection(request: Request, response: Response,
                       x_csrf_protection: Annotated[str | None, Header()] = None):
    response.headers["Cache-Control"] = "no-store"
    # A custom header forces browser cross-origin writes through CORS preflight.
    # Bearer credentials are explicitly attached by a server/client, never ambient cookies.
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        if not request.headers.get("Authorization") and x_csrf_protection != "1":
            raise HTTPException(403, "X-CSRF-Protection: 1 헤더가 필요합니다.")


router = APIRouter(prefix="/api", tags=["고객·양식장"],
                   dependencies=[Depends(request_protection), Depends(HTTPBearer(auto_error=False))])


def credential(request: Request) -> str:
    authorization = request.headers.get("Authorization")
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(401, "유효한 세션이 필요합니다.")
    else:
        token = request.cookies.get(COOKIE, "")
    if len(token) != 45 or token[:2] not in ("g_", "m_"):
        raise HTTPException(401, "로그인 또는 양식장 등록이 필요합니다.")
    return token


def current_customer(request: Request, db: Connection) -> dict:
    token = credential(request)
    row = db.execute("""
        SELECT c.*, s.session_id FROM customer_service.customers c
        JOIN customer_service.guest_sessions s USING (customer_id)
        WHERE s.token_hash = %s AND s.revoked_at IS NULL AND s.expires_at > CURRENT_TIMESTAMP
        FOR UPDATE OF c, s
    """, (token_hash(token),)).fetchone()
    expected = "guest" if token.startswith("g_") else "member"
    if row is None or row["membership_status"] != expected:
        raise HTTPException(401, "세션이 만료되었거나 해제되었습니다.")
    return row


def issue_session(db: Connection, customer: dict, response: Response) -> dict:
    settings = get_settings()
    guest = customer["membership_status"] == "guest"
    days = settings.guest_session_days if guest else settings.member_session_days
    token = ("g_" if guest else "m_") + secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(days=days)
    # Existing guest_sessions has no guest-only constraint: also store newly
    # issued member sessions here, keeping the existing schema unchanged.
    db.execute("""
        INSERT INTO customer_service.guest_sessions (customer_id, token_hash, expires_at)
        VALUES (%s, %s, %s)
    """, (customer["customer_id"], token_hash(token), expires))
    response.set_cookie(COOKIE, token, max_age=days * 86400, expires=expires,
                        httponly=True, secure=settings.session_cookie_secure, samesite="lax", path="/api")
    return {"access_token": token, "expires_at": expires, "customer": customer}


def validate_selection(db: Connection, data: FarmInput) -> dict:
    region = db.execute("""
        SELECT region_id, sigungu_name, area_name FROM public.sigungu_area_coordinates WHERE region_id = %s
    """, (data.region_id,)).fetchone()
    if region is None:
        raise HTTPException(422, "존재하는 지역 ID를 선택하세요.")
    species = db.execute("SELECT species_id, species_name FROM customer_service.species WHERE species_id = ANY(%s)",
                         (data.species_ids,)).fetchall()
    if len(species) != len(data.species_ids):
        raise HTTPException(422, "존재하는 품종 ID를 선택하세요.")
    for row in species:
        if row["species_name"] == "전복":
            raise HTTPException(422, "전복은 육상·해상 구분을 선택해 주세요.")
        expected = ABALONE_METHODS.get(row["species_name"])
        if expected and data.farming_method != expected:
            raise HTTPException(422, "선택한 전복 품종과 양식 방식이 일치하지 않습니다.")
    return region


def farm_row(db: Connection, customer_id: str, farm_id: UUID) -> dict:
    row = db.execute("""
        SELECT f.*, ARRAY(SELECT fs.species_id FROM customer_service.farm_species fs
                          WHERE fs.farm_id = f.farm_id ORDER BY fs.species_id) AS species_ids
        FROM customer_service.farms f WHERE f.farm_id = %s AND f.customer_id = %s
    """, (farm_id, customer_id)).fetchone()
    if row is None:
        raise HTTPException(404, "양식장을 찾을 수 없습니다.")
    return row


def replace_species(db: Connection, farm_id: UUID, ids: list[int]):
    db.execute("DELETE FROM customer_service.farm_species WHERE farm_id = %s", (farm_id,))
    for species_id in ids:
        db.execute("INSERT INTO customer_service.farm_species (farm_id, species_id) VALUES (%s, %s)",
                   (farm_id, species_id))


def insert_farm(db: Connection, customer_id: str, data: FarmInput) -> dict:
    region = validate_selection(db, data)
    row = db.execute("""
        INSERT INTO customer_service.farms
            (customer_id, region_id, sigungu_name, town_name, farming_method, insurance_status)
        VALUES (%s, %s, %s, %s, %s, %s) RETURNING farm_id
    """, (customer_id, data.region_id, region["sigungu_name"], region["area_name"],
          data.farming_method, data.insurance_status)).fetchone()
    replace_species(db, row["farm_id"], data.species_ids)
    return farm_row(db, customer_id, row["farm_id"])


@router.get("/regions", response_model=list[Region])
def regions(db: DB, sigungu_name: str | None = None):
    return db.execute("""
        SELECT region_id, sigungu_name, area_name, latitude, longitude
        FROM public.sigungu_area_coordinates
        WHERE (%s::text IS NULL OR sigungu_name = %s)
        ORDER BY sigungu_name, area_name, region_id
    """, (sigungu_name, sigungu_name)).fetchall()


@router.get("/species", response_model=list[Species])
def species(db: DB):
    return db.execute("SELECT species_id, species_name FROM customer_service.species ORDER BY species_id").fetchall()


@router.get("/regions/{region_id}", response_model=RegionCoordinates, tags=["지역 좌표"])
def region_coordinates(region_id: Annotated[int, Path(gt=0)], db: DB):
    row = db.execute("""
        SELECT region_id, sigungu_name, area_name, latitude, longitude,
               coordinate_type, source_url, aquaculture_coordinate_verification
        FROM public.sigungu_area_coordinates WHERE region_id = %s
    """, (region_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "선택한 지역의 좌표를 찾을 수 없습니다.")
    return row


@router.post("/guest-registrations", response_model=GuestRegistration, status_code=201)
def register_guest(data: FarmInput, db: DB, response: Response):
    # Validate before creating anything; the entire request is still one transaction.
    validate_selection(db, data)
    customer = db.execute(f"INSERT INTO customer_service.customers DEFAULT VALUES RETURNING {CUSTOMER_FIELDS}").fetchone()
    farm = insert_farm(db, customer["customer_id"], data)
    return {**issue_session(db, customer, response), "farm": farm}


@router.get("/me", response_model=Customer)
def me(request: Request, db: DB):
    return current_customer(request, db)


@router.get("/me/farms", response_model=list[Farm])
def my_farms(request: Request, db: DB):
    customer = current_customer(request, db)
    rows = db.execute("SELECT farm_id FROM customer_service.farms WHERE customer_id = %s ORDER BY created_at, farm_id",
                      (customer["customer_id"],)).fetchall()
    return [farm_row(db, customer["customer_id"], row["farm_id"]) for row in rows]


@router.post("/me/farms", response_model=Farm, status_code=201)
def add_farm(data: FarmInput, request: Request, db: DB):
    customer = current_customer(request, db)
    return insert_farm(db, customer["customer_id"], data)


@router.patch("/me/farms/{farm_id}", response_model=Farm)
def edit_farm(farm_id: UUID, data: FarmPatch, request: Request, db: DB):
    customer = current_customer(request, db)
    old = farm_row(db, customer["customer_id"], farm_id)
    changes = data.model_dump(exclude_unset=True)
    if not changes or any(value is None for value in changes.values()):
        raise HTTPException(422, "변경할 항목을 입력하세요. null은 허용되지 않습니다.")
    if changes.get("region_id", old["region_id"]) is None:
        raise HTTPException(422, "지역이 연결되지 않은 양식장은 region_id도 지정해 주세요.")
    merged = FarmInput.model_validate({k: changes.get(k, old[k]) for k in FarmInput.model_fields})
    region = validate_selection(db, merged)
    db.execute("""
        UPDATE customer_service.farms SET region_id=%s, sigungu_name=%s, town_name=%s,
            farming_method=%s, insurance_status=%s, updated_at=CURRENT_TIMESTAMP
        WHERE farm_id=%s AND customer_id=%s
    """, (merged.region_id, region["sigungu_name"], region["area_name"], merged.farming_method,
          merged.insurance_status, farm_id, customer["customer_id"]))
    replace_species(db, farm_id, merged.species_ids)
    return farm_row(db, customer["customer_id"], farm_id)


@router.delete("/me/farms/{farm_id}", status_code=204)
def delete_farm(farm_id: UUID, request: Request, db: DB):
    customer = current_customer(request, db)
    farm_row(db, customer["customer_id"], farm_id)
    db.execute("DELETE FROM customer_service.farms WHERE farm_id=%s AND customer_id=%s",
               (farm_id, customer["customer_id"]))


@router.post("/auth/signup", response_model=SessionResult, status_code=201)
def signup(data: SignupInput, request: Request, db: DB, response: Response):
    customer = current_customer(request, db)
    if customer["membership_status"] != "guest":
        raise HTTPException(409, "이미 가입한 고객입니다.")
    password = hash_password(data.password.get_secret_value())
    customer = db.execute(f"""
        UPDATE customer_service.customers SET membership_status='member', name=%s, birth_date=%s,
            phone_number=%s, password_hash=%s, registered_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP
        WHERE customer_id=%s RETURNING {CUSTOMER_FIELDS}
    """, (data.name, data.birth_date, data.phone_number, password, customer["customer_id"])).fetchone()
    db.execute("UPDATE customer_service.guest_sessions SET revoked_at=CURRENT_TIMESTAMP WHERE customer_id=%s AND revoked_at IS NULL",
               (customer["customer_id"],))
    return issue_session(db, customer, response)


# A valid dummy hash makes unknown-phone and incorrect-password verification comparable.
_DUMMY_HASH = hash_password(secrets.token_urlsafe(32))


@router.post("/auth/login", response_model=SessionResult)
def login(data: LoginInput, request: Request, db: DB, response: Response):
    ip = request.client.host if request.client else "unknown"
    login_limiter.check(ip)
    login_limiter.check("phone:" + token_hash(data.phone_number))
    customer = db.execute("""
        SELECT * FROM customer_service.customers WHERE phone_number=%s AND membership_status='member'
    """, (data.phone_number,)).fetchone()
    valid = verify_password(data.password.get_secret_value(), customer["password_hash"] if customer else _DUMMY_HASH)
    if not valid or customer is None:
        raise HTTPException(401, "전화번호 또는 비밀번호를 확인하세요.")
    return issue_session(db, customer, response)


@router.post("/auth/logout", status_code=204)
def logout(request: Request, db: DB, response: Response):
    token = credential(request)
    db.execute("UPDATE customer_service.guest_sessions SET revoked_at=CURRENT_TIMESTAMP WHERE token_hash=%s AND revoked_at IS NULL",
               (token_hash(token),))
    response.delete_cookie(COOKIE, path="/api", httponly=True,
                           secure=get_settings().session_cookie_secure, samesite="lax")
