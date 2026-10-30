# 파일 담당자

AI(언어 모델)와 팀원이 코드를 고치기 전에 담당자를 확인하는 표입니다. 규칙은 `.github/instructions/team-ownership.instructions.md`에 있습니다.

- 담당자가 아닌 파일은 AI가 수정·삭제하지 않습니다. 꼭 필요하면 변경안을 보여 주고 사용자의 승인을 받습니다.
- **공동** 파일은 줄 단위로 작성자를 확인하고(`git blame`), 추가만 합니다.
- 이 표는 2026-10-22 기준 `git log` 작성자로 만든 **초안**입니다. 팀 회의에서 확인한 뒤 "확인" 칸에 ✅를 적어 주세요. 담당이 바뀌면 이 표부터 고칩니다.

## 팀원과 git 이름

| 팀원 | GitHub | git user.name | 확인 |
|---|---|---|---|
| | sooui9 (팀 저장소) | sooui9 | |
| | Dicaffeinonemore | Dicaffeinonemore | |
| | seungwonyyii-ai | seungwonyyii-ai | |
| | 확인 필요 | LSH | |

## 화면 (HTML)

| 파일 | 담당 | 비고 | 확인 |
|---|---|---|---|
| `app.html` | **공동** (sooui9 · LSH · Dicaffeinonemore) | 시작·양식장 등록·로그인·회원가입 | |
| `home.html` | sooui9 | 홈(오늘의 수온), n8n 예측 연결 예정 | |
| `home_test.html`, `home_test.py` | seungwonyyii-ai | 홈 화면 v2 (하단 바 디자인 기준) | |
| `insurance.html`, `insurance_test.py` | sooui9 | 보험 정보·지원제도 | |
| `response.html` | sooui9 | 대응 요령 | |
| `loading.html` | sooui9 | 로딩·오류 화면 | |
| `common.css`, `common.js` | **공동** · 관리 sooui9 | 모든 화면의 하단 바. 관리자를 거쳐 수정 | |
| `start_bg.jpg`, `start_screen.py` | sooui9 | | |

## 백엔드 (`backend/`)

| 파일 | 담당 | 확인 |
|---|---|---|
| `backend/api.py`, `routes.py`, `schemas.py`, `team.py`, `team.env.example`, `manage.py`, `requirements*.txt` | LSH | |
| `backend/customer_api.py`, `customer_schemas.py`, `customer_security.py`, `species_catalog.py` | Dicaffeinonemore | |
| `backend/insurance.py`, `support.py` | sooui9 | |
| `backend/main.py`, `config.py`, `db.py`, `.env.example` | **공동** | |
| `backend/tests/test_api.py`, `test_db.py` | LSH | |
| `backend/tests/` 나머지, `run_tests.py`, `CUSTOMER_API.md` | Dicaffeinonemore | |
| `database/*.sql` | Dicaffeinonemore | |
| `LAN_SETUP.md` | LSH | |

## 테스트 (최상위 `tests/`)

| 파일 | 담당 | 확인 |
|---|---|---|
| `test_guest_flow.py` | **공동** (LSH · Dicaffeinonemore) | |
| `test_region_coordinates.py`, `test_species_selection.py` | Dicaffeinonemore | |

## 저장소 공통

| 파일 | 담당 | 확인 |
|---|---|---|
| `README.md`, `.gitignore` | **공동** | |
