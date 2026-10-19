# 폐쇄망 설치 안내

인터넷이 되는 PC 에서 아래 파일을 받아 반입합니다. 반입 전에 해시를 기록해 두세요.

## 반입 목록

| 구성요소 | 필수 | 크기 | 비고 |
|---|---|---|---|
| Python 3.11 이상 설치 파일 | 예 | 약 30MB | 이미 있으면 생략 |
| Git | 예 | 약 60MB | 변경분 검사에 필요 |
| VS Code 와 `rulefirst-review-x.y.z.vsix` | 선택 | 약 100MB + 40KB | 편집기 통합을 쓸 때 |
| 이 저장소 소스 zip | 선택 | 1MB 미만 | 명령줄만 쓸 때 |
| llama.cpp Windows CPU 빌드 zip | 선택 | 약 50MB | 모델 층을 쓸 때 |
| 모델 GGUF 파일 | 선택 | 1~5GB | 모델 층을 쓸 때 |

## 해시 기록

```bat
certutil -hashfile rulefirst-review-0.1.0.vsix SHA256
certutil -hashfile qwen2.5-coder-1.5b-instruct-q4_k_m.gguf SHA256
```

공식 배포처가 해시를 공개하면 그 값과 대조합니다.

## 설치 순서

1. Python 과 Git 을 설치합니다. `python --version` 이 3.11 이상인지 확인합니다.
2. VS Code 에서 **Extensions: Install from VSIX...** 로 확장을 설치합니다.
3. Python 경로가 기본(`python`)과 다르면 설정 `rulefirst.pythonPath` 를 채웁니다.
4. 저장소를 열고 **RuleFirst: 변경분 리뷰** 를 실행해 규칙 층이 도는지 확인합니다.

## 모델 층 (선택)

```bat
llama-server.exe -m D:\models\qwen2.5-coder-1.5b-instruct-q4_k_m.gguf --host 127.0.0.1 --port 8080 -c 8192
```

- 설정 `rulefirst.llm.endpoint` 에 `http://127.0.0.1:8080/v1` 을 넣습니다.
- `--host` 는 반드시 `127.0.0.1` 로 둡니다. `0.0.0.0` 으로 열면 같은 망의 다른 PC 가 코드를 보낼 수 있습니다.
- 먼저 `llama-bench.exe -m <모델>` 로 속도를 재 두면 리뷰 소요시간을 예상할 수 있습니다.

## 운용 팁

- 모델 층은 CPU 를 거의 다 씁니다. 노트북은 전원을 연결하고, 큰 변경분은 점심시간이나 퇴근 후에 돌리세요.
- 리포트를 팀 폴더에 모으려면 설정 `rulefirst.reportDir` 를 지정합니다.
