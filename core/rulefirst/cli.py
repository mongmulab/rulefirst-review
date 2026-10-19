"""명령줄 진입점.

    python -m rulefirst review [--repo .] [--base HEAD] [--md-out r.md] [--json-out r.json]
    python -m rulefirst list-rules

종료 코드: 0 = 통과, 1 = fail_on 이상 지적 있음, 2 = 실행 오류.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

from . import __version__, changes, config, llm, report, rules


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="rulefirst", description="규칙 우선 오프라인 코드 리뷰")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("review", help="변경분을 리뷰한다")
    r.add_argument("--repo", default=".", help="대상 git 저장소 (기본: 현재 폴더)")
    r.add_argument("--base", default="HEAD", help="비교 기준 리비전 (기본: HEAD = 커밋 전 변경분)")
    r.add_argument("--files", nargs="+", help="변경분 대신 이 파일들 전체를 검토")
    r.add_argument("--all", action="store_true", help="저장소 전체 파일을 검토")
    r.add_argument("--config", type=Path, help="설정 파일 (기본: <repo>/.rulefirst.toml)")
    r.add_argument("--rules-dir", type=Path, help="규칙팩 폴더")
    r.add_argument("--checklists-dir", type=Path, help="체크리스트 폴더")
    r.add_argument("--pack", action="append", help="규칙팩 (여러 번 지정 가능, 설정보다 우선)")
    r.add_argument("--fail-on", choices=["critical", "high", "medium", "low"])
    r.add_argument("--llm-endpoint", help="예: http://127.0.0.1:8080/v1 (주면 모델 층을 켠다)")
    r.add_argument("--llm-model", help="엔드포인트에 전달할 모델 이름")
    r.add_argument("--allow-remote", action="store_true", help="로컬이 아닌 모델 엔드포인트 허용")
    r.add_argument("--md-out", type=Path, help="Markdown 리포트 저장 경로")
    r.add_argument("--json-out", type=Path, help="JSON 리포트 저장 경로")
    r.add_argument("--quiet", action="store_true", help="표준출력에 리포트를 찍지 않는다")

    l = sub.add_parser("list-rules", help="불러올 규칙을 나열한다")
    l.add_argument("--repo", default=".")
    l.add_argument("--config", type=Path)
    l.add_argument("--rules-dir", type=Path)
    l.add_argument("--pack", action="append")
    return p


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def cmd_list(a) -> int:
    repo = Path(a.repo).resolve()
    cfg = config.load(repo, a.config)
    rs = rules.load_packs(a.pack or cfg["packs"], rules.find_data_dir("rules", a.rules_dir))
    for r in rs:
        print(f"{r.id:10} {r.severity:8} {r.perspective:11} {r.kind:18} {r.title}")
    return 0


def cmd_review(a) -> int:
    started = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    repo = changes.repo_root(Path(a.repo).resolve())
    cfg = config.load(repo, a.config)
    if a.fail_on:
        cfg["fail_on"] = a.fail_on
    if a.llm_endpoint:
        cfg["llm"]["endpoint"] = a.llm_endpoint
    if a.llm_model:
        cfg["llm"]["model"] = a.llm_model
    if a.allow_remote:
        cfg["llm"]["allow_remote"] = True
    packs = a.pack or cfg["packs"]

    rule_list = rules.load_packs(packs, rules.find_data_dir("rules", a.rules_dir))
    chg = changes.collect(repo, a.base, a.files, a.all)
    ws = rules.Workspace(repo, chg, changes.list_files(repo), cfg["exclude"])
    _log(f"[rulefirst] 대상 {len(ws.changes)}개 파일 · 규칙 {len(rule_list)}개")

    findings = rules.run_all(ws, rule_list, cfg)
    _log(f"[rulefirst] 규칙 층 지적 {len(findings)}건")

    stats = None
    llm_label = ""
    if cfg["llm"]["endpoint"]:
        llm.check_endpoint(cfg["llm"]["endpoint"], cfg["llm"]["allow_remote"])
        cls = llm.load_checklists(
            rules.find_data_dir("checklists", a.checklists_dir), cfg["llm"]["perspectives"])
        llm_label = f"{cfg['llm']['model'] or '(기본 모델)'} @ {cfg['llm']['endpoint']}"

        def prog(i, n, rel, p):
            _log(f"[rulefirst] 모델 {i}/{n} {p} {rel}")

        lf, st = llm.run(ws, cls, cfg, prog)
        findings += lf
        stats = st.to_dict()
        _log(f"[rulefirst] 모델 층 채택 {st.accepted} · 인용 불일치 폐기 {st.rejected_quote} · 실패 {st.errors}")

    meta = {
        "started_at": started, "repo": str(repo), "base": a.base if not (a.files or a.all) else "(지정 파일)",
        "file_count": len(ws.changes), "files": sorted(ws.changes), "packs": packs,
        "rule_count": len(rule_list), "llm": llm_label,
    }
    md = report.to_markdown(meta, findings, stats, cfg["fail_on"])
    if a.md_out:
        a.md_out.parent.mkdir(parents=True, exist_ok=True)
        a.md_out.write_text(md, encoding="utf-8")
    if a.json_out:
        a.json_out.parent.mkdir(parents=True, exist_ok=True)
        a.json_out.write_text(report.to_json(meta, findings, stats, cfg["fail_on"]), encoding="utf-8")
    if not a.quiet:
        print(md)
    from .model import at_least
    return 1 if any(at_least(f.severity, cfg["fail_on"]) for f in findings) else 0


def _safe_streams() -> None:
    """콘솔 인코딩(예: 한국어 Windows 의 cp949)은 유지하고, 표현 못 하는 글자만 대체한다.
    UTF-8 이 필요한 호출자(VS Code 확장 등)는 PYTHONIOENCODING=utf-8 을 준다."""
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass


def main(argv=None) -> int:
    _safe_streams()
    a = _parser().parse_args(argv)
    try:
        return cmd_review(a) if a.cmd == "review" else cmd_list(a)
    except (RuntimeError, ValueError, FileNotFoundError) as e:
        _log(f"[rulefirst] 오류: {e}")
        return 2
