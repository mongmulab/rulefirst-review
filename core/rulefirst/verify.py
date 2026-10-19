"""인용 검증: 모델이 댄 근거가 원문에 실제로 있는지 확인한다.

소형 모델의 가장 흔한 실패는 그럴듯한 줄을 지어내는 것이다. 근거 문자열이
지목한 줄 주변(기본 ±3줄)에 없으면 그 지적은 버린다.
"""
from __future__ import annotations

import re

_WS = re.compile(r"\s+")
MIN_QUOTE = 4


def normalize(s: str) -> str:
    s = re.sub(r"^\s*\d+\|\s?", "", s)  # 모델이 줄번호 접두어까지 베껴 온 경우
    return _WS.sub(" ", s).strip()


def quote_matches(lines: list[str], line: int, quote: str, window: int = 3) -> bool:
    q = normalize(quote)
    if len(q) < MIN_QUOTE:
        return False
    lo = max(1, line - window)
    hi = min(len(lines), line + window)
    # 여러 줄에 걸친 인용도 받도록 창 전체를 이어 붙여 비교한다.
    region = normalize(" ".join(lines[lo - 1:hi]))
    return q in region
