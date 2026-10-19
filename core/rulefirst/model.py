"""공통 자료형: 지적(Finding), 심각도, 관점."""
from __future__ import annotations

from dataclasses import asdict, dataclass

SEVERITIES = ["critical", "high", "medium", "low"]
SEVERITY_KO = {"critical": "치명", "high": "높음", "medium": "중간", "low": "낮음"}

# 표시 순서가 곧 리포트 장 순서다. 모르는 관점은 뒤에 붙는다.
PERSPECTIVES = {
    "security": "보안",
    "ux": "사용자(UX)",
    "test": "테스트",
    "structure": "구조 일관성",
    "e2e": "E2E 블랙박스",
    "performance": "성능",
}


def severity_rank(sev: str) -> int:
    """작을수록 심각하다. 모르는 값은 가장 가볍게 본다."""
    return SEVERITIES.index(sev) if sev in SEVERITIES else len(SEVERITIES)


def at_least(sev: str, threshold: str) -> bool:
    return severity_rank(sev) <= severity_rank(threshold)


@dataclass
class Finding:
    perspective: str
    severity: str
    rule_id: str
    title: str
    file: str
    line: int
    snippet: str = ""
    advice: str = ""
    source: str = "rule"  # rule | llm

    def to_dict(self) -> dict:
        return asdict(self)

    def sort_key(self):
        return (severity_rank(self.severity), self.file, self.line, self.rule_id)
