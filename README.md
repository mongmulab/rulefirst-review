# RuleFirst Review

규칙으로 먼저 확인하고 LLM 모델로 한 번 더 체크하는, 폐쇄망에서도 사용 가능한 오프라인 코드 리뷰 도구입니다.

AI 코드 리뷰는 편하지만 폐쇄망에서는 쓸 수가 없습니다.
그렇다고 로컬에 큰 모델을 올리자니 GPU가 없는 경우가 많습니다.
그래서 GPU 없이, 코드를 PC 밖으로 내보내지 않고 쓸 수 있는 리뷰 도구를 만들었습니다.

바뀐 코드를 보안 · 사용자(UX) · 테스트 · 구조 · E2E 다섯 가지 눈으로 살펴보고,
사람이 읽는 Markdown 리포트와 VS Code "문제" 패널 표시를 만들어 줍니다.

```
변경 파일 (git diff)
   │
   ▼
① 규칙 층      정규식·구조 규칙 27개. 같은 입력에는 늘 같은 결과, 수 초~수십 초
   │
   ▼
② 모델 층      (선택) 로컬 소형 LLM 에 파일 1개 × 관점 1개 × 체크리스트만 묻는다
   │
   ▼
③ 인용 검증    모델이 댄 근거 문장이 그 줄에 정말 있는지 대조. 없으면 버린다
   │
   ▼
④ 리포트       Markdown + JSON · VS Code 문제 패널 · 종료 코드(0 통과 / 1 보류 / 2 오류)
```

## 왜 규칙이 먼저인가

배포를 막아야 하는 지적 가운데 상당수는 모델 없이도 잡힙니다.
설정 파일에 그대로 적힌 비밀번호, 누구나 아는 기본값 비밀번호, MyBatis `${}` 치환, 짝이 되는 테스트가 없는 클래스 같은 것들입니다.

그래서 이 도구는 규칙을 본체로 두고, 작은 모델에게는 좁은 체크리스트 판정만 맡깁니다.
규칙은 같은 입력에 같은 결과를 내서 치명적인 항목을 믿고 막을 수 있기 때문입니다.

작은 모델이 가장 자주 틀리는 방식은 그럴듯한 근거를 지어내는 것입니다.
이건 인용 검증이 기계적으로 걸러 냅니다.
모델이 "이 줄에 이렇게 적혀 있다"고 댄 문장이 실제 소스에 없으면 그 지적은 버립니다.

## 이런 점을 신경 썼습니다

- **설치할 것이 없습니다.** 엔진은 Python 3.11 이상의 표준 라이브러리만 씁니다. 폐쇄망에서는 `pip install` 을 못 하는 경우가 많기 때문입니다.
- 바뀐 줄만 봅니다. 예전부터 쌓인 부채보다 이번 변경이 만든 문제를 먼저 보는 게 리뷰의 목적이기 때문입니다. 저장소 전체 검사도 할 수 있습니다.
- 비밀값은 리포트에서 가립니다. 규칙이 잡은 비밀번호는 리포트·JSON·문제 패널 어디에도 원문 대신 `****` 로 남습니다.
- 한국어로 읽힙니다. 규칙 설명과 리포트가 한국어이고, CP949(EUC-KR)로 저장된 옛 소스도 읽습니다.
- 모델은 내 PC 주소로만 연결됩니다. 원격 주소는 `--allow-remote` 를 붙여야 열립니다. 코드가 모르는 사이에 밖으로 나가면 안 되기 때문입니다.
- 로컬 모델은 무엇이든 붙습니다. llama.cpp `llama-server`, Ollama, LM Studio 처럼 OpenAI 호환 주소를 내주는 서버면 됩니다.

## 그러면 설치부터 보겠습니다

### 명령줄에서 쓰기

```bash
git clone https://github.com/mongmulab/rulefirst-review
# Windows (cmd):   set PYTHONPATH=C:\path\to\rulefirst-review\core
# macOS/Linux:     export PYTHONPATH=/path/to/rulefirst-review/core

cd <검토할 저장소>
python -m rulefirst review                      # 커밋 전 변경분
python -m rulefirst review --base origin/main   # 브랜치 전체 변경분
python -m rulefirst review --files src/A.java   # 지정한 파일 전체
python -m rulefirst review --all --quiet --md-out review.md   # 저장소 전체
python -m rulefirst list-rules                  # 불러온 규칙 보기
```

종료 코드는 `0` 통과, `1` 보류(`fail_on` 등급 이상의 지적이 있음), `2` 실행 오류입니다.
CI 나 git hook 에 그대로 걸어 두시면 됩니다. 보류가 나오면 커밋이나 배포를 멈추게 할 수 있기 때문입니다.

### VS Code 에서 쓰기

1. [Releases](https://github.com/mongmulab/rulefirst-review/releases) 에서 `.vsix` 파일을 받습니다.
2. 명령 팔레트에서 **[Extensions: Install from VSIX...]** 로 설치합니다. 엔진과 규칙이 같이 들어 있어서 따로 받을 것은 없습니다.
3. 명령 팔레트에서 **[RuleFirst: 변경분 리뷰]** 를 실행합니다. 편집기나 탐색기에서 오른쪽 클릭으로 **[이 파일 리뷰]** 도 할 수 있습니다.

결과는 문제 패널과 상태 표시줄에 나옵니다.
Markdown 리포트는 **[RuleFirst: 마지막 리포트 열기]** 로 보시면 됩니다.

## 로컬 모델 붙이기 (선택)

모델이 없어도 규칙 층만으로 동작합니다.
모델 층을 켜고 싶으시면 OpenAI 호환 로컬 서버를 띄우고 주소만 알려 주시면 됩니다.

```bash
# llama.cpp
llama-server -m qwen2.5-coder-1.5b-instruct-q4_k_m.gguf --host 127.0.0.1 --port 8080 -c 8192
python -m rulefirst review --llm-endpoint http://127.0.0.1:8080/v1

# Ollama
ollama pull qwen2.5-coder:1.5b
python -m rulefirst review --llm-endpoint http://127.0.0.1:11434/v1 --llm-model qwen2.5-coder:1.5b
```

VS Code 에서는 설정의 `rulefirst.llm.endpoint` 와 `rulefirst.llm.model` 을 채우시면 됩니다.
응답은 JSON 스키마로 받기 때문에, `response_format` 의 `json_schema` 를 지원하는 서버 버전을 쓰셔야 합니다.

### 어떤 모델을 쓰면 좋을까

| 구성 | 모델 예 | 라이선스 | 맡길 일 |
|---|---|---|---|
| 보조 1.5B Q4 | Qwen2.5-Coder-1.5B-Instruct | Apache-2.0 | 빠른 예·아니오 판정 |
| 주력 4B Q4 | Qwen3-4B-Instruct, Phi-4-mini | Apache-2.0, MIT | 보안·UX·테스트 체크리스트 |
| 확장 7B Q4 | Qwen2.5-Coder-7B-Instruct | Apache-2.0 | 밤에 돌리는 배치, 다시 판정하기 |

모델 파일은 이 저장소에 들어 있지 않습니다.
쓰시기 전에 모델 카드의 라이선스를 한 번 확인해 보세요. 같은 계열이라도 크기에 따라 라이선스가 다른 경우가 있기 때문입니다.

### 얼마나 걸리나 (GPU 없는 노트북 기준)

| 항목 | 값 | 비고 |
|---|---|---|
| 규칙 층, spring-petclinic 전체 (132개 파일) | 약 6초 | Ryzen 5 5500U 노트북에서 잰 값 (2026-10-19) |
| 규칙 층, macrozheng/mall 전체 (717개 파일) | 약 25초 | 같은 노트북에서 잰 값 (2026-10-19) |
| 4B Q4 실행 메모리 | 약 3.5~4GB | 추정 |
| 4B Q4 모델 호출 1회 | 약 1분 | 추정, 입력 약 2,500토큰 |
| 10개 파일 변경분, 모델 층 포함 | 약 15~20분 | 추정 |

모델 쪽 숫자는 아직 추정입니다.
`llama-bench` 로 쓰시는 PC 에서 직접 재 보시는 게 가장 정확합니다. 잰 값을 보내 주시면 표에 반영하겠습니다.

## 설정

검토할 저장소 맨 위 폴더에 `.rulefirst.toml` 을 두면 기본값 대신 그 값을 씁니다.
전체 예시는 [docs/rulefirst.example.toml](docs/rulefirst.example.toml) 에 있습니다.

```toml
packs = ["core", "examples/layered-spring.toml"]
fail_on = "high"
exclude = ["**/generated/**", "**/node_modules/**"]

[e2e]
harness_globs = ["**/e2e/**", "**/*.spec.ts"]

[llm]
endpoint = "http://127.0.0.1:8080/v1"
perspectives = ["security", "ux", "test"]
```

## 기본으로 들어 있는 규칙

| 팩 | 규칙 수 | 예 |
|---|---|---|
| 보안 | 13 | 설정 파일 평문 비밀번호, 기본값 비밀번호, 개인키, URL 속 자격증명, MyBatis `${}`, SQL 이어 붙이기, 이스케이프 없는 출력, CSRF 끄기, 약한 암호, TLS 검증 끄기, 로그 속 민감정보 |
| 사용자(UX) | 5 | 빈 catch, `innerHTML +=` 누적 렌더, alert, console.log, printStackTrace |
| 테스트 | 5 | 짝 없는 클래스, 단언 없는 테스트, 꺼 둔 테스트, `.only`, 고정 sleep |
| 구조·성능·E2E | 4 | 새로 생긴 TODO, 다중 컬럼 IN 서브쿼리, SELECT *, E2E 하네스에 없는 엔드포인트 |

규칙을 직접 추가하는 방법은 [docs/writing-rules.md](docs/writing-rules.md) 에 적어 두었습니다.

## 아직 못 하는 것

못 하는 것도 그대로 적어 둡니다. 모르고 쓰시면 놓친 걸 잡았다고 믿게 되기 때문입니다.

- **파일 여러 개를 엮어야 보이는 결함은 잡지 못합니다.** 설정값이 다른 파일의 조건문에 걸려 무시되는 버그 같은 경우입니다. 그래서 리포트 맨 위에 늘 "파일 간 추론 미수행"이라고 표시됩니다.
- 정규식 규칙이라 오탐이 있습니다. 규칙마다 제외 경로와 예외 패턴을 두고, 오탐 사례를 테스트로 남겨 가며 줄이고 있습니다.
- 모델 층의 정확도는 아직 재 보지 않았습니다. 인용 검증은 지어낸 근거를 걸러 내지만, 모델이 놓친 문제까지 찾아 주지는 못합니다.
- 이 도구는 1차 리뷰입니다. 배포 여부는 사람이나 그 위의 리뷰가 정하도록 운영하시는 게 맞습니다.

## 앞으로 할 일

- [ ] 지난 리뷰 결과로 재현율·정밀도를 재는 평가 도구
- [ ] gitleaks·PMD 결과 가져오기
- [ ] 설정 키와 그 값을 쓰는 곳을 맞대 보는 교차 파일 규칙
- [ ] 전자정부프레임워크·JSP 규칙팩
- [ ] 코드 심볼 색인으로 관련 파일을 같이 보여 주기

## 폴더 구성

```
core/        엔진 (Python, 표준 라이브러리만)
rules/       규칙팩 (TOML). core = 기본, examples = 복사해서 쓰는 예시
checklists/  모델 층 체크리스트 (TOML)
vscode/      VS Code 확장 (빌드 없는 JavaScript)
docs/        설계·설치·규칙 작성 문서
```

## 함께 만들기

[CONTRIBUTING.md](CONTRIBUTING.md) 를 먼저 봐 주세요.
규칙을 추가하실 때는 잡아야 할 예와 잡지 말아야 할 예를 테스트로 같이 넣어 주세요. 그래야 다음 사람이 규칙을 고쳐도 오탐이 되살아나지 않기 때문입니다.

## 라이선스

[MIT License](LICENSE).
언어 모델 가중치는 들어 있지 않고, 같이 쓰는 모델은 각 모델의 라이선스를 따릅니다.

---

### English summary

RuleFirst Review is an offline, CPU-friendly code reviewer. Deterministic rules run first. An optional small local LLM answers narrow per-file checklists through any OpenAI-compatible local server, such as llama.cpp or Ollama. Every model finding must quote the exact source line it points to, or it is discarded. Findings are grouped into five perspectives: security, UX, tests, structure and E2E. Output is a Markdown/JSON report plus VS Code diagnostics. The engine is pure Python 3.11+ standard library. Rules, checklists and reports are in Korean. MIT licensed.
