# RuleFirst Review — 오프라인 코드 리뷰

규칙으로 먼저 확인하고 LLM 모델로 한 번 더 체크하는, 폐쇄망에서도 사용 가능한 오프라인 코드 리뷰 확장입니다.

- **RuleFirst: 변경분 리뷰** — 커밋 전 변경분(또는 설정한 기준 리비전 이후)을 검토합니다.
- **RuleFirst: 이 파일 리뷰** — 편집기·탐색기 우클릭 메뉴에서 파일 하나를 통째로 검토합니다.
- 결과는 문제 패널, 상태 표시줄, Markdown 리포트로 나옵니다.

## 필요한 것

- Python 3.11 이상 (외부 패키지 불필요)
- Git
- 선택: llama.cpp `llama-server` 나 Ollama 같은 OpenAI 호환 로컬 모델 서버

## 설정

| 설정 | 기본값 | 설명 |
|---|---|---|
| `rulefirst.pythonPath` | `python` | Python 실행 파일 |
| `rulefirst.base` | `HEAD` | 비교 기준 리비전 |
| `rulefirst.failOn` | `high` | 이 등급 이상이면 "보류" 표시 |
| `rulefirst.reportDir` | 비움 | 리포트 저장 폴더 |
| `rulefirst.llm.endpoint` | 비움 | 예: `http://127.0.0.1:8080/v1`. 비우면 규칙 층만 |
| `rulefirst.llm.model` | 비움 | 모델 이름 |

코드는 PC 밖으로 나가지 않습니다. 모델 주소는 기본으로 로컬만 허용합니다.

자세한 내용은 저장소 README 를 보세요.
