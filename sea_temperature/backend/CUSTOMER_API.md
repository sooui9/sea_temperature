# 고객·비회원 API 연결 안내

기존 `customer_service` 테이블과 `public.sigungu_area_coordinates`의 실제 컬럼·제약조건에 맞춘 API입니다. Streamlit의 등록·회원가입·로그인 화면이 고객 API에 연결되어 있습니다. `public.roms_forecast`의 예측 격자 연결은 포함하지 않습니다. 현재 고객 ID는 DB가 생성하는 `C-...` 형식의 문자열이고 양식장 ID는 UUID입니다.

## 전복 품종 선택 저장

`customer_service.species`는 공통 품종 목록이고 고객별 선택은 `farm_species`가 연결합니다. 이번 기능은 새 테이블이나 컬럼을 만들지 않고 다음 두 품종 데이터를 사용합니다.

| 화면 선택 | `species.species_name` | 양식 방식 |
| --- | --- | --- |
| 전복 → 육상 | `전복(육상)` | `land_based` |
| 전복 → 해상 | `전복(해상)` | `cage` |

프론트는 두 항목을 ‘전복’으로 묶어 표시하고, 전복 선택 시에만 육상·해상 선택 버튼을 표시합니다. 제출 시 `/api/species`에서 받은 실제 ID를 `species_ids`에 넣습니다. 종을 고객마다 중복 생성하거나 ID를 하드코딩하지 않습니다. `farms`에는 별도의 전복 구분 컬럼을 추가하지 않습니다.

기존 `전복` 품종과 그 품종을 선택했던 고객 데이터는 그대로 유지합니다. 새 등록·수정 요청에서 미구분 `전복` ID를 보내면 422를 반환하며, 육상·해상 중 하나를 다시 선택해야 합니다. 두 전복 품종을 동시에 선택하거나 양식 방식이 맞지 않아도 거절합니다. 기존 기록의 구분을 임의로 추정해 바꾸지 않습니다.

전복 두 품종만 초기화하려면 프로젝트 최상위에서 실행하세요. 동일 이름이 있으면 기존 ID를 유지하며 재실행할 수 있습니다.

```powershell
Push-Location backend
py -m backend.manage seed-abalone-species
Pop-Location
```

SQL로 적용할 때는 `backend/database/02_abalone_species.sql`을 사용합니다. 구분을 바꿀 때는 기존 양식장에 `PATCH /api/me/farms/{farm_id}`로 새로운 `species_ids`와 맞는 `farming_method`를 함께 보내면 됩니다.

## 실행과 초기 데이터

프로젝트 최상위 폴더에서 실행합니다. `backend/backend/.env`의 기존 DB 연결 설정을 사용합니다.

```powershell
py -m pip install -r backend/backend/requirements.txt
py -m uvicorn backend.main:app --app-dir backend --reload --port 8000
```

`py` 실행 별칭에 문제가 있으면 설치된 Python 실행 파일 경로를 사용하세요.

```powershell
$python = "$env:LOCALAPPDATA\Python\pythoncore-3.14-64\python.exe"
& $python -m uvicorn backend.main:app --app-dir backend --reload --port 8000
```

API 문서: <http://127.0.0.1:8000/docs>

품종은 DB의 목록을 그대로 반환합니다. 아래 명령으로 기존 기본 품종, PDF에서 확인한 품종, 전복 육상·해상 항목 중 없는 데이터를 추가할 수 있습니다. **공유 DB에 쓰는 명령**이며, 기존 품종 ID와 이름은 수정하지 않습니다. 자동 실행하지 않습니다.

```powershell
Push-Location backend
py -m backend.manage seed-customer-species
Pop-Location
```

실행 DB 계정에는 `customer_service` 스키마 사용, 고객·양식장·품종 연결·세션 테이블의 필요한 SELECT/INSERT/UPDATE/DELETE 권한과, 지역·품종 목록 SELECT 권한이 필요합니다. 품종 초기화는 품종 INSERT 및 해당 identity sequence 사용 권한도 필요합니다. 계정의 권한은 자동으로 변경하지 않습니다.

## PDF에서 확인한 품종

| 제공 문서 | 확인 위치 | 품종 |
| --- | --- | --- |
| `cage_fish_research_full.pdf` | 15쪽 D-1 가입 대상 | 조피볼락(우럭), 볼락, 참돔, 돌돔, 감성돔, 점농어, 말쥐치, 참쥐치, 가숭어, 능성어, 방어 |
| `gul_research_full.pdf` | 1쪽 제목·대상 범위 | 굴 |
| `meongge_research_full.pdf` | 1쪽 제목·대상 범위 | 멍게 |
| `styela_research_full.pdf` | 1쪽 제목·대상 범위 | 미더덕, 오만둥이 |

문서의 비교 사례나 범위 밖 품종을 전부 자동 수집하지 않고 위 대상 품종을 반영했습니다. 기존 넙치·숭어·기타와 고객의 품종 연결은 유지합니다. 조피볼락은 기존 DB 표기 `조피볼락 (우럭)`을 사용합니다. `가숭어`를 기존 `숭어` 행에 합치거나 기존 ID를 재지정하지 않습니다.

초기 데이터 SQL은 `backend/database/03_research_species.sql`입니다. PDF 품종만 추가하려면 `backend` 폴더에서 `py -m backend.manage seed-research-species`를 실행합니다. 동일 이름이 있으면 기존 ID를 보존합니다.

등록 화면은 세션 시작 시 받은 품종 목록을 영구 고정하지 않고, 클라이언트의 60초 공개 목록 캐시를 매번 조회합니다. 즉시 반영하려면 등록 화면의 **목록 새로고침** 버튼을 누르세요. 이 버튼은 공개 목록 캐시만 비우며 입력한 값과 고객 토큰을 지우지 않습니다.

## 프론트 연결 순서

1. `GET /api/regions`, `GET /api/species`로 입력 목록을 조회합니다.
2. 양식장 등록 시 `POST /api/guest-registrations`를 호출합니다.
3. 응답의 `access_token`을 현재 사용자 세션에만 보관하고, 이후 요청에 `Authorization: Bearer <token>`을 전달합니다.
4. 재조회는 `GET /api/me`, `GET /api/me/farms`로 처리합니다.
5. 가입 시 현재 비회원 토큰으로 `POST /api/auth/signup`을 호출합니다. 응답의 새 회원 토큰으로 교체합니다. 고객 ID와 양식장 ID는 유지되고 기존 비회원 세션은 모두 폐기됩니다.
6. 기존 회원 로그인은 `POST /api/auth/login`, 로그아웃은 `POST /api/auth/logout`입니다.

Streamlit의 토큰이나 개인정보를 `st.cache_resource` 등 사용자 사이에 공유되는 캐시에 넣지 마세요. `client.py`·`app.py`는 사용자별 `st.session_state`에 토큰을 보관하고 공개 지역·품종 목록만 짧게 캐시합니다. 단독 HTML은 버튼을 포함한 화면 체험용이며 실제 DB 저장과 인증은 Streamlit에서 제공합니다.

## 엔드포인트

| 메서드 | 경로 | 인증 | 역할 |
| --- | --- | --- | --- |
| GET | `/api/regions?sigungu_name=통영시` | 없음 | 지역 ID·시군구·읍면동·좌표 조회 |
| GET | `/api/regions/{region_id}` | 없음 | 선택한 지역의 위도·경도·좌표 유형·출처 조회 |
| GET | `/api/species` | 없음 | 품종 ID·이름 조회 |
| POST | `/api/guest-registrations` | 없음 | 고객·양식장·품종 연결·비회원 세션을 하나의 트랜잭션으로 생성 |
| GET | `/api/me` | 비회원/회원 | 본인 고객 정보 조회, 비밀번호 해시 제외 |
| GET | `/api/me/farms` | 비회원/회원 | 본인 양식장 목록 |
| POST | `/api/me/farms` | 비회원/회원 | 본인 양식장 추가 |
| PATCH | `/api/me/farms/{farm_id}` | 비회원/회원 | 전달한 항목만 수정 |
| DELETE | `/api/me/farms/{farm_id}` | 비회원/회원 | 본인 양식장 삭제 |
| POST | `/api/auth/signup` | 비회원 | 같은 고객을 회원으로 전환하고 세션 교체 |
| POST | `/api/auth/login` | 없음 | 전화번호·비밀번호 인증 후 회원 세션 발급 |
| POST | `/api/auth/logout` | 비회원/회원 | 해당 세션 폐기, 쿠키 삭제 |

수정·삭제 시 다른 고객의 양식장 ID를 지정하면 404를 반환합니다. 만료·폐기 세션은 401, 입력 오류는 422, 중복 전화번호는 409를 반환합니다.

## 위험정보 화면의 지역 좌표 조회

실제 연결 DB `nifs_ocean`의 `public.sigungu_area_coordinates`를 읽습니다. 시군구는 `sigungu_name`, 읍·면·리 선택 항목은 DB의 `area_name`을 표시합니다. DB에 별도 리 단위 행이 없으면 임의로 추가하지 않습니다.

`client.fetch_coordinate_regions()`가 `/api/regions`의 공개 목록을 가져오고, 화면은 선택한 시군구의 행만 하위 목록에 표시합니다. 읍·면·리/지역 선택값은 이름이 아닌 `region_id`이며 `client.fetch_region_coordinates(region_id)`로 상세 API를 조회합니다. 다른 시군구에 같은 지역명이 있어도 ID로 구분합니다.

상세 응답은 `region_id`, `sigungu_name`, `area_name`, `latitude`, `longitude`, `coordinate_type`, `source_url`, `aquaculture_coordinate_verification`입니다. ID가 0 이하이거나 숫자가 아니면 422, 존재하지 않으면 404입니다. 조회에는 계정 인증이 필요하지 않습니다.

화면은 등록된 양식장의 지역을 기본으로 선택하고 좌표를 소수점 여섯 자리로 표시합니다. 해당 위치가 목록에 없거나 시군구를 변경하면 하위 지역 선택을 비웁니다. 선택이 없거나 조회가 실패하면 좌표를 표시하지 않습니다. 현재 DB의 좌표 유형이 ‘행정지명 대표점’이면 해당 유형도 함께 표시하므로, 이 값을 실제 양식장의 GPS 위치라고 해석하지 않습니다.

두 공개 조회 함수는 60초 캐시를 사용하고 상세 조회 캐시는 최대 256개입니다. 고객 토큰은 캐시에 넣지 않습니다. 위험정보 화면의 조회 선택은 양식장 저장 API를 호출하지 않습니다. 단독 HTML 체험 버전에는 실제 좌표 조회를 연결하지 않았습니다.

## 양식장 입력

```json
{
  "region_id": 1,
  "farming_method": "cage",
  "insurance_status": "uninsured",
  "species_ids": [1, 2]
}
```

ID는 예시입니다. 반드시 조회 API에 존재하는 값을 사용하세요. 중복 품종 ID와 존재하지 않는 지역·품종은 거절합니다. 시군구와 읍면동 이름은 지역 ID에 맞춰 서버가 저장합니다.

| 화면 값 | API 값 |
| --- | --- |
| 가두리 | `cage` |
| 육상 | `land_based` |
| 가입 | `insured` |
| 미가입 | `uninsured` |
| 잘 모름 | `unknown` |

PATCH에서는 변경할 항목만 보냅니다. 빈 요청과 명시적인 `null`은 허용하지 않습니다. 품종 목록을 전달하면 기존 연결 목록을 교체합니다. 기존 DB에서 지역이 미연결된 양식장은 수정 시 `region_id`도 지정해야 합니다.

## 회원가입·로그인 입력

```json
{
  "name": "홍길동",
  "birth_date": "1980-01-01",
  "phone_number": "010-1234-5678",
  "password": "example-password"
}
```

로그인에는 `phone_number`, `password`만 전달합니다. 전화번호는 DB 제약에 맞춰 `010`으로 시작하는 11자리로 정규화합니다. 비밀번호는 8~128자이고 서버에서 무작위 salt를 사용한 scrypt 해시로 저장합니다. 현재 API는 SMS 본인확인을 수행하지 않으며 `phone_verified_at`을 채우지 않습니다. 기존에 다른 알고리즘으로 생성한 해시는 자동 호환되지 않습니다.

기존 회원으로 로그인하면 해당 회원의 양식장이 조회됩니다. 직전에 생성한 비회원 양식장을 기존 회원 계정에 자동 병합하지 않습니다. 그 기능을 추가할 때는 비회원 토큰도 별도로 유지하고 명시적 동의를 받는 전환 흐름이 필요합니다.

## 세션·쿠키

기존 `guest_sessions`에는 고객 외래키, 토큰 해시, 만료·폐기 시각이 있고 비회원만 허용하는 제약은 없습니다. 이번 구현에서는 **비회원·회원 세션을 모두 이 테이블에 보관**합니다. 원문 토큰은 DB에 저장하지 않습니다. `g_`/`m_` 토큰 구분과 고객의 현재 회원 상태가 일치해야 접근할 수 있습니다. 팀에서 세션 조회 시 테이블 이름만으로 비회원이라고 판단하면 안 됩니다. 추후 테이블명을 일반적인 세션 이름으로 정리할 수 있습니다.

세션 발급 응답은 JSON 토큰과 `nifs_session` HttpOnly 쿠키를 함께 제공합니다. 쿠키 경로는 `/api`, SameSite는 `lax`입니다. 기본 만료는 비회원 30일, 회원 7일이며 활동 시 자동 연장하지 않습니다. 고객 데이터는 세션이 만료되더라도 삭제하지 않습니다.

Bearer 인증이 없는 POST/PATCH/DELETE 요청에는 **`X-CSRF-Protection: 1` 헤더**가 필요합니다. `/docs`의 기본 실행에서는 이 헤더를 직접 추가하거나 먼저 발급받은 토큰을 Authorize에 입력해야 합니다. 브라우저가 API를 직접 호출할 때는 `credentials: 'include'`와 이 헤더를 사용하세요. 허용된 프론트 출처는 `CORS_ORIGINS`에 JSON 배열로 설정합니다. HTTPS 서비스에서는 `SESSION_COOKIE_SECURE=true`로 설정하세요. 현재 SameSite 설정은 같은 사이트 배치를 전제로 합니다.

Streamlit 서버의 Python HTTP 요청에서 받은 쿠키는 사용자 브라우저에 자동 전달되지 않습니다. 현재 구현은 API 쿠키 발급·검증까지 제공하며, Streamlit의 브라우저 재접속 복원은 프론트 측 쿠키 연결 작업이 추가로 필요합니다. 단독 HTML을 `file://`로 열어 사용하는 방식도 쿠키 연동 대상으로 삼지 않습니다.

로그인 요청은 프로세스 내에서 IP별·전화번호별 5분에 10회로 제한합니다. 여러 worker나 서버를 운영할 때는 공용 저장소 기반 제한으로 바꿔야 합니다. 세션·개인정보 응답에는 `Cache-Control: no-store`를 사용합니다.

## 검사

기능별 계정 연동 검사와 공통 테스트 도구는 [tests/README.md](backend/tests/README.md)를 참고하세요. 프로젝트 최상위에서 `py backend/run_tests.py --db`로 현재 DB 접속 계정의 권한과 계정별 데이터 저장·조회까지 검사할 수 있습니다.

전복 품종 선택만 검사하려면 `py backend/run_tests.py --db --suite species`를 실행하세요. 테스트는 실제 테이블 정의를 복제한 임시 스키마에 저장한 뒤 롤백합니다.

```powershell
# 표준 라이브러리 기반 보안·입력 검사
py -m unittest discover -s backend/backend/tests -p test_customer_service.py -v

# DB 통합 검사: 실제 테이블 정의를 임시 스키마로 복제하고 전체 롤백
$env:RUN_CUSTOMER_DB_TESTS = '1'
py -m unittest discover -s backend/backend/tests -p test_customer_service.py -v
Remove-Item Env:RUN_CUSTOMER_DB_TESTS
```

통합 검사에는 스키마 생성 권한이 필요합니다. 임시 스키마의 생성·데이터 변경을 한 트랜잭션 안에서 수행하고 롤백하며, 실제 고객 테이블에는 쓰지 않습니다. 기존 해양 API의 pytest 테스트는 기존 테스트 DB 및 개발 의존성을 별도로 사용합니다.

구현 참고: [Python scrypt](https://docs.python.org/3/library/hashlib.html#hashlib.scrypt), [FastAPI 쿠키 응답](https://fastapi.tiangolo.com/advanced/response-cookies/).
