# 백엔드 데이터 연동 테스트

고객 데이터의 `입력 → API → PostgreSQL 저장 → 계정별 조회`를 검사합니다. 현재 `.env`에 설정된 **DB 접속 계정**의 연결·권한을 확인하고, 앱 고객 계정은 임시 테스트 회원 두 명을 생성해 검사합니다. 실제 회원의 전화번호나 비밀번호를 입력할 필요가 없습니다.

## 실행

프로젝트 최상위 폴더에서:

```powershell
# DB 연결 없이 보안·입력 테스트. DB 검사는 skipped로 표시됩니다.
py backend/run_tests.py

# 현재 .env의 DB에 연결해 전체 고객 검사
py backend/run_tests.py --db

# 계정 데이터 연동 검사만
py backend/run_tests.py --db --suite accounts

# 전복 육상·해상 품종 저장 검사만
py backend/run_tests.py --db --suite species

# 시군구·읍면리별 좌표 조회 검사만
py backend/run_tests.py --db --suite regions

# 보안·입력 검사만
py backend/run_tests.py --suite security
```

`py` 별칭에 문제가 있으면:

```powershell
& "$env:LOCALAPPDATA\Python\pythoncore-3.14-64\python.exe" backend/run_tests.py --db
```

기본 실행은 환경에 남아 있는 `RUN_CUSTOMER_DB_TESTS` 값과 관계없이 DB 검사를 생략합니다. `--db`로 명시해서 실행합니다. 실패 시 종료 코드가 1이므로 이후 CI에서도 같은 명령을 사용할 수 있습니다. 이 실행기는 표준 라이브러리 `unittest`를 사용하며 서버를 미리 켤 필요가 없습니다.

## 폴더 구조

```text
backend/
├── run_tests.py                       # 고객 테스트 실행 진입점
└── backend/tests/
    ├── support.py                    # API 요청·임시 DB 공통 도구
    ├── test_customer_service.py      # 보안 검사·기존 전체 흐름 회귀 검사
    ├── integration/
    │   ├── __init__.py
    │   └── test_accounts.py          # 계정별 데이터 연동 검사
    ├── test_db.py                    # 기존 pytest 연결 설정 검사
    └── test_api.py                   # 기존 pytest 해양 API 검사
```

## 확인 항목

| 대상 | 검사 |
| --- | --- |
| 현재 DB 접속 계정 | 연결, 필요한 컬럼 접근, 고객 테이블 사용·쓰기 권한 |
| 비회원 등록 | 입력한 지역·양식 방식·보험 상태·복수 품종이 DB와 API 조회에서 일치 |
| 회원 전환 | 같은 고객·양식장 ID 유지, 회원 정보·비밀번호 해시 저장 |
| 재로그인 | 새 세션에서도 같은 회원의 기존 양식장 조회 |
| 계정 분리 | A/B 계정이 각자 데이터만 조회하고 상대 양식장 수정·삭제는 거절 |
| 수정 | 변경한 값이 DB와 다음 조회 응답에 반영 |
| 실패 처리 | 잘못된 품종 입력 시 기존 값 유지, 저장 중 예외 발생 시 전체 롤백 |
| 세션·보안 | 토큰 해시 저장, 비밀번호 검증, 만료·로그아웃 토큰 차단, CSRF 헤더 |
| 전복 품종 선택 | 육상·해상별 `species_id`, `farm_species` 연결, 구분 변경·재로그인 후 유지 |
| 전복 입력 오류 | 미구분 전복·양식 방식 불일치·다른 고객 양식장 변경 거절 |
| 품종 초기 데이터 | 반복 초기화 시 기존 품종 ID 유지 |
| PDF 품종 목록 | 확인된 15개 대상 품종의 API 표시·양식장 연결, 반복 입력 시 기존 ID 보존 |
| 오래된 등록 목록 | 전복만 있던 세션에서도 갱신된 목록이 표시되고 유효한 선택값은 유지 |
| 지역 좌표 | 시군구 필터, 지역 ID별 위도·경도, 서로 다른 시의 같은 지역명 구분, 잘못된 ID 처리 |

## DB 데이터 처리

- 실제 `customer_service` 테이블의 **정의**를 무작위 임시 스키마에 복제합니다. 실제 고객·양식장·세션 행은 복사하지 않습니다.
- 지역 기준 데이터 두 행만 복사하고 품종·고객 데이터는 테스트용으로 생성합니다.
- `C-...` 고객 ID의 원본 발급 시퀀스도 소비하지 않도록 테스트 스키마에 별도 ID 발급 시퀀스를 만듭니다.
- 테스트마다 새 스키마를 사용하고 요청마다 savepoint로 실패를 롤백합니다. 테스트가 실패해도 바깥 트랜잭션 전체를 롤백하고 임시 스키마가 사라졌는지 검사합니다.
- 스키마 생성 권한이 필요합니다. 원본 테이블의 실제 쓰기 권한은 `has_table_privilege`로 조회하며, 원본 고객 테이블에는 쓰지 않습니다.
- 이 검사는 PostgreSQL/API 연동 검사입니다. 원본 테이블의 트리거·RLS 정책, 실제 커밋 후 별도 DB 연결에서의 영구 보관, 브라우저 쿠키·화면 동작까지 검증하지는 않습니다.
- 테스트 프레임워크가 FastAPI 의존성을 교체하므로, 같은 프로세스에서 스레드 병렬 실행은 하지 않습니다. 별도 프로세스는 서로 다른 임시 스키마를 사용합니다.

## 새 데이터 연동 검사 추가

`integration/test_보험기능.py`처럼 기능별 파일을 추가하고 `unittest.TestCase`로 케이스를 나눕니다. 고객 데이터에는 `support.customer_sandbox()`와 `support.request()`를 재사용할 수 있습니다. `customer_sandbox()`는 고객 테이블용이므로 다른 스키마를 연결할 때는 해당 데이터용 fixture와 명시적인 SQL 경로 매핑을 별도로 추가해야 합니다.

새 파일의 테스트는 `@unittest.skipUnless(os.getenv('RUN_CUSTOMER_DB_TESTS') == '1', 'Enable DB checks')`로 DB 연결을 명시적으로 제한하세요. 실행기는 `integration/`의 `test_*.py` 파일을 자동 탐색합니다.

기존 `test_db.py`, `test_api.py`는 pytest용이며 이번 실행기에 포함하지 않습니다. 기존 해양 API 통합 테스트는 별도의 `_test` DB와 기존 SQL 파일이 필요합니다. 프론트 테스트는 프로젝트 최상위의 `tests/test_guest_flow.py`에서 유지합니다.

## 전복 버튼부터 DB까지 확인

백엔드 검사는 `integration/test_species_selection.py`, 화면·클라이언트 검사는 프로젝트 최상위 `tests/test_species_selection.py`에 있습니다. 저장값은 `farm_species`와 `species`를 JOIN해 품종 이름까지 비교합니다.

```powershell
$env:RUN_CUSTOMER_DB_TESTS = '1'
py -m unittest discover -s tests -v
Remove-Item Env:RUN_CUSTOMER_DB_TESTS
```

실제 Streamlit 입력 → 클라이언트 요청 본문 → ASGI API → 임시 PostgreSQL 테이블을 거칩니다. 해상 선택·등록 → 회원가입 → 로그아웃·재로그인 → 육상 변경 후, 같은 고객·양식장에 `전복(육상)` ID가 연결되는지 확인합니다. 서버를 별도로 켤 필요는 없습니다. `RUN_CUSTOMER_DB_TESTS`를 설정하지 않으면 DB 통합 검사는 생략하고 버튼 표시·선택 초기화·미선택 차단·API 실패 처리·품종 ID 매핑만 검사합니다.

## 위험정보 화면 좌표 검사

- `backend/backend/tests/integration/test_region_coordinates.py`: 시군구 필터, 지역 ID 상세 조회, 위도·경도 및 메타데이터 일치, 같은 지역명 구분, 404·422 응답.
- `tests/test_region_coordinates.py`: 등록 지역 기본 선택, 시군구 변경 시 이전 선택·좌표 초기화, 빈 목록·연결 오류, 오류 후 이전 좌표 숨김, 조회 중 양식장 정보 보존.
- `RUN_CUSTOMER_DB_TESTS=1`이면 화면 선택부터 ASGI API와 임시 PostgreSQL 좌표까지 비교합니다. 임시 스키마에는 서로 다른 시의 같은 이름을 가진 지역을 만들어 검사하고 모두 롤백합니다.

```powershell
py backend/run_tests.py --db --suite regions

$env:RUN_CUSTOMER_DB_TESTS = '1'
py -m unittest discover -s tests -p test_region_coordinates.py -v
Remove-Item Env:RUN_CUSTOMER_DB_TESTS
```

