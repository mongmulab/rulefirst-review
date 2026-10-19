# 규칙 작성법

규칙팩은 TOML 파일이고 `[[rule]]` 배열을 가집니다. 폴더를 팩으로 지정하면 그 안의 `*.toml` 을 모두 읽습니다.

## 공통 필드

| 필드 | 필수 | 설명 |
|---|---|---|
| `id` | 예 | 전체 팩에서 유일해야 합니다. 겹치면 로딩 오류입니다. |
| `kind` | 아니오 | `regex`(기본), `filename`, `test_counterpart`, `junit_no_assert`, `endpoint_coverage` |
| `perspective` | 예 | `security`, `ux`, `test`, `structure`, `e2e`, `performance` 또는 임의 이름 |
| `severity` | 예 | `critical`, `high`, `medium`, `low` |
| `title` | 예 | 리포트와 문제 패널에 보이는 한 줄 |
| `files` | 아니오 | 대상 글롭 목록. 비우면 모든 변경 파일 |
| `exclude_files` | 아니오 | 제외 글롭 목록 |
| `advice` | 아니오 | 조치 안내 한두 문장 |

글롭 규칙은 이렇습니다. `**/` 는 0개 이상의 폴더, `*` 는 한 경로 조각 안에서만 맞습니다. `/` 가 없는 패턴(`*.yml`)은 어느 깊이의 파일 이름에도 맞습니다.

## kind 별 필드

### regex

| 필드 | 설명 |
|---|---|
| `pattern` | Python 정규식. TOML 에서는 `'''...'''` 리터럴 문자열로 쓰면 이스케이프가 편합니다. |
| `flags` | `"i"` 면 대소문자 무시. 패턴 앞에 `(?i)` 를 써도 됩니다. |
| `multiline` | `true` 면 파일 전체에 적용합니다. 여러 줄에 걸친 구조(빈 catch 등)에 씁니다. |
| `scope` | `changed`(기본)는 바뀐 줄의 일치만, `file` 은 바뀐 파일의 모든 줄을 봅니다. |
| `mask_group` | 이 이름으로 시작하는 이름 그룹(`val`, `val2`...)의 값을 리포트에서 `****` 로 가립니다. |

```toml
[[rule]]
id = "MY-001"
perspective = "security"
severity = "high"
title = "운영 접속 주소가 코드에 박혀 있다"
files = ["*.java"]
exclude_files = ["**/test/**"]
pattern = '''"jdbc:[^"]*prod[^"]*"'''
advice = "설정 파일로 옮긴다."
```

### filename

바뀐 파일의 이름이 `must_match` 정규식에 맞지 않으면 지적합니다. 명명 규약에 씁니다.

### test_counterpart

바뀐 소스 파일에 `이름 + 접미사` 테스트 파일이 저장소 어디에도 없으면 지적합니다. 대상과 접미사는 `.rulefirst.toml` 의 `[test]` 에서 정합니다.

### junit_no_assert

`@Test` 메서드 본문에 assert, verify, expect, should, fail 류 호출이 없으면 지적합니다.

### endpoint_coverage

바뀐 줄의 `@GetMapping` 같은 요청 매핑 URL 이 E2E 하니스 파일 어디에도 문자열로 나오지 않으면 지적합니다. 클래스 수준 `@RequestMapping` 접두어를 합칩니다. 하니스 경로는 `[e2e] harness_globs` 에서 정합니다.

## 규칙 시험하기

```bash
python -m rulefirst list-rules --pack my-pack.toml
python -m rulefirst review --files path/to/sample.java --pack my-pack.toml
```

## 오탐 줄이기

1. 먼저 `files` 로 대상을 좁힙니다. 가장 효과가 큽니다.
2. 테스트 코드가 문제면 `exclude_files` 에 테스트 경로를 넣습니다.
3. 주석 줄이 문제면 패턴 앞에 `^(?!\s*(\*|//|/\*)).*?` 를 붙입니다.
4. 의도를 이름으로 드러내는 관례가 있으면 존중합니다. 기본 규칙은 `catch (Exception ignored) {}` 를 지적하지 않습니다.
5. 규칙을 고쳤으면 잡아야 할 예와 잡지 말아야 할 예를 `core/tests` 에 함께 넣습니다.
