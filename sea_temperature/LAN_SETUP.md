# 내부망 공용 PostgreSQL

같은 공유기/내부망에 있는 팀원들이 서버 PC 한 대의 DB에 접속합니다. 현재 서버는 `192.168.0.96:5432`, DB는 `nifs_ocean`, 내부망은 `192.168.0.0/24`입니다. 팀원은 PostgreSQL 서버를 설치하거나 DB를 별도로 만들 필요가 없습니다.

```text
팀원 PC 1 (DBeaver / IDE / FastAPI) ─┐
                                  ├─ PostgreSQL 192.168.0.96:5432/nifs_ocean
팀원 PC 2 (DBeaver / IDE / FastAPI) ─┘       서버 PC
```

## 서버 PC

기존 `backend/.env`의 `DB_HOST=localhost`와 관리자 계정을 유지합니다. 아래 명령은 프로젝트 최상위 폴더에서 실행합니다.

```powershell
# 설정 파일 경로와 수신 주소 확인 (비밀번호는 출력하지 않음)
.\.venv\Scripts\python.exe -m backend.manage server-info

# 팀원 계정 생성: 12자 이상 비밀번호를 화면 표시 없이 두 번 입력
.\.venv\Scripts\python.exe -m backend.manage create-user nifs_team1
.\.venv\Scripts\python.exe -m backend.manage create-user nifs_team2
```

기본 권한은 조회입니다. 데이터 추가·수정·삭제 담당자는 **계정을 처음 만들 때** `--write-data`를 붙입니다. 기존 계정은 덮어쓰지 않습니다. DB/테이블 생성·삭제 권한은 부여하지 않으며, 스키마 변경과 `init-db`는 서버 관리자가 수행합니다. 새 테이블의 자동 권한은 계정을 만든 관리자 역할이 생성하는 테이블에 적용됩니다. 다른 소유자가 만든 테이블은 별도 권한 설정이 필요합니다.

현재 서버는 `listen_addresses=*`이므로 수신 주소 변경과 PostgreSQL 재시작이 필요 없습니다. 다른 서버가 `localhost`만 수신한다면 `server-info`에 나온 `postgresql.conf`에서 `listen_addresses = 'localhost,서버내부IP'`로 변경하고 PostgreSQL 서비스를 재시작하세요. [PostgreSQL 접속 설정](https://www.postgresql.org/docs/18/runtime-config-connection.html)

**관리자 권한 PowerShell**을 열고 프로젝트 폴더로 이동해 실행합니다.

```powershell
# 미리 보기: 실제 변경 없음
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/enable-lan.ps1 -ServerAddress 192.168.0.96 -AllowedSubnet 192.168.0.0/24 -WhatIf

# 실제 적용
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/enable-lan.ps1 -ServerAddress 192.168.0.96 -AllowedSubnet 192.168.0.0/24
```

스크립트는 기존 `pg_hba.conf`를 같은 위치에 백업하고 다음 규칙을 추가합니다. Windows에서는 새 연결부터 적용됩니다. [PostgreSQL HBA 문서](https://www.postgresql.org/docs/18/auth-pg-hba-conf.html)

```text
host nifs_ocean nifs_team1,nifs_team2 192.168.0.0/24 scram-sha-256
```

방화벽 규칙 `NIFS-PostgreSQL-LAN`은 개인/도메인 네트워크에서 내부망 `192.168.0.0/24`가 서버 `192.168.0.96`의 TCP 5432로 접속하도록 허용합니다. 신뢰하는 팀 공유기인데 Windows 네트워크 프로필이 공용이라면 설정에서 개인으로 변경하세요. 기존 다른 HBA/방화벽 규칙을 없애지는 않으므로 이미 더 넓은 허용 규칙이 있으면 별도로 검토해야 합니다.

## 팀원 PC

DBeaver의 새 PostgreSQL 연결 또는 IDE의 DB 연결 기능에 아래 값을 입력합니다. 관리자 `postgres` 비밀번호 대신 본인 팀원 계정을 사용합니다.

| 항목 | 값 |
| --- | --- |
| 호스트 | `192.168.0.96` |
| 포트 | `5432` |
| DB | `nifs_ocean` |
| 사용자 | `nifs_team1` 또는 `nifs_team2` |
| 비밀번호 | 서버에서 계정 생성 시 정한 비밀번호 |

팀원 PC에서 FastAPI도 실행하려면 README의 Python 환경·패키지 설치 후 `backend/team.env.example`을 `backend/.env`로 복사하고 계정과 비밀번호를 입력합니다. 기존 `.env`는 덮어쓰지 말고 편집합니다.

```powershell
if (-not (Test-Path backend/.env)) { Copy-Item backend/team.env.example backend/.env }
.\.venv\Scripts\python.exe -m backend.manage check-db
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

FastAPI는 팀원 PC에서 실행되지만 데이터는 공용 DB에서 조회됩니다. DB 직접 연결에는 서버 PC의 FastAPI 실행이나 8000 포트 개방이 필요 없습니다. 팀원은 `init-db` 또는 백업 복원을 실행하지 않습니다.

## 접속 확인과 운영

팀원 PC에서 아래 명령의 `TcpTestSucceeded=True`를 확인하고 DBeaver의 Test Connection 또는 `check-db`를 실행하세요.

```powershell
Test-NetConnection 192.168.0.96 -Port 5432
```

- 포트 연결 실패: 서버 전원/절전, IP, 방화벽, 네트워크 프로필, 게스트 Wi-Fi의 기기 간 격리를 확인합니다.
- `no pg_hba.conf entry`: 팀원 IP 대역과 계정명이 허용 규칙에 맞는지 확인합니다.
- `password authentication failed`: 해당 팀원 계정의 비밀번호를 확인합니다.
- `permission denied`: 조회 계정으로 쓰기/구조 변경을 시도하는지 확인합니다.

서버 PC는 켜져 있어야 합니다. 공유기에서 서버 IP를 DHCP 예약하면 주소 변경을 줄일 수 있습니다. IP가 바뀌면 팀원 `.env`와 HBA/방화벽도 갱신합니다. 다른 설정의 기존 `NIFS-PostgreSQL-LAN` 방화벽 규칙은 자동 덮어쓰지 않으므로 검토 후 수정/삭제하세요.

이 구성은 신뢰하는 내부망용입니다. `DB_SSLMODE=prefer`는 TLS 암호화를 보장하지 않습니다. 공유기의 인터넷 포트 포워딩은 설정하지 않습니다.

되돌리려면 HBA의 `BEGIN NIFS TEAM LAN`~`END NIFS TEAM LAN` 블록을 제거하고 관리자 PowerShell에서 `Remove-NetFirewallRule -Name NIFS-PostgreSQL-LAN`을 실행합니다. 백업 이후 다른 HBA 변경이 없다면 스크립트가 출력한 백업 파일로 복원해도 됩니다.
