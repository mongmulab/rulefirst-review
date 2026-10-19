"""설정 로딩. 대상 저장소 루트의 .rulefirst.toml 이 기본값을 덮어쓴다."""
from __future__ import annotations

import copy
import functools
import re
import tomllib
from pathlib import Path

DEFAULT: dict = {
    "packs": ["core"],
    "exclude": [
        "**/.git/**", "**/node_modules/**", "**/build/**", "**/target/**",
        "**/dist/**", "**/out/**", "**/.gradle/**", "**/*.min.js",
    ],
    "fail_on": "high",
    "test": {
        "source_globs": ["**/src/main/java/**/*.java"],
        "test_suffixes": ["Test", "Tests", "IT"],
        "ignore_globs": [
            "**/package-info.java", "**/*Application.java", "**/*Config.java",
            "**/*Configuration.java", "**/*Dto.java", "**/*DTO.java", "**/*Vo.java", "**/*VO.java",
        ],
    },
    "e2e": {
        "harness_globs": ["**/e2e/**", "**/*e2e*.py", "**/*.spec.ts", "**/*.spec.js", "**/*.cy.js"],
    },
    "llm": {
        "endpoint": "",           # 예: http://127.0.0.1:8080/v1  (비우면 모델 층을 끈다)
        "model": "",
        "perspectives": ["security", "ux", "test"],
        "context_lines": 30,
        "max_chars": 6000,
        "timeout": 300,
        "allow_remote": False,
    },
}


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load(repo: Path, explicit: Path | None = None) -> dict:
    path = explicit or (repo / ".rulefirst.toml")
    if path.is_file():
        with open(path, "rb") as f:
            return _merge(DEFAULT, tomllib.load(f))
    if explicit:
        raise FileNotFoundError(f"설정 파일이 없다: {explicit}")
    return copy.deepcopy(DEFAULT)


@functools.lru_cache(maxsize=1024)
def _glob_rx(pat: str) -> re.Pattern:
    """글롭을 정규식으로 바꾼다.

    '**/' 는 0개 이상의 폴더, 끝의 '/**' 는 그 아래 전부, '*' 는 한 경로 조각 안에서만 맞는다.
    '/' 가 없는 패턴('*.yml')은 어느 깊이의 파일 이름에도 맞는다.
    """
    pat = pat.replace("\\", "/").lstrip("/")
    if "/" not in pat:
        pat = "**/" + pat
    i, out = 0, []
    while i < len(pat):
        if pat.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pat.startswith("/**", i) and i + 3 == len(pat):
            out.append("(?:/.*)?")
            i += 3
        elif pat.startswith("**", i):
            out.append(".*")
            i += 2
        elif pat[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pat[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pat[i]))
            i += 1
    return re.compile("".join(out))


def gmatch(relpath: str, patterns) -> bool:
    """저장소 상대경로를 글롭 목록과 대조한다."""
    p = relpath.replace("\\", "/").lstrip("/")
    return any(_glob_rx(pat).fullmatch(p) for pat in patterns or [])
