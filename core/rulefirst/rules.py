"""규칙 층: 결정적 검사. 같은 입력에는 항상 같은 결과를 낸다.

규칙팩은 TOML 파일이고 [[rule]] 배열을 가진다. kind 별 필드는 docs/writing-rules.md 참고.
"""
from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .changes import ChangeMap, is_binary, read_text
from .config import gmatch
from .model import Finding

KINDS = {"regex", "filename", "test_counterpart", "junit_no_assert", "endpoint_coverage"}


@dataclass
class Rule:
    id: str
    kind: str
    perspective: str
    severity: str
    title: str
    files: list[str] = field(default_factory=list)
    exclude_files: list[str] = field(default_factory=list)
    pattern: str = ""
    flags: str = ""
    multiline: bool = False
    scope: str = "changed"      # changed | file
    mask_group: str = ""        # 이 이름의 그룹 값을 리포트에서 가린다
    must_match: str = ""        # filename 규칙: 파일명이 맞아야 하는 정규식
    advice: str = ""
    pack: str = ""

    def compiled(self) -> re.Pattern:
        fl = 0
        if "i" in self.flags:
            fl |= re.IGNORECASE
        if self.multiline:
            fl |= re.MULTILINE | re.DOTALL
        return re.compile(self.pattern, fl)


def _data_dirs() -> list[Path]:
    here = Path(__file__).resolve().parent
    # 저장소 배치(core/rulefirst)와 확장 번들 배치(engine/rulefirst) 둘 다 찾는다.
    return [here.parent, here.parent.parent, here / "data"]


def find_data_dir(name: str, override: Path | None = None) -> Path:
    if override:
        return override
    for d in _data_dirs():
        if (d / name).is_dir():
            return d / name
    raise FileNotFoundError(f"'{name}' 폴더를 찾을 수 없다. --rules-dir 로 지정하라.")


def load_packs(packs: list[str], rules_dir: Path) -> list[Rule]:
    rules: list[Rule] = []
    seen: set[str] = set()
    for pack in packs:
        # 규칙 폴더 안의 이름을 먼저 본다. 현재 폴더에 같은 이름이 있어도 헷갈리지 않게 한다.
        target = rules_dir / pack
        if not target.exists():
            target = Path(pack)
        files = sorted(target.glob("*.toml")) if target.is_dir() else [target]
        if not files or not all(f.is_file() for f in files):
            raise FileNotFoundError(f"규칙팩을 찾을 수 없다: {pack}")
        before = len(rules)
        for f in files:
            with open(f, "rb") as fh:
                data = tomllib.load(fh)
            for raw in data.get("rule", []):
                raw = dict(raw)
                raw.setdefault("kind", "regex")
                if raw["kind"] not in KINDS:
                    raise ValueError(f"{f.name}: 알 수 없는 kind '{raw['kind']}' ({raw.get('id')})")
                if raw["id"] in seen:
                    raise ValueError(f"{f.name}: 규칙 ID 중복 '{raw['id']}'")
                seen.add(raw["id"])
                rule = Rule(pack=f"{pack}/{f.name}", **raw)
                if rule.kind == "regex":
                    rule.compiled()  # 잘못된 정규식은 여기서 바로 드러나게 한다
                rules.append(rule)
        if len(rules) == before:
            raise ValueError(f"규칙팩에 규칙이 없다: {pack} ({target})")
    return rules


class Workspace:
    """파일 읽기를 캐시하고, 저장소 전체 파일 목록을 필요할 때만 만든다."""

    def __init__(self, repo: Path, changes: ChangeMap, all_files: list[str], exclude: list[str]):
        self.repo = repo
        self.changes = {f: v for f, v in changes.items() if not gmatch(f, exclude)}
        self.all_files = [f for f in all_files if not gmatch(f, exclude)]
        self._cache: dict[str, list[str] | None] = {}

    def lines(self, rel: str) -> list[str] | None:
        if rel not in self._cache:
            p = self.repo / rel
            if not p.is_file() or is_binary(p):
                self._cache[rel] = None
            else:
                self._cache[rel] = read_text(p).splitlines()
        return self._cache[rel]

    def is_changed_line(self, rel: str, line: int) -> bool:
        s = self.changes.get(rel)
        return s is None or line in s


def _mask(m: re.Match, group: str, text: str) -> str:
    """이름이 group 으로 시작하는 모든 그룹(val, val2, ...)의 값을 가린다."""
    if not group:
        return text
    for name in m.re.groupindex:
        if name.startswith(group) and m.group(name):
            text = text.replace(m.group(name), "****")
    return text


def _snippet(line: str) -> str:
    s = line.strip()
    return s if len(s) <= 160 else s[:157] + "..."


def _targets(ws: Workspace, rule: Rule):
    for rel in ws.changes:
        if rule.files and not gmatch(rel, rule.files):
            continue
        if rule.exclude_files and gmatch(rel, rule.exclude_files):
            continue
        yield rel


def run_regex(ws: Workspace, rule: Rule) -> list[Finding]:
    rx = rule.compiled()
    out = []
    for rel in _targets(ws, rule):
        lines = ws.lines(rel)
        if lines is None:
            continue
        if rule.multiline:
            text = "\n".join(lines)
            for m in rx.finditer(text):
                ln = text.count("\n", 0, m.start()) + 1
                if rule.scope == "changed" and not ws.is_changed_line(rel, ln):
                    continue
                out.append(_mk(rule, rel, ln, _mask(m, rule.mask_group, _snippet(lines[ln - 1]))))
            continue
        for i, line in enumerate(lines, 1):
            if rule.scope == "changed" and not ws.is_changed_line(rel, i):
                continue
            m = rx.search(line)
            if m:
                out.append(_mk(rule, rel, i, _mask(m, rule.mask_group, _snippet(line))))
    return out


def run_filename(ws: Workspace, rule: Rule) -> list[Finding]:
    rx = re.compile(rule.must_match)
    out = []
    for rel in _targets(ws, rule):
        name = rel.rsplit("/", 1)[-1]
        if not rx.search(name):
            out.append(_mk(rule, rel, 1, name))
    return out


def run_test_counterpart(ws: Workspace, rule: Rule, cfg: dict) -> list[Finding]:
    tcfg = cfg["test"]
    names = {f.rsplit("/", 1)[-1] for f in ws.all_files}
    out = []
    for rel in ws.changes:
        if not gmatch(rel, tcfg["source_globs"]) or gmatch(rel, tcfg["ignore_globs"]):
            continue
        name = rel.rsplit("/", 1)[-1]
        stem, _, ext = name.rpartition(".")
        if any(f"{stem}{suf}.{ext}" in names for suf in tcfg["test_suffixes"]):
            continue
        out.append(_mk(rule, rel, 1, f"{stem}{{{','.join(tcfg['test_suffixes'])}}}.{ext} 없음"))
    return out


_TEST_ANN = re.compile(r"@(?:Test|ParameterizedTest|RepeatedTest)\b")
_ASSERTISH = re.compile(
    r"\b(assert\w*|verify\w*|expect\w*|should\w*|fail)\s*\(|assertThat|\.andExpect\(|@Test\s*\(\s*expected",
)


def _method_body(lines: list[str], ann_idx: int) -> tuple[int, str]:
    """테스트 애너테이션 뒤 메서드의 (선언 줄 번호, 본문)을 돌려준다.

    '@Test void f() {' 처럼 한 줄에 붙은 경우와, 애너테이션이 여러 줄로 이어진 경우를 모두 다룬다.
    """
    rest = _TEST_ANN.split(lines[ann_idx], 1)[-1]
    rest = re.sub(r"^\s*\([^)]*\)", "", rest)  # @Test(timeout=..) 의 괄호는 빼고 본다
    j = ann_idx
    if not re.search(r"\w+\s*\(", rest):
        j = ann_idx + 1
        while j < len(lines) and lines[j].strip().startswith("@"):
            j += 1
    j = min(j, len(lines) - 1)
    decl = j + 1
    depth, started, buf = 0, False, []
    for k in range(j, min(len(lines), j + 400)):
        line = lines[k]
        for ch in line:
            if ch == "{":
                depth += 1
                started = True
            elif ch == "}" and started:
                depth -= 1
        if started:
            buf.append(line)
            if depth <= 0:
                break
    return decl, "\n".join(buf)


def run_junit_no_assert(ws: Workspace, rule: Rule) -> list[Finding]:
    out = []
    for rel in _targets(ws, rule):
        lines = ws.lines(rel)
        if lines is None:
            continue
        for i, line in enumerate(lines):
            if not _TEST_ANN.search(line):
                continue
            decl, body = _method_body(lines, i)
            end = decl + body.count("\n")
            if rule.scope == "changed" and not any(ws.is_changed_line(rel, n) for n in range(i + 1, end + 1)):
                continue
            if "@Test" in line and "expected" in line:
                continue
            if not _ASSERTISH.search(body):
                out.append(_mk(rule, rel, decl, _snippet(lines[decl - 1])))
    return out


_MAPPING = re.compile(
    r"@(Get|Post|Put|Delete|Patch|Request)Mapping\s*\(\s*(?:(?:value|path)\s*=\s*)?\{?\s*\"([^\"]*)\""
)
_CLASS_DECL = re.compile(r"\b(class|interface)\s+\w+")


def run_endpoint_coverage(ws: Workspace, rule: Rule, cfg: dict) -> list[Finding]:
    harness_files = [f for f in ws.all_files if gmatch(f, cfg["e2e"]["harness_globs"])]
    corpus_parts = []
    for f in harness_files[:2000]:
        ls = ws.lines(f)
        if ls:
            corpus_parts.append("\n".join(ls))
    corpus = "\n".join(corpus_parts)
    out = []
    for rel in _targets(ws, rule):
        lines = ws.lines(rel)
        if lines is None:
            continue
        prefix, seen_class = "", False
        for i, line in enumerate(lines, 1):
            m = _MAPPING.search(line)
            if not seen_class:
                if _CLASS_DECL.search(line):
                    seen_class = True
                elif m and m.group(1) == "Request":
                    prefix = m.group(2).rstrip("/")
                continue
            if not m or not ws.is_changed_line(rel, i):
                continue
            path = prefix + "/" + m.group(2).lstrip("/") if m.group(2) else prefix
            path = path or "/"
            if path not in corpus:
                hint = "E2E 하니스 없음" if not harness_files else "하니스에 등장하지 않음"
                out.append(_mk(rule, rel, i, f"{m.group(1).upper()} {path} · {hint}"))
    return out


def _mk(rule: Rule, rel: str, line: int, snippet: str) -> Finding:
    return Finding(
        perspective=rule.perspective, severity=rule.severity, rule_id=rule.id,
        title=rule.title, file=rel, line=line, snippet=snippet, advice=rule.advice, source="rule",
    )


def run_all(ws: Workspace, rules: list[Rule], cfg: dict) -> list[Finding]:
    findings: list[Finding] = []
    for r in rules:
        if r.kind == "regex":
            findings += run_regex(ws, r)
        elif r.kind == "filename":
            findings += run_filename(ws, r)
        elif r.kind == "test_counterpart":
            findings += run_test_counterpart(ws, r, cfg)
        elif r.kind == "junit_no_assert":
            findings += run_junit_no_assert(ws, r)
        elif r.kind == "endpoint_coverage":
            findings += run_endpoint_coverage(ws, r, cfg)
    return findings
