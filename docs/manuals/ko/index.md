# MagLab 한국어 매뉴얼

[README로 돌아가기](../../../README.ko.md) · [English](../en/index.md)

이 매뉴얼은 MagLab을 실제 연구 작업에 쓰려는 자성/스핀트로닉스 연구자를
위해 작성되었습니다. 각 문서는 연구 병목에서 시작해서 바로 실행할 수 있는
명령으로 끝납니다.

## 기능별 가이드

| 영역 | 필요한 경우 |
|---|---|
| [문헌 인텔리전스](literature.md) | 논문 검색, 키워드 추출, evidence matrix 생성, 저자/저널/인용 그래프 확인이 필요할 때. |
| [물질과 물리](materials-physics.md) | 자성 물질 조회, 스택 구성, 물리 공식 계산, 단위 변환, plausibility check가 필요할 때. |
| [시뮬레이션](simulation.md) | micromagnetic, DFT, atomistic, multiscale simulation workflow를 준비할 때. |
| [분석과 피팅](analysis-fitting.md) | 데이터를 로드하고, 모델을 확인하고, 스핀트로닉스 효과를 피팅하고, consistency를 체크할 때. |
| [그림](figures.md) | `FigureSpec`, journal-aware figure, multi-panel export, schematic primitive가 필요할 때. |
| [계측기](instruments.md) | PyVISA driver, SCPI validation, manual RAG, measurement script, safety check가 필요할 때. |
| [연구노트와 계획](lab-planning.md) | ELN 기록, note 조회, measurement plan, DOE, active-learning 제안이 필요할 때. |
| [리뷰와 이상 현상 설명](review-explain.md) | manuscript review panel이나 anomalous result mechanism 후보가 필요할 때. |
| [논문 작성과 커뮤니케이션](authoring-comms.md) | 논문, revision letter, cover letter, email, abstract, grant, slide, poster 초안이 필요할 때. |
| [오케스트레이션, agent, MCP, gateway](orchestration.md) | REPL, one-shot prompt, Ralph loop, subagent, skill, MCP, gateway bot, cost/config tooling을 쓸 때. |

## 추천 읽기 순서

1. [물질과 물리](materials-physics.md)에서 deterministic core를 먼저 확인합니다.
2. 지금 당장 필요한 연구 작업에 해당하는 문서를 읽습니다.
3. 여러 도구를 묶고 싶을 때 [오케스트레이션](orchestration.md)을 읽습니다.
4. 검증된 결과가 준비된 뒤 [논문 작성과 커뮤니케이션](authoring-comms.md)을 사용합니다.

## 설치 요약

```sh
uv venv --python 3.12
source .venv/bin/activate
uv pip install -e .
uv pip install -e ".[research]"
maglab setup all
```

실제 연구 장비에서는 전체 research bundle인 `.[research]`를 권장합니다.
`maglab setup all`은 이미 준비된 기능, 추가 터미널 설정이 필요한 기능, 대응되는
REPL slash command를 한 번에 보여줍니다. 개별 기능은 `maglab setup <feature>`나
`/setup-<feature>`로 점검할 수 있습니다. OOMMF, MuMax3, magnum.np, VAMPIRE,
VASP, Quantum ESPRESSO 같은 solver는 MagLab 외부에서 별도 설치가 필요할 수
있습니다.
