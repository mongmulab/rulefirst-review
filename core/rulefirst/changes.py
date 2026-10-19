"""검토 대상 수집: git 변경 파일과 바뀐 줄 번호."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")

# 값이 None 이면 "파일 전체가 대상"(새 파일, 직접 지정한 파일)이라는 뜻이다.
ChangeMap = dict[str, "set[int] | None"]


def git(repo: Path, *args: str) -> str:
    r = subprocess.run(
        ["git", "-c", "core.quotepath=false", *args],
        cwd=repo, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} 실패: {r.stderr.strip()}")
    return r.stdout


def repo_root(path: Path) -> Path:
    return Path(git(path, "rev-parse", "--show-toplevel").strip())


def list_files(repo: Path) -> list[str]:
    tracked = git(repo, "ls-files").splitlines()
    others = git(repo, "ls-files", "--others", "--exclude-standard").splitlines()
    return sorted({f for f in tracked + others if f})


def _has_rev(repo: Path, rev: str) -> bool:
    try:
        git(repo, "rev-parse", "--verify", "--quiet", rev + "^{commit}")
        return True
    except RuntimeError:
        return False


def parse_diff(diff: str) -> ChangeMap:
    out: ChangeMap = {}
    cur = None
    for line in diff.splitlines():
        if line.startswith("+++ "):
            p = line[4:].strip()
            cur = p[2:] if p.startswith("b/") else None
            if cur is not None:
                out.setdefault(cur, set())
        elif line.startswith("@@") and cur is not None:
            m = HUNK.match(line)
            if not m:
                continue
            start = int(m.group(1))
            count = int(m.group(2)) if m.group(2) is not None else 1
            out[cur].update(range(start, start + count))
    return out


def collect(repo: Path, base: str = "HEAD", files=None, all_files: bool = False) -> ChangeMap:
    if files:
        return {f.replace("\\", "/"): None for f in files}
    if all_files or (base == "HEAD" and not _has_rev(repo, "HEAD")):
        return {f: None for f in list_files(repo)}
    if not _has_rev(repo, base):
        raise RuntimeError(f"기준 리비전을 찾을 수 없다: {base}")
    changes = parse_diff(git(repo, "diff", "-U0", "--no-color", "--diff-filter=AMR", base))
    for f in git(repo, "ls-files", "--others", "--exclude-standard").splitlines():
        if f:
            changes[f] = None
    return changes


def read_text(path: Path) -> str:
    """UTF-8 을 먼저 보고, 실패하면 CP949(EUC-KR 계열)로 읽는다."""
    data = path.read_bytes()
    for enc in ("utf-8", "cp949"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def is_binary(path: Path) -> bool:
    try:
        with open(path, "rb") as f:
            return b"\0" in f.read(4096)
    except OSError:
        return True
