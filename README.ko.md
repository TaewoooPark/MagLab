<h1 align="center">MagLab</h1>

<p align="center">
  <strong>자성 및 스핀트로닉스 연구를 위한 AI for Science 하네스.</strong>
</p>

<p align="center">
  <a href="README.md">English README</a> ·
  <a href="docs/manuals/en/index.md">Manuals</a> ·
  <a href="docs/manuals/ko/index.md">한국어 매뉴얼</a>
</p>

<p align="center">
  <img src="https://img.shields.io/github/license/TaewoooPark/MagLab?style=flat-square&labelColor=000000&color=333333" alt="License">
  <img src="https://img.shields.io/github/stars/TaewoooPark/MagLab?style=flat-square&logo=github&logoColor=white&labelColor=000000&color=333333" alt="GitHub stars">
  <img src="https://img.shields.io/github/last-commit/TaewoooPark/MagLab?style=flat-square&labelColor=000000&color=333333" alt="Last commit">
  <img src="https://img.shields.io/github/languages/top/TaewoooPark/MagLab?style=flat-square&labelColor=000000&color=333333" alt="Top language">
  &nbsp;
  <img src="https://img.shields.io/badge/Python-000000?style=flat-square&logo=python&logoColor=white&labelColor=000000" alt="Python">
  <img src="https://img.shields.io/badge/NumPy-000000?style=flat-square&logo=numpy&logoColor=white&labelColor=000000" alt="NumPy">
  <img src="https://img.shields.io/badge/SciPy-000000?style=flat-square&logo=scipy&logoColor=white&labelColor=000000" alt="SciPy">
  <img src="https://img.shields.io/badge/lmfit-000000?style=flat-square&labelColor=000000&color=333333" alt="lmfit">
  <img src="https://img.shields.io/badge/Pydantic-000000?style=flat-square&logo=pydantic&logoColor=white&labelColor=000000" alt="Pydantic">
</p>

![MagLab research lifecycle](image1.png)

## MagLab을 만든 이유

MagLab은 자성 및 스핀트로닉스 연구자가 AI for Science를 실제 연구 도구로
사용할 수 있게 만들기 위한 플랫폼입니다. 목표는 멋진 데모 프롬프트를 만드는
것이 아니라, 연구자가 실제로 시간을 빼앗기는 지점을 구체적으로 지원하는
것입니다. 문헌 탐색과 검증, 물질 스택의 파라미터화, 단위 변환, 물리 범위
체크, 다중 스케일 시뮬레이션 연결, 스핀트로닉스 효과 피팅, 재현 가능한 그림
생성, 계측기 스크립트 작성, 전자 연구노트, 논문 리뷰, 그리고 검증된 결과를
논문, 포스터, 발표, rebuttal, grant text로 옮기는 과정까지 하나의 하네스로
묶습니다.

핵심 설계는 MagLab이 하네스 플랫폼이라는 점입니다. LLM 계층은 계획하고,
라우팅하고, 설명하고, 초안을 작성합니다. 실제 과학 작업은 물리 공식, 단위
변환, 물질 데이터베이스, 시뮬레이션 파이프라인, 피팅 모델, 그림 렌더러,
문헌 커넥터, SCPI 안전 검사, 데이터 lineage, 리뷰 워크플로 같은 도메인
모듈이 수행합니다. 연구자를 대체하려는 도구가 아니라, 연구자의 루프를 더
빠르고 구조적이며 재현 가능하게 만드는 도구입니다.

## MagLab이 줄이는 연구 병목

| 연구 병목 | MagLab이 지원하는 것 |
|---|---|
| 문헌 과부하 | 논문 폴더에서 키워드 추출, OpenAlex/Semantic Scholar/arXiv/Crossref 검색, evidence matrix 생성, 저자/저널/인용 그래프/로컬 corpus 확인. |
| 물질과 단위 처리 | 자성 물질 조회, multilayer stack 생성, exchange length/FMR/domain-wall/skyrmion 공식 계산, 자기 단위 변환, physics oracle 실행. |
| 시뮬레이션 handoff | micromagnetic spec 생성과 검증, DFT/atomistic 입력 생성, solver 출력 파싱, DFT -> atomistic -> micromagnetic -> device workflow 연결. |
| 피팅과 해석 | AMR, AHE, OHE, PHE, SMR, USMR, ST-FMR, FMR/Kittel, damping, spin pumping/ISHE, DMI, domain-wall, skyrmion/Thiele, hysteresis, Curie-temperature 모델 피팅. |
| 그림 재현성 | `FigureSpec` JSON 생성, journal-aware vector figure 렌더링, multi-panel composition, spintronics schematic primitive catalog 사용. |
| 계측기 스크립팅 | PyVISA driver scaffold, SCPI sequence 검증, manual RAG ingest, 실험 설명 기반 script 생성, hardware 실행 전 safety check. |
| 실험 기억 | 구조화된 ELN entry 작성, 날짜/샘플/tag/type별 note 조회, measurement plan 생성, DOE/active-learning 기반 다음 실험 제안. |
| 리뷰와 비판 | persona-style manuscript review, consensus/dissent synthesis, anomalous result explanation, AI assistance disclosure. |
| 논문과 커뮤니케이션 | manuscript section, cover letter, revision letter, rebuttal, abstract, grant, email, slides, poster 초안 생성. |
| 오케스트레이션 | interactive REPL, Ralph loop, MCP server/client, subagent, skill, gateway bot, cost tracking, checkpoint, provenance record로 연구 lifecycle 조율. |

## 바로 시작하기

먼저 MagLab을 전역 터미널 프로그램으로 설치합니다. 권장 research bundle은
MagLab의 연구 기능 전체를 한 번에 넣고, 남은 provider, solver, instrument,
gateway 설정은 터미널 안에서 확인하도록 안내합니다.

```sh
git clone https://github.com/TaewoooPark/MagLab.git
cd MagLab
pipx install --editable ".[research]"
maglab doctor
maglab setup all
maglab manual --lang ko
```

이후에는 어떤 연구 폴더에서든 `maglab`을 실행하면 됩니다. MagLab은
config/data/cache는 전역 사용자 앱 경로에 보관하고, 프로젝트 산출물은 실행한
폴더를 기준으로 읽고 씁니다.

```sh
cd ~/research/my_spintronics_project
maglab workspace init
maglab workspace status
maglab
```

LLM key 없이 deterministic tool부터 사용할 수 있습니다.

```sh
maglab physics compute exchange_length A=13e-12 Ms=860e3
maglab physics units 1000 Oe T
maglab mat show Permalloy
maglab analyze model stfmr
maglab figure primitives list
```

자연어 오케스트레이션, 초안 작성, 리뷰, agent workflow를 쓰려면 LLM backend를
연결합니다. Codex는 공식 Codex CLI의 인증 상태를 위임해서 사용하며, MagLab은
Codex OAuth token을 저장하지 않습니다. 직접 API provider로는 Anthropic, Grok,
DeepSeek, Qwen, Kimi, Gemini, OpenAI를 지원합니다.

```sh
maglab auth codex
maglab auth anthropic
maglab auth qwen
maglab auth status
maglab
```

REPL 안에서는 `/help`로 전체 slash-command tree를 볼 수 있습니다.
`/connect codex`, `/connect <provider>`, `/connect api <provider>`,
`/connect ollama`로 backend를 바꿀 수 있습니다. API-key 명령은 터미널 숨김
입력을 사용하며, `maglab auth set <provider>`는 명시적 key 저장과 scripting
용도로 계속 사용할 수 있습니다. `/reset config`는 이전 config backup으로
복구하고, `/reset defaults`는 깨끗한 기본 config로 되돌립니다.

`maglab doctor`는 설치 감사 명령입니다. 현재 폴더, LLM backend, feature extra,
GPU/SSH/no-GPU 시뮬레이션 경로, 한국어/영어 매뉴얼, figure/export 준비 상태,
poster/deck template, workspace-scoped LLM file tool, physics/provenance gate가
`plan/`의 UX 의도와 맞는지 한 번에 보여줍니다.

스크립트나 CI에서는 one-shot 모드를 사용할 수 있습니다.

```sh
maglab -p "Plan a reproducible ST-FMR analysis workflow for Pt/CoFeB/MgO"
```

## 매뉴얼

README는 지도이고, 매뉴얼은 실제 사용 설명서입니다.
전역 설치된 CLI에서도 바로 볼 수 있습니다.

```sh
maglab manual --lang ko
maglab manual figures --lang ko
```

| 영역 | English | 한국어 |
|---|---|---|
| 매뉴얼 인덱스 | [docs/manuals/en/index.md](docs/manuals/en/index.md) | [docs/manuals/ko/index.md](docs/manuals/ko/index.md) |
| 문헌 인텔리전스 | [English](docs/manuals/en/literature.md) | [한국어](docs/manuals/ko/literature.md) |
| 물질과 물리 | [English](docs/manuals/en/materials-physics.md) | [한국어](docs/manuals/ko/materials-physics.md) |
| 시뮬레이션 | [English](docs/manuals/en/simulation.md) | [한국어](docs/manuals/ko/simulation.md) |
| 분석과 피팅 | [English](docs/manuals/en/analysis-fitting.md) | [한국어](docs/manuals/ko/analysis-fitting.md) |
| 그림 | [English](docs/manuals/en/figures.md) | [한국어](docs/manuals/ko/figures.md) |
| 계측기 | [English](docs/manuals/en/instruments.md) | [한국어](docs/manuals/ko/instruments.md) |
| 연구노트와 계획 | [English](docs/manuals/en/lab-planning.md) | [한국어](docs/manuals/ko/lab-planning.md) |
| 리뷰와 이상 현상 설명 | [English](docs/manuals/en/review-explain.md) | [한국어](docs/manuals/ko/review-explain.md) |
| 논문 작성과 커뮤니케이션 | [English](docs/manuals/en/authoring-comms.md) | [한국어](docs/manuals/ko/authoring-comms.md) |
| 오케스트레이션, agent, MCP, gateway | [English](docs/manuals/en/orchestration.md) | [한국어](docs/manuals/ko/orchestration.md) |

## 예시 연구 루프

**문헌에서 실험 계획까지**

```sh
maglab lit search papers/pt_cofeb_mgo --top-n 40
maglab lit authors "spin orbit torque CoFeB MgO"
maglab lab plan "SOT efficiency in Pt/CoFeB/MgO" --n-doe 16 --output sot_plan.yaml
```

**측정 데이터에서 피팅과 그림까지**

```sh
maglab analyze load data/stfmr.csv --columns frequency,field,voltage
maglab analyze model stfmr
maglab fit --effect stfmr data/stfmr.csv --method least_squares
maglab sim plot data/stfmr.csv --journal aps --format pdf --output figures/stfmr.pdf
```

**다중 스케일 시뮬레이션 handoff**

```sh
maglab sim dft --structure bcc_fe --engine qe --calc-type jij --output-dir runs/dft_fe
maglab sim atomistic --engine vampire --j-ij-k 398 --t-max-k 1300 --output-dir runs/vampire_fe
maglab sim pipeline --structure bcc_fe --scales dft,atomistic,micro,device --backend mock
```

**계측기 workflow**

```sh
maglab instr ingest "Keithley 2400" --manufacturer Keithley --manual-path manuals/keithley_2400.pdf
maglab instr skillgen "Keithley 2400" --manufacturer Keithley --safety-model keithley-2400
maglab instr script "Keithley 2400" --description "field sweep Hall voltage measurement" --output hall_sweep.py
maglab instr check hall_sweep.py
```

**검증된 결과를 바탕으로 authoring**

```sh
maglab write "ST-FMR fit gives xi_DL=0.12 with provenance IDs ..." --journal prl --dry-run
maglab comms cover-letter --journal "Physical Review Letters" --title "Spin-orbit torque ..."
maglab present templates --detail
maglab present slides "Key results and figures from the SOT study" --template aps-12min --format beamer --n-slides 10
maglab present poster "Key results and figures from the SOT study" --template aps-march-poster --format svg
```

## 명령어 표면

```text
maglab                    interactive research agent
maglab -p "QUERY"         non-interactive one-shot query

auth      codex · claude · gemini-cli · ollama · anthropic · grok · deepseek · qwen · kimi · gemini · openai · set · list · status · test
physics   compute · units · oracle
mat       list · show · build
sim       doctor · micro · validate · plot · job · dft · atomistic · pipeline
fit       --effect EFFECT DATA.csv
analyze   load · model · consistency · symmetry
device    fom
figure    spec · render · compose · export
          primitives list · show
instr     scaffold · scpi · script · check · ingest · skillgen · implement
lit       search · authors · keywords · journal · graph
lab       note · note-list · plan
review    MANUSCRIPT
explain   ANOMALY
ralph     start · status · cancel
write     RESULTS
comms     revision · cover-letter · email · abstract · grant · rebuttal
gateway   setup · start · stop · status · install
present   templates · slides · poster
hypotheses TOPIC
mcp       list · serve · add · enable · disable
agents    list · show
skill     list
cost
manual    [topic] --lang en|ko
config    show · path · restore · reset
install
doctor
workspace status · init · tree
theme     list · set
version · info
```

## 아키텍처

![MagLab agent architecture](image2.png)

MagLab은 계층형 하네스로 구성됩니다.

```text
researcher intent
  -> CLI / REPL / gateway / MCP
  -> orchestrator, subagents, skills, checkpoints, budgets
  -> physics oracle, honesty gate, DataPoint, W3C PROV ledger
  -> deterministic engines
       physics · materials · simulation · analysis · figures · instruments
  -> lifecycle applications
       literature · lab notebook · review · authoring · communications
  -> human-reviewed scientific output
```

검증 계층은 MagLab의 목적 자체가 아닙니다. 과학 연구에서 실제로 유용한 도구가
되기 위한 안전 레일입니다. MagLab은 질문에서 evidence, 실험, 분석,
커뮤니케이션으로 이어지는 루프를 빠르게 돌리되, 나중에 다시 검토할 수 있는
구조를 남기도록 설계되어 있습니다.

## 패키지 구조

```text
maglab/
├── core/          orchestrator, hooks, autonomy, budgets, checkpoints, Ralph, subagents
├── llm/           provider abstraction, credentials, tool schemas, MCP client
├── physics/       formulae, units, materials database, physics oracle
├── sim/           DFT, atomistic, micromagnetic, multiscale pipeline, backends
├── analysis/      effect registry, fitting, consistency, symmetry, device FoM
├── figure/        FigureSpec, renderers, primitives, journal styles, exports
├── instrument/    SCPI, PyVISA scaffold, manual RAG, safety checks, scripts
├── literature/    connectors, corpus, RAG, graphs, authors, journals, keywords
├── lab/           ELN entries, measurement planning, active learning
├── reviewer/      persona review, meta-review, rubrics, disclosure, corpus RAG
├── authoring/     manuscript, BibTeX, data vault, slides, posters, comms
├── gateway/       Slack, Telegram, Discord daemon adapters
├── provenance/    DataPoint, W3C PROV ledger, store
├── report/        honesty gate and report rendering
├── ui/            terminal rendering and themes
└── mcp_server.py  external agent tool server
```

`harness.manifest.json`는 이 패키지를 agent society로 묶습니다.
`local-context-librarian`, `search-scout`, `citation-auditor`, `paper-reviewer`,
`synthesis-editor`, `physics-validator`, `result-analyst`, `experiment-manager`,
`hypothesis-gen`, `comms-writer`가 정의되어 있습니다.

## 설치 세부 사항

Python 3.11부터 3.13까지 지원합니다.

```sh
uv pip install -e .                    # core
uv pip install -e ".[research]"        # 권장: 모든 연구 기능
uv pip install -e ".[llm]"             # LLM backends
uv pip install -e ".[mcp]"             # MCP server and client
uv pip install -e ".[sim]"             # simulation stack
uv pip install -e ".[figure]"          # plotting and figure rendering
uv pip install -e ".[instr]"           # PyVISA and instrument manuals
uv pip install -e ".[literature]"      # literature APIs and RAG
uv pip install -e ".[reviewer]"        # reviewer panel support
uv pip install -e ".[authoring]"       # papers, slides, posters, docs
uv pip install -e ".[gateway]"         # messaging gateway
uv pip install -e ".[dev]"             # ruff, mypy, pytest, pre-commit
```

일반 연구용 설치에서는 `.[research]` extra를 권장합니다. 설치 후
`maglab setup all`을 실행하면 각 기능의 준비 상태, 터미널 설정 명령, 대응되는
REPL slash command를 한 번에 볼 수 있습니다. MagLab REPL 안에서는 `/setup`,
`/setup <feature>`, 또는 `/setup-llm`, `/setup-literature`,
`/setup-simulation`, `/setup-figure`, `/setup-instrument`,
`/setup-authoring`, `/setup-review`, `/setup-gateway`, `/setup-mcp`를 사용할 수
있습니다. 이미 준비된 dependency나 외부 명령은 그대로 통과시키고, 부족한 부분만
터미널에서 알려줍니다.

일부 시뮬레이션 엔진은 별도 외부 바이너리나 실행 환경이 필요합니다. 예를 들면
OOMMF, MuMax3, magnum.np, VAMPIRE, VASP, Quantum ESPRESSO, HPC/GPU 환경입니다.
MagLab은 이런 solver를 직접 소유하지 않아도 입력 생성, spec 검증, mock path,
준비된 출력 파싱을 수행할 수 있습니다.

## 개발

```sh
uv pip install -e ".[dev]"
ruff check maglab/ tests/
mypy maglab/
pytest
```

테스트는 smoke, integrity, golden, integration marker로 구성됩니다. 물리,
피팅, 인용, 수치 정확성은 deterministic validation을 기준으로 하며,
LLM-as-judge를 사용하지 않습니다.

## 프로젝트 문서

- [MAGLAB.md](MAGLAB.md): persistent project context와 invariant principles
- [harness.manifest.json](harness.manifest.json): subagent, workflow, model routing
- [Manuals](docs/manuals/en/index.md): feature-by-feature operating guide
- [한국어 매뉴얼](docs/manuals/ko/index.md): 기능별 한국어 사용 설명서

## 라이선스

MIT. [LICENSE](LICENSE)를 참고하세요.

<p align="center">
Built with Python, NumPy, SciPy, lmfit, Matplotlib, Pydantic, and the assumption that researchers remain responsible for science.
</p>
