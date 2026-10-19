"""모델 층: 파일 1개 × 관점 1개 × 체크리스트 몇 문항만 로컬 모델에 묻는다.

OpenAI 호환 /chat/completions 엔드포인트를 쓴다. llama.cpp 의 llama-server,
Ollama(/v1), LM Studio 등이 모두 이 형식을 제공한다.
"""
from __future__ import annotations

import json
import re
import tomllib
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from .config import gmatch
from .model import Finding
from .verify import quote_matches

LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}

SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "hit": {"type": "boolean"},
                    "line": {"type": "integer"},
                    "quote": {"type": "string"},
                    "why": {"type": "string"},
                },
                "required": ["id", "hit", "line", "quote", "why"],
            },
        }
    },
    "required": ["items"],
}


@dataclass
class Checklist:
    perspective: str
    files: list[str]
    system: str
    items: list[dict]
    exclude_files: list[str] = field(default_factory=list)

    def item(self, iid: str) -> dict | None:
        return next((i for i in self.items if i["id"] == iid), None)


@dataclass
class Stats:
    calls: int = 0
    accepted: int = 0
    rejected_quote: int = 0
    rejected_other: int = 0
    errors: int = 0
    error_samples: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def check_endpoint(endpoint: str, allow_remote: bool) -> None:
    host = (urlparse(endpoint).hostname or "").lower()
    if host not in LOCAL_HOSTS and not allow_remote:
        raise ValueError(
            f"모델 엔드포인트가 로컬이 아니다: {host or endpoint}. "
            "코드가 PC 밖으로 나가므로 기본으로 막는다. 의도했다면 --allow-remote 를 준다."
        )


def load_checklists(dirpath: Path, perspectives: list[str]) -> list[Checklist]:
    out = []
    for f in sorted(dirpath.glob("*.toml")):
        with open(f, "rb") as fh:
            d = tomllib.load(fh)
        if d.get("perspective") not in perspectives:
            continue
        out.append(Checklist(
            perspective=d["perspective"], files=d.get("files", []), system=d.get("system", ""),
            items=d.get("item", []), exclude_files=d.get("exclude_files", []),
        ))
    return out


def excerpt(lines: list[str], changed: set[int] | None, context: int, max_chars: int) -> str:
    """바뀐 줄 앞뒤 context 줄만 줄번호를 붙여 잘라 낸다. 새 파일은 앞부분부터."""
    n = len(lines)
    if changed is None:
        keep = list(range(1, n + 1))
    else:
        s: set[int] = set()
        for c in changed:
            s.update(range(max(1, c - context), min(n, c + context) + 1))
        keep = sorted(s)
    out, prev, size = [], 0, 0
    for ln in keep:
        if prev and ln != prev + 1:
            out.append("   ...")
        row = f"{ln:5d}| {lines[ln - 1]}"
        size += len(row) + 1
        if size > max_chars:
            out.append("   ... (길이 제한으로 생략)")
            break
        out.append(row)
        prev = ln
    return "\n".join(out)


def build_messages(cl: Checklist, rel: str, code: str) -> list[dict]:
    qs = "\n".join(f"{i['id']}: {i['question']}" for i in cl.items)
    system = (cl.system or "너는 코드 체크리스트 판정기다.") + (
        "\n규칙: 각 문항마다 해당 여부만 판정한다. 해당(hit=true)이면 line 에 줄 번호를, "
        "quote 에 그 줄의 코드를 글자 그대로 옮겨 적는다. 확실하지 않으면 hit=false 로 둔다. "
        "해당 없음이면 line=0, quote=\"\" 로 둔다. why 는 한 문장."
    )
    user = f"파일: {rel}\n\n[문항]\n{qs}\n\n[코드] (앞의 숫자는 줄 번호)\n{code}"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _post(endpoint: str, body: dict, timeout: int) -> dict:
    req = urllib.request.Request(
        endpoint.rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def parse_content(content: str) -> dict:
    content = content.strip()
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content)
    start = content.find("{")
    if start > 0:
        content = content[start:]
    return json.loads(content)


def ask(endpoint: str, model: str, messages: list[dict], timeout: int) -> dict:
    body = {
        "model": model,
        "messages": messages,
        "temperature": 0,
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "checklist", "strict": True, "schema": SCHEMA},
        },
    }
    resp = _post(endpoint, body, timeout)
    return parse_content(resp["choices"][0]["message"]["content"])


def run(ws, checklists: list[Checklist], cfg: dict, progress=None) -> tuple[list[Finding], Stats]:
    lcfg = cfg["llm"]
    stats = Stats()
    findings: list[Finding] = []
    jobs = [
        (rel, cl) for rel in ws.changes for cl in checklists
        if gmatch(rel, cl.files) and not gmatch(rel, cl.exclude_files)
    ]
    for idx, (rel, cl) in enumerate(jobs, 1):
        lines = ws.lines(rel)
        if not lines:
            continue
        if progress:
            progress(idx, len(jobs), rel, cl.perspective)
        code = excerpt(lines, ws.changes[rel], lcfg["context_lines"], lcfg["max_chars"])
        stats.calls += 1
        try:
            result = ask(lcfg["endpoint"], lcfg["model"], build_messages(cl, rel, code), lcfg["timeout"])
        except (urllib.error.URLError, TimeoutError, OSError, KeyError, ValueError, json.JSONDecodeError) as e:
            stats.errors += 1
            if len(stats.error_samples) < 5:
                stats.error_samples.append(f"{rel} [{cl.perspective}]: {e}")
            continue
        for it in result.get("items", []):
            if not isinstance(it, dict) or not it.get("hit"):
                continue
            spec = cl.item(str(it.get("id", "")))
            line = it.get("line")
            quote = it.get("quote") or ""
            if spec is None or not isinstance(line, int) or not (1 <= line <= len(lines)):
                stats.rejected_other += 1
                continue
            if not quote_matches(lines, line, quote):
                stats.rejected_quote += 1
                continue
            stats.accepted += 1
            findings.append(Finding(
                perspective=cl.perspective, severity=spec.get("severity", "medium"),
                rule_id=f"LLM-{spec['id']}", title=spec.get("title", spec["question"]),
                file=rel, line=line, snippet=quote.strip()[:160],
                advice=str(it.get("why", ""))[:300], source="llm",
            ))
    return findings, stats
