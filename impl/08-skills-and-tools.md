# MagLab 구현 — 스킬 · 도구 · 패키지 카탈로그

> 설계 근거: PLAN.md §18 기술 스택 · plan/11-appendices.md 부록 B(MCP)·C(스킬)
> 횡단 문서 — "어느 스킬·도구·패키지를 어느 Phase에서 설치·활성화하는가".
> 규약: impl/README.md

## 1. 활성화 상태 요약

| 분류 | 항목 |
|---|---|
| **본 세션 완료** | git 리포(`main`)·`.gitignore`, `impl/` 계획 문서군. 환경 감사(§7). |
| **이미 사용 가능** | 구현용 Claude Code 스킬 전부(§2), `uv`·`git`·`node/npx`·`tectonic`·`ollama`. |
| **`00-foundation`에서 설치** | venv(Python 3.12), 코어 Python 패키지, `[dev]` 툴체인(§6). |
| **Phase별 설치** | extras 패키지·외부 솔버·MCP 커넥터 — Phase별 체크리스트(§8). |
| **설치 필요(미설치)** | `inkscape`(P1·P4 — `cairosvg` 폴백 가능), 외부 시뮬 솔버(P1·P3). |

## 2. Claude Code 스킬 — 구현 작업용

MagLab을 *구현하는* Claude Code 세션이 활용하는 스킬이다. **전부 현재 환경에서
이미 사용 가능 — 별도 설치 불필요.**

| 스킬 | 구현 Phase | 용도 | 상태 |
|---|---|---|---|
| `mcp-builder` | P0 | `mcp_server.py` FastMCP 서버 구축(§5.18 서버 역할)·MCP 카탈로그(부록 B) 구현 | ✓ |
| `skill-creator` | P0·P4 | MagLab 스킬 시스템(§5.6)·번들 스킬(부록 C) 저작. **§5.17·§13.3 스킬 자동 생성 파이프라인이 이 패턴을 차용** — P4 `skillgen.py` 설계 레퍼런스 | ✓ |
| `pdf` / `pdf-processing` | P4·P5 | 장비 매뉴얼·논문 PDF 판독 — `manual_rag`(§13.2)·문헌 전문 추출(§14.3) | ✓ |
| `arxiv-search` | P5 | `literature/connectors.py` arXiv 커넥터(§14.1) 구현·검증 | ✓ |
| `firecrawl-cli` / `firecrawl-web` | P4·P5 | 매뉴얼 웹 검색·다운로드(§13.2)·문헌 메타데이터 수집(§14) | ✓ |
| `doc-coauthoring` | P5·P6 | `authoring/`(§16)·리뷰 종합(§15) 워크플로 설계 레퍼런스 | ✓ |
| `pptx` | P6 | `authoring/present/` 슬라이드(§16.6) 구현·검증 | ✓ |
| `docx` | P6 | Wiley *Advanced Materials* Word 양식(§16.2) | ✓ |
| `webapp-testing` | 횡단(opt) | 게이트웨이·MCP 서버 스모크 테스트 보조 | ✓ |
| `xlsx` | opt | 데이터 표 입출력 보조 | ✓ |

> **중요 구분.** 위 표의 스킬은 *구현자가 MagLab을 만들 때* 쓰는 도구다.
> MagLab이 *런타임에 보유·생성*하는 SKILL.md 스킬(부록 C 번들 스킬,
> §13.3 계측기 스킬)은 MagLab의 산출물이며 별개다. 둘 다 SKILL.md 오픈
> 표준을 따르므로 Claude Code·Codex 등에서 상호 재사용 가능(§5.6).

## 3. Python 패키지 — `pyproject.toml` extras

PLAN §18 — **코어 설치는 GPU·LLM 없이.** 무거운 의존은 extras로 격리한다.

### 코어 (extras 없이 설치)
`typer` · `rich` · `prompt_toolkit` · `pyfiglet` · `rich-gradient`(CLI·UI §7) ·
`platformdirs` · `tomlkit`(설정 §7.1) · `keyring`(자격증명 §7.2) ·
`pydantic`(데이터 모델) · `jinja2`(템플릿 — instrument·authoring 공용) ·
`numpy` · `scipy` · `pandas` · `lmfit`(수치·피팅) · `prov`(provenance §17).
※ SQLite는 표준 라이브러리 `sqlite3`.

### extras

| extra | 패키지 | 사용 Phase |
|---|---|---|
| `[llm]` | `litellm`(Anthropic·OpenAI·Google·OpenAI호환 통합), `ollama` | P0 |
| `[mcp]` | `fastmcp`, `mcp`(Python SDK) | P0 |
| `[sim]` | `ubermag`, `oommfc`, `discretisedfield`, `micromagneticmodel`, `magnumnp` | P1·P3 |
| `[figure]` | `matplotlib`, `scienceplots`, `discretisedfield`, `pyvista`, `cairosvg` | P1·P3·P4 |
| `[instr]` | `pyvisa`, `pyvisa-sim`(목 계측기) | P4 |
| `[literature]` | `pyalex`, `semanticscholar`, `arxiv`, `habanero`, `scikit-learn`, `keybert`, `yake`, `mp-api`, `optimade`, `lancedb`, `sentence-transformers`, `pdfplumber` | P5 |
| `[reviewer]` | `rank-bm25`(BM25 하이브리드) + `[literature]`의 RAG 스택 공유 | P5 |
| `[authoring]` | `bibtexparser`(≥2.0), `pylatex`, `python-pptx`, `python-docx` | P6 |
| `[gateway]` | `slack-bolt`, `python-telegram-bot`, `discord.py` | P6 |
| `[dev]` | `ruff`, `mypy`, `pytest`, `pytest-cov`, `pre-commit` | Foundation~ |
| `[all]` | 위 전부 | — |

> 위임 CLI 백엔드(`codex`·`claude`·`gemini`)는 **외부 설치 도구**이며 pip
> 의존이 아니다 — 서브프로세스로 구동(§7.2). 매뉴얼·문헌 RAG 스택(`lancedb`·
> `sentence-transformers`·`pdfplumber`)은 `[instr]`·`[literature]`가 공유한다.

설치 예: `uv pip install -e ".[llm,mcp]"` (P0) · `uv pip install -e ".[all]"`.

## 4. 외부 바이너리 · 솔버

MagLab은 솔버를 직접 구현하지 않고 외부 바이너리에 위임한다(§2.4). pip 의존이
아니므로 별도 설치하며, 미설치 시 해당 Phase 기능만 비활성된다.

| 도구 | 용도 | Phase | 상태 | 설치 |
|---|---|---|---|---|
| OOMMF | CPU 미세자기 — **Mac 개발 주력** | P1 | ✗ | conda-forge / 소스 빌드, `oommfc` 래핑 |
| magnum.np | Python 미세자기 — Mac CPU 동작 | P1 | (pip `magnumnp`) | `[sim]` extra |
| MuMax3 | GPU 미세자기 | P1 | ✗ | GitHub 릴리스 — NVIDIA CUDA 필요(Mac 미지원, HPC용) |
| VAMPIRE | 원자론 스핀 동역학 | P3 | ✗ | 소스 빌드 / 바이너리 |
| Spirit | 원자론 스핀 동역학 | P3 | ✗ | pip `spirit` 또는 소스 |
| Quantum ESPRESSO | DFT(무료) | P3 | ✗ | conda-forge — Mac 빌드 가능 |
| VASP / FLEUR | DFT(VASP 상용 유료) | P3 | ✗ | 사용자 보유 라이선스 / FLEUR 소스 |
| TB2J | DFT→`J_ij` 추출 | P3 | ✗ | pip `TB2J` |
| `tectonic` | LaTeX 컴파일(§16.5) | P6 | **✓** | 설치됨 — `pdflatex` 불필요 |
| Inkscape | SVG→PDF 벡터 변환(§12.3·12.7) | P1·P4 | **✗** | `brew install inkscape` — **폴백: `cairosvg`**(`[figure]` 포함, 헤드리스·경량이나 SVG 기능 일부 제한). 스키매틱(P4) 본격화 전 설치 권장 |
| Ollama | 로컬 LLM 서버(§7.2) | P0 | **✓** | 설치됨 |
| `node`/`npx` | 논문검색 MCP 커넥터 구동(§14.7) | P5 | **✓** | 설치됨(v24.13) |

> Mac(Apple Silicon) 개발 환경의 시뮬 경로: **OOMMF/magnum.np CPU**로 P1
> 미세자기 검증(µMAG 표준문제), GPU·HPC 솔버는 `ssh_hpc`/`ssh_gpu` 백엔드로
> 원격 위임(§10.2). 외부 솔버 부재 시 P1·P3은 mock·골든 픽스처로 CI 통과.

## 5. MCP 서버

### MagLab이 클라이언트로 소비 (§5.18 역할 A)

| 서버 | 라이선스 | 역할 | Phase |
|---|---|---|---|
| `paperplain` | MIT | PubMed·arXiv·S2 통합 초벌 검색 | P5 |
| `@cyanheads/openalex-mcp-server` | Apache-2.0 | 서지계량·OA·retraction 필터 | P5 |
| `cite-mcp` | MIT | 다출처 병합·DOI 상세·BibTeX 포맷 | P5 |
| 과학 MCP(Materials Project·OPTIMADE·GPAW 등) | 각 서버 | 물성·구조·DFT 질의 | P0·P3 |

논문검색 커넥터 3종은 `npx`로 구동, `.maglab/mcp.json`에 **opt-in** 등록(§14.7).

### MagLab이 서버로 노출 (§5.18 역할 B)

`maglab mcp serve` — FastMCP 기반 자체 MCP 서버(부록 B 도구·리소스·프롬프트
카탈로그). P0에서 `mcp_server.py`로 구현. 외부 하네스(Claude Code 등) 연동용.

### 레지스트리

`.maglab/mcp.json` — 서버별 `type`(stdio/http)·`command`/`url`·`trust_level`·
`enabled`·`always_load`. lazy 연결·도구 네임스페이싱·동적 도구 로딩(§5.18).

## 6. 개발 도구

| 도구 | 용도 | 상태 |
|---|---|---|
| `git` | 버전 관리·Ralph iteration 커밋(§6.2) | ✓ 2.39.5 |
| `uv` | 패키지·venv 관리자 | ✓ 0.10.4 |
| `ruff` | 린트 + 포맷 | `[dev]` 설치 |
| `mypy` | 정적 타입 검사 | `[dev]` 설치 |
| `pytest`(+`pytest-cov`) | 테스트 러너 | `[dev]` 설치 |
| `pre-commit` | 커밋 게이트(비밀키 탐지 포함) | `[dev]` 설치 |
| GitHub Actions | CI(macOS·Linux × py3.11·3.12) | 원격 |

## 7. 이 머신의 현재 환경 (2026-05-19 감사)

```
OS        Darwin 24.6.0 arm64 (Apple Silicon)
Python    3.14.2 · 3.12.12 · 3.11.14   → venv는 3.12 채택
uv 0.10.4 · pip 25.3 · git 2.39.5
node v24.13.0 · npx ✓
tectonic ✓ · ollama ✓
inkscape ✗ · pandoc ✗ · pdflatex ✗   (pandoc·pdflatex은 설계상 불필수)
```

## 8. Phase별 설치 · 활성화 체크리스트

- [x] **사전(본 세션)** — git·`.gitignore`. `uv`·`node`·`tectonic`·`ollama` 확인.
- [ ] **Foundation** — `uv venv --python 3.12`; `uv pip install -e ".[dev]"`;
  코어 패키지 설치 검증(GPU·LLM 없이).
- [ ] **P0** — `uv pip install -e ".[llm,mcp,dev]"`; Ollama 모델 pull(로컬
  백엔드 테스트용); `mcp-builder`·`skill-creator` 스킬 활용.
- [ ] **P1** — `".[sim,figure]"`; OOMMF 또는 magnum.np 설치(미세자기 µMAG);
  Inkscape 설치 **또는** `cairosvg` 폴백 확인.
- [ ] **P2** — 추가 설치 없음(코어 `numpy`·`scipy`·`lmfit`로 충분).
- [ ] **P3** — `[sim]` 확장; VAMPIRE·Quantum ESPRESSO·TB2J 설치(또는 골든
  픽스처·mock로 대체); `pyvista` 헤드리스 동작 확인.
- [ ] **P4** — `".[instr]"`; Inkscape(스키매틱 SVG→PDF) 권장 설치;
  `pdf`·`firecrawl`·`skill-creator` 스킬 활용.
- [ ] **P5** — `".[literature,reviewer]"`; `npx`로 논문검색 MCP 커넥터 3종
  구동 확인; `arxiv-search`·`pdf` 스킬 활용.
- [ ] **P6** — `".[authoring,gateway]"`; `tectonic` 확인(설치됨);
  Slack/Telegram/Discord 봇 토큰 발급(사용자); `pptx`·`docx` 스킬 활용.

## 관련 문서

- 설치 절차: [`00-foundation.md`](00-foundation.md)
- 검증·CI: [`09-testing-and-ci.md`](09-testing-and-ci.md)
- Phase별 상세: `01`~`07` Phase 문서의 `PX.5` 절
- 설계: [`../PLAN.md`](../PLAN.md) §18 · [`../plan/11-appendices.md`](../plan/11-appendices.md) 부록 B·C
