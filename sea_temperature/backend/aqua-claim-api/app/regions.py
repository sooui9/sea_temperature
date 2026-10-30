"""시군 → 해수면 권역 매핑 (현재 7·8권역만).

7권역: 경남 사천·통영·하동·남해·고성
8권역: 부산, 경남 거제·창원
sigungu_area_coordinates.sigungu_name 은 '거제시', '고성군' 처럼 접미사가 붙어 있으므로 떼고 비교한다.
주의: '고성'은 강원 고성군과 이름이 같다. sigungu 테이블에 시도 컬럼이 없어 구분할 수 없으므로
현재 데이터 범위(경남)에서는 경남 고성으로 간주한다.
"""
from __future__ import annotations

REGION_7 = {"사천", "통영", "하동", "남해", "고성"}
REGION_8 = {"부산", "거제", "창원"}


def normalize_sigungu(name: str | None) -> str | None:
    if not name:
        return None
    n = name.strip().replace(" ", "")
    if n.startswith("부산"):
        return "부산"
    for suffix in ("광역시", "특별시", "시", "군", "구"):
        if n.endswith(suffix) and len(n) > len(suffix):
            return n[: -len(suffix)]
    return n


def sea_region_of(sigungu_name: str | None) -> int | None:
    n = normalize_sigungu(sigungu_name)
    if n in REGION_7:
        return 7
    if n in REGION_8:
        return 8
    return None
