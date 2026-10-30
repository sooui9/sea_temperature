"""
우리 바다 안심도우미 - 정부지원(고수온 피해 지원) 조회 바로가기 (backend/backend/gov_support.py 를 부름)

Super DB는 쓰지 않습니다. backend/backend/data/damage/ 의 CSV 4개(해양수산부 복구 단가 고시 기준)만 읽습니다.
화면에서 쓰는 API(/api/v1/gov-support/damage)는 팀 백엔드(uvicorn backend.main:app)에 등록되어 함께 뜹니다.

실행 (sea_temperature 폴더에서)
  python gov_support_api.py --species 조피볼락 --species 감성돔

다른 파이썬 코드에서
    from gov_support_api import damage_support
    data = damage_support(["조피볼락", "감성돔"])   # DB 연결 필요 없음
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))   # backend 패키지를 불러오기 위해

from backend.gov_support import damage_support, main  # noqa: E402

__all__ = ["damage_support"]   # 다른 코드에서 여기서 바로 가져다 씀

if __name__ == "__main__":
    main()
