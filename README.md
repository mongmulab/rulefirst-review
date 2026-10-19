# RuleFirst Review

**규칙으로 먼저, 모델은 나중에.** 폐쇄망과 GPU 없는 노트북에서 돌아가는 오프라인 코드 리뷰 도구입니다.

변경된 코드를 보안 · 사용자(UX) · 테스트 · 구조 · E2E 다섯 관점으로 검토하고, 사람이 읽는 Markdown 리포트와 VS Code "문제" 패널 표시를 만듭니다. 코드는 PC 밖으로 나가지 않습니다.

```
변경 파일 (git diff)
   │
   ▼
① 규칙 층      정규식·구조 규칙 27개. 결정적이고 빠르다 (수 초~수십 초)
   │
   ▼
② 모델 층      (선택) 로컬 소형 LLM 에 파일 1개 × 관점 1개 × 체크리스트만 묻는다
   │
   ▼
③ 인용 검증    모델이 댄 근거 문장이 그 줄에 실제로 있는지 확인. 없으면 버린다
   │
   ▼
④ 리포트       Markdown + JSON · VS Code 문제 패널 · 종료 코드(0 통과 / 1 보류 / 2 오류)
```

## 왜 만들었나

클라우드 AI 리뷰는 강력하지만 폐쇄망에서는 쓸 수 없고, 로컬 대형 모델은 GPU 가 필요합니다. 그런데 배포를 막아야 하는 지적의 상당수는 모델 없이도 잡힙니다. 설정 파일에 박힌 비밀번호, 잘 알려진 기본값, MyBatis `${}` 치환, 짝 없는 테스트가 그렇습니다.

그래서 이 도구는 규칙을 본체로 두고, 소형 모델은 좁은 체크리스트 판정만 맡깁니다. 소형 모델이 가장 자주 틀리는 방식인 "그럴듯한 근거 지어내기"는 인용 검증으로 기계적으로 걸러 냅니다.

## 특징

- **의존성 없음.** 엔진은 Python 3.11+ 표준 라이브러리만 씁니다. 폐쇄망에서 `pip install` 이 필요 없습니다.
- **변경된 줄만 봅니다.** 기존 코드의 부채가 아니라 이번 변경이 만든 문제를 먼저 보여 줍니다. 전체 검사도 됩니다.
- **비밀값은 리포트에서 가립니다.** 규칙이 잡은 비밀번호는 `****` 로 바뀌어 기록됩니다.
- **한국어 환경을 고려했습니다.** 규칙·체크리스트·리포트가 한국어이고, CP949(EUC-KR) 소스도 읽습니다.
- **모델은 로컬 주소만 허용합니다.** 원격 엔드포인트는 `--allow-remote` 를 명시해야 열립니다.
- **어떤 로컬 모델이든 붙습니다.** llama.cpp `llama-server`, Ollama, LM Studio 등 OpenAI 호환 주소면 됩니다.

## 빠른 시작

### 명령줄

```bash
git clone https://github.com/mongmulab/rulefirst-review
# Windows (cmd):   set PYTHONPATH=C:\path\to\rulefirst-review\core
# macOS/Linux:     export PYTHONPATH=/path/to/rulefirst-review/core

cd <검토할 저장소>
python -m rulefirst review                      # 커밋 전 변경분
python -m rulefirst review --base origin/main   # 브랜치 전체 변경분
python -m rulefirst review --files src/A.java   # 지정 파일 전체
python -m rulefirst review --all --quiet --md-out review.md   # 저장소 전체
python -m rulefirst list-rules                  # 불러온 규칙 보기
```

종료 코드는 `0` 통과, `1` 보류(`fail_on` 등급 이상 지적 있음), `2` 실행 오류입니다. CI 나 git hook 에 그대로 쓸 수 있습니다.

### VS Code

1. [Releases](https://github.com/mongmulab/rulefirst-review/releases) 에서 `.vsix` 를 받습니다.
2. 명령 팔레트에서 **Extensions: Install from VSIX...** 로 설치합니다. 엔진과 규칙이 들어 있습니다.
3. 명령 팔레트에서 **RuleFirst: 변경분 리뷰** 를 실행합니다. 편집기·탐색기 우클릭으로 **이 파일 리뷰** 도 됩니다.

결과는 문제 패널과 상태 표시줄에 나오고, **RuleFirst: 마지막 리포트 열기** 로 Markdown 리포트를 봅니다.

## 로컬 모델 연결 (선택)

모델 없이도 규칙 층만으로 동작합니다. 모델 층을 켜려면 OpenAI 호환 로컬 서버를 띄우고 주소를 줍니다.

```bash
# llama.cpp
llama-server -m qwen2.5-coder-1.5b-instruct-q4_k_m.gguf --host 127.0.0.1 --port 8080 -c 8192
python -m rulefirst review --llm-endpoint http://127.0.0.1:8080/v1

# Ollama
ollama pull qwen2.5-coder:1.5b
python -m rulefirst review --llm-endpoint http://127.0.0.1:11434/v1 --llm-model qwen2.5-coder:1.5b
```

VS Code 에서는 설정 `rulefirst.llm.endpoint` 와 `rulefirst.llm.model` 을 채웁니다. 응답 형식은 JSON 스키마로 강제하므로, `response_format` 의 `json_schema` 를 지원하는 서버판을 쓰세요.

### 권장 모델

| 구성 | 모델 예 | 라이선스 | 용도 |
|---|---|---|---|
| 보조 1.5B Q4 | Qwen2.5-Coder-1.5B-Instruct | Apache-2.0 | 빠른 예·아니오 판정 |
| 주력 4B Q4 | Qwen3-4B-Instruct, Phi-4-mini | Apache-2.0, MIT | 보안·UX·테스트 체크리스트 |
| 확장 7B Q4 | Qwen2.5-Coder-7B-Instruct | Apache-2.0 | 야간 배치, 재판정 |

모델 파일은 이 저장소에 포함하지 않습니다. 쓰기 전에 각 모델 카드의 라이선스를 확인하세요. 같은 계열이라도 크기에 따라 라이선스가 다를 수 있습니다.

### 자원 (CPU 전용 노트북 기준)

| 항목 | 값 | 비고 |
|---|---|---|
| 규칙 층, spring-petclinic 전체 (132개 파일) | 약 6초 | Ryzen 5 5500U 실측 (2026-10-19) |
| 규칙 층, macrozheng/mall 전체 (717개 파일) | 약 25초 | 같은 PC 실측 (2026-10-19) |
| 4B Q4 실행 메모리 | 약 3.5~4GB | 추정 |
| 4B Q4 모델 호출 1회 | 약 1분 | 추정, 입력 약 2,500토큰 |
| 10개 파일 변경분, 모델 층 포함 | 약 15~20분 | 추정 |

모델 쪽 수치는 추정입니다. `llama-bench` 로 자기 PC 에서 재 보길 권합니다. 측정값 기여를 환영합니다.

## 설정

검토할 저장소 루트에 `.rulefirst.toml` 을 두면 기본값을 덮어씁니다. 전체 예시는 [docs/rulefirst.example.toml](docs/rulefirst.example.toml) 에 있습니다.

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

## 기본 규칙

| 팩 | 규칙 | 예 |
|---|---|---|
| 보안 | 13 | 설정 파일 평문 비밀번호, 기본값 비밀번호, 개인키, URL 속 자격증명, MyBatis `${}`, SQL 이어 붙이기, 이스케이프 없는 출력, CSRF 끄기, 약한 암호, TLS 검증 끄기, 로그 속 민감정보 |
| 사용자(UX) | 5 | 빈 catch, `innerHTML +=` 누적 렌더, alert, console.log, printStackTrace |
| 테스트 | 5 | 짝 없는 클래스, 단언 없는 테스트, 테스트 끄기, `.only`, 고정 sleep |
| 구조·성능·E2E | 4 | 새 TODO, 다중 컬럼 IN 서브쿼리, SELECT *, E2E 하니스에 없는 엔드포인트 |

규칙을 추가하는 방법은 [docs/writing-rules.md](docs/writing-rules.md) 에 있습니다.

## 한계

솔직하게 적습니다.

- **파일 여러 개를 엮어야 보이는 결함은 잡지 못합니다.** 예를 들어 설정값이 다른 파일의 조건문에 걸려 무시되는 버그가 그렇습니다. 리포트 머리에 항상 "파일 간 추론 미수행"을 표시합니다.
- **정규식 규칙이라 오탐이 있습니다.** 규칙마다 제외 경로와 예외 패턴을 두고, 오탐 사례를 테스트로 고정해 줄여 갑니다.
- **모델 층의 정확도는 아직 측정 전입니다.** 인용 검증이 지어낸 근거는 걸러 내지만, 모델이 놓친 문제는 걸러 낼 수 없습니다.
- 이 도구는 **1차 리뷰**입니다. 배포 판정을 사람이나 상위 리뷰에 맡기는 운영을 권합니다.

## 로드맵

- [ ] 과거 리뷰 결과로 재현율·정밀도를 재는 평가 도구
- [ ] gitleaks·PMD 결과 가져오기
- [ ] 설정 키와 사용처를 대조하는 교차 파일 규칙
- [ ] 전자정부프레임워크·JSP 규칙팩
- [ ] 코드 심볼 색인으로 관련 파일을 문맥에 붙이기

## 폴더 구성

```
core/        엔진 (Python, 표준 라이브러리만)
rules/       규칙팩 (TOML). core = 기본, examples = 복사해서 쓰는 예시
checklists/  모델 층 체크리스트 (TOML)
vscode/      VS Code 확장 (빌드 없는 JavaScript)
docs/        설계·설치·규칙 작성 문서
```

## 기여

[CONTRIBUTING.md](CONTRIBUTING.md) 를 봐 주세요. 규칙을 추가할 때는 잡아야 할 예와 잡지 말아야 할 예를 테스트로 함께 넣어 주세요.

## 라이선스

[MIT License](LICENSE). 언어 모델 가중치는 포함하지 않으며, 함께 쓰는 모델은 각 모델의 라이선스를 따릅니다.

---

### English summary

RuleFirst Review is an offline, CPU-friendly code reviewer. Deterministic rules run first. An optional small local LLM answers narrow per-file checklists through any OpenAI-compatible local server, such as llama.cpp or Ollama. Every model finding must quote the exact source line it points to, or it is discarded. Findings are grouped into five perspectives: security, UX, tests, structure and E2E. Output is a Markdown/JSON report plus VS Code diagnostics. The engine is pure Python 3.11+ standard library. Rules, checklists and reports are in Korean.
