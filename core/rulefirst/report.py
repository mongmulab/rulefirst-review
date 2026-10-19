"""리포트: 사람용 Markdown 과 도구용 JSON."""
from __future__ import annotations

import json
from collections import Counter

from . import __version__
from .model import PERSPECTIVES, SEVERITIES, SEVERITY_KO, Finding, at_least


def _order(findings: list[Finding]) -> list[str]:
    known = [p for p in PERSPECTIVES]
    extra = sorted({f.perspective for f in findings} - set(known))
    return known + extra


def to_json(meta: dict, findings: list[Finding], llm_stats: dict | None, fail_on: str) -> str:
    blocked = [f for f in findings if at_least(f.severity, fail_on)]
    return json.dumps({
        "tool": "rulefirst-review",
        "version": __version__,
        **meta,
        "fail_on": fail_on,
        "blocked": bool(blocked),
        "counts": dict(Counter(f.severity for f in findings)),
        "findings": [f.to_dict() for f in sorted(findings, key=Finding.sort_key)],
        "llm": llm_stats,
    }, ensure_ascii=False, indent=2)


def _row(f: Finding) -> str:
    src = f"규칙 {f.rule_id}" if f.source == "rule" else f"모델 {f.rule_id}"
    s = f"- [{SEVERITY_KO.get(f.severity, f.severity)}] `{f.file}:{f.line}` — {f.title}"
    if f.snippet:
        s += f"\n  - 근거: `{f.snippet.replace('`', "'")}`"
    if f.advice:
        s += f"\n  - 조치: {f.advice}"
    s += f"\n  - 출처: {src}"
    return s


def to_markdown(meta: dict, findings: list[Finding], llm_stats: dict | None, fail_on: str) -> str:
    fs = sorted(findings, key=Finding.sort_key)
    blocked = [f for f in fs if at_least(f.severity, fail_on)]
    out = [
        "# 로컬 1차 리뷰 리포트",
        "",
        "> **로컬 1차 리뷰 · 파일 간 추론 미수행.** 여러 파일을 엮어야 보이는 결함은 잡지 못한다.",
        "> 배포 판정은 사람 확인이나 상위 리뷰로 한다.",
        "",
        f"- 일시: {meta['started_at']}",
        f"- 저장소: `{meta['repo']}`",
        f"- 기준: `{meta['base']}` · 대상 파일 {meta['file_count']}개",
        f"- 규칙팩: {', '.join(meta['packs'])} (규칙 {meta['rule_count']}개)",
        f"- 모델 층: {meta['llm'] or '꺼짐'}",
        f"- 도구: rulefirst-review {__version__}",
        "",
        "## 종합 요약",
        "",
        "| 관점 | " + " | ".join(SEVERITY_KO[s] for s in SEVERITIES) + " |",
        "|---|" + "---|" * len(SEVERITIES),
    ]
    for p in _order(fs):
        c = Counter(f.severity for f in fs if f.perspective == p)
        out.append(f"| {PERSPECTIVES.get(p, p)} | " + " | ".join(str(c.get(s, 0)) for s in SEVERITIES) + " |")
    out.append("")
    if blocked:
        out += [f"## 배포 보류 사유 ({SEVERITY_KO[fail_on]} 이상 {len(blocked)}건)", ""]
        out += [_row(f) for f in blocked]
    else:
        out += [f"## 판정", "", f"{SEVERITY_KO[fail_on]} 이상 지적 없음. 규칙 층 기준으로는 막을 사유가 없다."]
    out.append("")
    for n, p in enumerate(_order(fs), 1):
        items = [f for f in fs if f.perspective == p]
        out += [f"## {n}. {PERSPECTIVES.get(p, p)}", ""]
        out += [_row(f) for f in items] if items else ["발견 없음."]
        out.append("")
    if llm_stats:
        out += [
            "## 모델 판정 통계", "",
            "| 호출 | 채택 | 인용 불일치로 폐기 | 형식 오류로 폐기 | 호출 실패 |",
            "|---|---|---|---|---|",
            f"| {llm_stats['calls']} | {llm_stats['accepted']} | {llm_stats['rejected_quote']} "
            f"| {llm_stats['rejected_other']} | {llm_stats['errors']} |",
            "",
        ]
        for e in llm_stats.get("error_samples", []):
            out.append(f"- 실패 예: {e}")
        out.append("")
    return "\n".join(out)
