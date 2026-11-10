# 감사원 AI 도입 AHP

감사 업무 AI를 A 직접 구축과 B 공공 SaaS 중 무엇으로 들일지, 요인 5개로 쌍대비교한 자료입니다.

## 설문

사람용 설문은 아래 주소에서 엽니다.

https://vysang9296.github.io/ahp/ahp_survey.html

같은 파일은 저장소의 [ahp_survey.html](ahp_survey.html)입니다. 구글 시트 전송 주소는 파일 안에 아직 비어 있습니다. 마지막 화면에서 제출하면 브라우저 콘솔에만 답이 남습니다. 시트 연동 코드는 [Code.gs](Code.gs)입니다.

## 파일

| 파일 | 내용 |
|---|---|
| `ahp_survey.html` | 사람용 설문. 요인 정의, B/C, 사실표가 들어 있습니다. |
| `Code.gs` | 응답을 구글 시트에 쌓는 Apps Script. |
| `personas_nemotron.jsonl` | Nemotron-Personas-Korea에서 뽑은 합성 응답자 8명. |
| `실행가이드.md` | 설문 절차와 집계 규칙. |
| `results/main-facts-2026-11-10/` | DeepSeek v4.1 Flash 40회 결과. |
| `results/main-facts-2026-11-10/집단_집계.csv` | 전체와 직무별 가중치, 종합 점수. |
| `results/main-facts-2026-11-10/페르소나별_결과.csv` | 사람 1명으로 묶은 결과. |
| `results/main-facts-2026-11-10/trials.csv` | 시행 40행. |
| `results/main-facts-2026-11-10/items.csv` | 문항 560행. |
| `results/요약.txt` | 같은 집계의 텍스트. 경로는 `results/main-facts-2026-11-10/요약.txt`. |

## 합성 응답 실행

모델은 OpenCode Go의 `opencode-go/deepseek-v4.1-flash`, 온도 0.7, 사실표 포함입니다. 페르소나 1명 × 회차 1번마다 세션을 새로 열었습니다. 8명 × 5회, 40세션입니다. 40회 모두 CR 0.1 미만이라 수정 질문은 없었습니다. 제외된 페르소나는 없습니다.

전체 종합 점수(PFA 기준)는 A 0.664, B 0.336입니다. 단순 비례는 A 0.641, B 0.359입니다.

P01 1회차는 같은 프롬프트의 시험 세션을 원장에 넣었습니다. 나머지 39회는 2026-11-10에 새로 실행했습니다. 실행 스크립트는 `run_opencode_batch.py`입니다.
