# MagLab 설계 — 부록 A–J

> `PLAN.md`의 **부록 A–J**. 전체 개요·색인은 [`../PLAN.md`](../PLAN.md).
> 본문의 `(§N)` 교차참조는 문서 전역 절 번호이며, 절↔파일 대응표는
> `../PLAN.md` 「문서 구성」 절에 있다. 부록 E·F는 구현 착수 체크리스트다.

---

## 부록 A. CLI 명령어 트리

```
maglab                        # 대화형 REPL
maglab -p "<질의>"            # 비대화형 단발
maglab auth      set · list · test            # 인증 (API키/위임CLI/로컬)
maglab theme     list · set                   # 터미널 테마 (§7.8)
maglab physics   compute · units · oracle
maglab mat       list · show · search · build # build = 물질 DB 자동구축 (F5)
maglab sim       dft · atomistic · micro · pipeline · job · plot  # plot = F6
maglab fit       --effect <name> <data>       # 효과 피팅 레지스트리 (§11)
maglab analyze   load · model · consistency · symmetry
maglab figure    spec · render · compose · export · primitives   # §12
maglab instr     scaffold · scpi · script · check · ingest · implement  # F2
maglab lit       search · authors · keywords · journal   # F3·F4
maglab review    "<원고>"                     # F1 페르소나 패널
maglab write     "<결과>" --journal <name>    # F7 학술지 저술
maglab comms     revision · cover-letter · email · abstract · grant  # §16.3
maglab ralph     start · status · cancel
maglab gateway   setup · start · stop · status · install   # §8
maglab skill     list · install · create     # create = skill-creator (§5.17)
maglab ask "<자연어>"  ·  maglab run "<목표>"
maglab lab        note · plan                  # §13.5–§13.6 ELN·측정 계획
maglab present    slides · poster               # §16.6 발표 자료
maglab hypotheses "<주제>"  ·  explain "<데이터/결과>"   # §5.10–§5.11
maglab device     fom <소자스펙>                 # §11.7 소자 성능 지표
maglab cost       세션·런·Ralph 루프별 LLM·시뮬 비용   # §5.14
maglab lit graph  지식 그래프·인용 계보 질의            # §14.6
maglab mcp        add · list · enable · disable · serve   # MCP 레지스트리·서버 (§5.18)
maglab agents     list · show                  # 서브에이전트 정의 (§5.16)
maglab report · prov · config · task
```

## 부록 B. MCP 도구 카탈로그

`physics_compute`·`physics_check`·`convert_units` · `material_lookup`·
`material_search`·`material_build` · `sim_design`·`sim_validate`·`sim_run`·
`sim_parse` · `fit_effect`·`list_effects`·`symmetry_allowed` ·
`analysis_consistency` · `figure_design`·`figure_render`·`figure_compose`·
`figure_export`·`figure_list_primitives` · `instr_search_manual`·
`instr_ingest_manual`·`instr_generate_skill`·`instr_scaffold`·
`instr_safety_check` · `literature_search`·`literature_find_authors`·
`literature_keywords`·`journal_metrics` · `reviewer_build_panel`·
`reviewer_run_review` · `authoring_draft_section`·`authoring_verify_citations`·
`comms_draft` · `report_build`·`provenance_query`.
리소스: `materials://`·`literature://`·`provenance://`·`effects://`·
`manuals://`·`primitives://`.
프롬프트: `analyze_experiment`·`draft_methods`·`compare_samples`·`figure_caption`.
MCP 두 역할(클라이언트·서버)·3대 프리미티브·전송·레지스트리·보안 = §5.18.

## 부록 C. MagLab 스킬 카탈로그 (SKILL.md 오픈 표준)

번들 스킬 — `magnetotransport-fitting`·`sot-harmonic-hall`·`stfmr-analysis`·
`fmr-suite`·`orbital-hall`·`llg-dynamics`·`dmi-extraction`·`micromagnetics-setup`·
`multiscale-handoff`·`figure-dataplot`·`figure-schematic`·`literature-search`·
`literature-review`·`revision-letter`·`academic-email`·`cover-letter`·
`journal-templates`.
메타 스킬 — `skill-creator`(스킬 자동 생성·A/B 평가). 동적 생성 — 계측기별
스킬(§13.3). 구조: 디렉터리 + `SKILL.md` + `scripts/`·`references/`·`evals/`.
3단계 점진 공개. Claude Code·Codex 등과 이식 호환. 명세·저작·자동 생성 = §5.17.

## 부록 D. 정적 검증 규칙 (요약)

미세자기(셀<l_ex·α>0·전 region 파라미터·run≥수배τ) / 원자론(J_ij 완전·온도 vs
T_C) / DFT(k-메시·컷오프·SOC) / 핸드오프(스케일 N 출력단위=N+1 입력단위) /
장비(SCPI 안전 envelope·명령 순서) / 효과 피팅(필요 측정 기하 충족·텐서 rank
일치·파라미터 물리 경계) / Figure(데이터 패널이 DataPoint에 바인딩·벡터 출력·
저널 치수) / 저술(수치=데이터 볼트·인용=검증 풀).

## 부록 E. 핵심 기능 → 구현 매핑

| 기능 | 모듈 | 진입점 | Phase |
|---|---|---|---|
| F1 페르소나 리뷰어 + 리뷰·패치 | `reviewer/`·`core/ralph.py` A | `maglab review` | P5 |
| F2 매뉴얼→스킬 + 실험코드 Ralph | `instrument/manual_search·skillgen`·ralph B | `maglab instr implement` | P4 |
| F3 가중 키워드 검색 | `literature/keywords` | `maglab lit search` | P5 |
| F4 임팩트 메트릭 | `literature/journals` | `maglab lit journal` | P5 |
| F5 물질 DB 자동구축 | `physics/material_builder` | `maglab mat build` | P5 |
| F6 데이터→MuMax/OOMMF→figure | `sim/`·`figure/` | `maglab sim plot` | P1 |
| F7 학술지 양식 저술 | `authoring/`·ralph C | `maglab write` | P6 |
| Figure 제작 엔진 | `figure/`·ralph E | `maglab figure` | P1·P4 |
| 효과 피팅 레지스트리 | `analysis/providers·effects` | `maglab fit` | P2 |
| 인증 (API/위임CLI/로컬) | `llm/backends·auth` | `maglab auth` | P0 |
| CLI 디자인 (볼드 블록 UI) | `ui/` | (전역) | P0 |
| 메시징 게이트웨이 | `gateway/` | `maglab gateway` | P6 |
| 커뮤니케이션 스위트 | `authoring/comms/` | `maglab comms` | P6 |
| 가설 생성·평가 (D1) | `core/reasoning.py` | `maglab hypotheses` | P6 |
| 이상 결과 설명 (D2) | `core/reasoning.py` | `maglab explain` | P5 |
| 교정·계통오차·불확실도 (B4) | `analysis/calibration.py` | (§11 분석 내장) | P2 |
| 소자 성능 지표 FoM (E1) | `analysis/device_fom.py` | `maglab device fom` | P2 |
| 전자 실험노트 ELN (B1) | `lab/notebook` | `maglab lab note` | P5 |
| 측정 계획/DOE (B3) | `lab/planning` | `maglab lab plan` | P5 |
| 발표 자료 (C4) | `authoring/present/` | `maglab present` | P6 |
| 연구 루프 트리 탐색 | `core/orchestrator`·`experiment_manager` | (전역) | P0·P6 |
| 누적 연구 메모리 | `core/memory` (research_pool) | (전역) | P0 |
| 스텝별 비용·자원 추적 | `core/budget` | `maglab cost` | P0 |
| 무결성 차단 게이트·promise-check | `core/hooks`·`report/honesty_gate` | (전역) | P0 |
| 이론↔시뮬 bilevel 모델 발견 | `analysis/`·`sim/` | `maglab fit --discover` | P2·P3 |
| 능동학습·다중정밀도 DOE | `lab/planning` | `maglab lab plan` | P5 |
| 지식 그래프·인용 계보·문헌 무결성 | `literature/graph` | `maglab lit graph` | P5 |
| 저널별 리뷰 루브릭 | `reviewer/rubrics` | `maglab review` | P5 |
| 인용 의미 검증 | `authoring/citation_auditor` | (저술 내장) | P6 |
| 단계별 모델 라우팅 · 과학 MCP 연동 | `llm/`·MCP | (config) | P0 |
| 서브에이전트 · 오케스트레이션 디자인 | `core/orchestrator·subagents`·`agents/` | (전역) | P0 |
| 스킬 시스템 · 스킬 자동 생성 | `core/skills`·skill-creator | `maglab skill` | P0·P4 |
| MCP 통합 (클라이언트·서버·레지스트리) | `llm/mcp`·`mcp_server`·`.maglab/mcp.json` | `maglab mcp` | P0 |
| 논문검색 MCP 커넥터 · 리서치 오케스트레이션 | `literature/`·`agents/` | `maglab lit` | P5 |

## 부록 F. 효과 피팅 레지스트리 (구현 시 1차 문헌으로 확정)

| 효과 | 프로바이더 | 피팅식 (개요) | 핵심 파라미터 | 측정 기하 |
|---|---|---|---|---|
| 일반 홀 | magnetotransport | ρ_xy=R_H·B, R_H=1/nq | n | I∥x, B∥z, V_y |
| 이상 홀 AHE | magnetotransport | ρ_xy=R_0·B+μ₀R_s·M(H) | R_0, R_s | Hall bar, 포화 |
| TYJ 스케일링 | magnetotransport | ρ_AHE=a·ρ_xx0+b·ρ_xx² | a(외인성), b(내인성) | T 가변 |
| 평면 홀 PHE | magnetotransport | ρ_xy=(Δρ/2)sin2φ | Δρ | 면내 φ 회전 |
| 토폴로지컬 홀 THE | magnetotransport | ρ_THE=ρ_xy−R_0B−μ₀R_sM | 배경 차감 | ρ_xy(H)+M(H) |
| AMR | magnetotransport | ρ(θ)=ρ⊥+Δρcos²θ | Δρ_AMR | 면내 θ |
| SMR | magnetotransport | ρ_long=ρ+Δρ₀+Δρ₁(1−m_y²) | Δρ₁,Δρ₂,θ_SH,λ,G↑↓ | α/β/γ 각 스캔 |
| GMR/TMR | magnetotransport | G(θ)=G₀(1+(TMR/2)cosθ); TMR=2P₁P₂/(1−P₁P₂) | P₁,P₂ | 스핀밸브/MTJ |
| SOT 하모닉 홀 | spin_orbitronics | V_2ω 각의존 → H_DL,H_FL; H_DL=(H_DL_raw−2ξH_FL_raw)/(1−4ξ²) | H_DL,H_FL,ξ_DL,ξ_FL,ξ | 1ω·2ω 락인 |
| ST-FMR | spin_orbitronics | V_mix=S·F_sym+A·F_asym | S,A,H_res,ΔH,ξ_DL | CPW, RF 전류 |
| 스핀 펌핑/ISHE | spin_orbitronics | Δα=(γħ·g↑↓)/(4πμ₀Ms·d); V_ISHE | g↑↓,θ_SH,λ_sf | FMR 선폭 증가 |
| 오비탈 홀 OHE | spin_orbitronics | rank-3 텐서 σ^{l_γ}_{α,β}; θ_OH=σ_OH/σ_xx | σ_OH[α][β][γ], θ_OH | 하모닉 홀/Hanle MR/MOKE |
| FMR Kittel | ferromagnetic_resonance | (ω/γ)²=μ₀²H_res(H_res+M_eff) | M_eff,γ | 면내/면외 |
| Gilbert 댐핑 | ferromagnetic_resonance | ΔH=ΔH₀+(2α/γ)ω | α,ΔH₀ | 광대역 FMR |
| LLG (+STT/SOT) | magnetization_dynamics | dm/dt=−γ₀(m×H_eff)+α(m×ṁ)+τ_STT/SOT | α,τ_DL,τ_FL | — |
| 1D DW (q–Φ) | magnetization_dynamics | q–Φ 결합 ODE; Walker H_W=αK⊥/Ms | α,Δ,K⊥ | — |
| Thiele | domain_walls_skyrmions | G×v+αD·v=F; tanθ_SkH=G/(αD) | G,D,Q | — |
| DMI (BLS) | domain_walls_skyrmions | Δf=(γD_i/πMs)·k | D_i | BLS 비상반성 |

## 부록 G. 학술지 템플릿 & figure 치수 (요약)

| 저널 | 클래스 | 본문 한계 | 초록 | figure 폭(단/2단) |
|---|---|---|---|---|
| Nature | sn-jnl(sn-nature) | ~3,000단어 | 150단어 | 89 / 183 mm |
| Nature 자매지 | sn-jnl | ~3,000 | 150–200 | 89 / 183 mm |
| Nature Communications | sn-jnl | 5,000 | 200 | 89 / 183 mm |
| npj (Spintronics 등) | sn-jnl | 캡 없음(OA) | ≤250 권장 | 89 / 183 mm |
| Science | scifile(article.cls) | ~5,000 | 125 구조화 | 55·85 / 174 mm |
| Science Advances | scifile | ~10,000(총) | 200 | 55·85 / 174 mm |
| PRL | revtex4-2(prl) | 4쪽≈3,750단어 | ≤600자 | 86 / 178 mm |
| PRB/PRX/PR Applied | revtex4-2 | 무제한(Letter 4–5쪽) | ≤600자 | 86 / 178 mm |
| APL/JAP/APL Materials | revtex4-2(aip) | ≤3,500단어/유연 | ≤250단어 | 86 / 178 mm |
| IEEE Magnetics Letters | IEEEtran | 4–5쪽 | ~150단어 | 88.9 / 182 mm |
| JMMM / Acta Materialia | elsarticle-num | 유연 / ≤11,000 | ~200단어 | 90 / 190 mm |
| Advanced Materials | Word/PDF | ~10 조판쪽 | ≤200단어 | — |

벡터 PDF/EPS 우선, 폰트 임베딩(Type 42), 선폭 ≥0.25–0.5 pt, 라인아트 ≥600 dpi.

## 부록 H. 하네스 패턴 & 서브에이전트 계약

패턴 매핑 — 프롬프트 체이닝→시뮬·피팅 파이프라인 / 라우팅→서브커맨드 분기 /
병렬화→문헌 검색·패널 리뷰 / orchestrator-workers→연구 루프·핸드오프 /
evaluator-optimizer→Loop A/C/D/E / 자율 에이전트→`run` / Ralph 루프→반복 구현·
검토·저술·피팅·figure.

서브에이전트 계약은 6요소(§5.16): ① 단일 목표 ② 입력 명세 ③ 출력 스키마
④ 도구 예산 ⑤ 소스 가이드 ⑥ 작업 경계·모호성 처리. 정의 포맷 =
`agents/<name>.md`(frontmatter + 본문=시스템 프롬프트). 오케스트레이션 위상·
스킬 시스템·MCP 통합 상세는 §5.16–§5.18.

## 부록 I. 용어집

에이전트 하네스 / 컨텍스트 엔지니어링 / Ralph 루프 / Provenance / DataPoint /
데이터 볼트 / cite-then-write / 핸드오프 / sanity oracle / honesty gate /
EffectModel(효과별 정확한 피팅 포맷을 보유한 모델 단위) / ModelProvider(분야별
EffectModel 묶음) / 위임 CLI 백엔드(공식 인증된 에이전트 CLI를 서브프로세스
백엔드로 구동) / 페르소나 리뷰어(실명 인물이 아닌 공개 코퍼스 모델) / 볼드
솔리드 블록 로고 / FigureSpec(figure의 선언적 IR) / 스키매틱 프리미티브(자성
파라메트릭 벡터 템플릿) / 검증 가능한 오케스트레이터.

## 부록 J. 참고 자료 (조사 출처)

**하네스·오케스트레이션** — Anthropic *Building Effective Agents* / *Context
Engineering* / *Multi-Agent Research System*; Claude Agent SDK.

**MCP · 스킬 · 에이전트 표준** — Model Context Protocol 명세
(modelcontextprotocol.io, rev. 2025-11-25 — tools/resources/prompts·Streamable
HTTP·elicitation); Anthropic Agent Skills·SKILL.md 오픈 표준(agentskills.io)·
`skill-creator`; FastMCP·MCP Python SDK. 번들 논문검색 MCP 서버 —
`paperplain`(MIT)·`@cyanheads/openalex-mcp-server`(Apache-2.0)·`cite-mcp`(MIT).

**Ralph 루프** — Geoffrey Huntley *Ralph Wiggum*; AI Scientist v2 (arXiv:2504.08066).

**독립 CLI·인증·터미널 UI** — OpenAI Codex CLI(Apache-2.0); Claude Code/Gemini
CLI 인증; agentskills.io; LiteLLM; `keyring`; `rich`·`prompt_toolkit`·
`pyfiglet`·`rich-gradient`; Hermes Agent TUI.

**스핀트로닉스 효과 피팅** — Tian-Ye-Jin AHE 스케일링(PRL 103, 087206);
SMR(Chen et al.); 하모닉 홀(Hayashi PRB 89, 144425); ST-FMR(Liu PRL 106,
036601); 오비탈 홀(Choi Nature 619; arXiv:2409.20526); LLG+SOT 리뷰(JPCM 2022).

**Figure 생성** — PaperBanana(arXiv:2601.23265, 5-에이전트·이중경로); MatPlotAgent
(arXiv:2402.11453)·PlotGen(arXiv:2502.00988); AutomaTikZ(arXiv:2310.00367)·
DeTikZify·TikZilla; DiagrammerGPT(arXiv:2310.12128); SciencePlots; Ubermag
`discretisedfield`; AI figure 무결성(arXiv:2603.16159, Cell Press 정책).

**메시징** — NousResearch hermes-agent; Vercel Chat SDK; `slack-bolt`·
`python-telegram-bot`·`discord.py`.

**학술지·저술** — Springer Nature `sn-jnl`; Science `scifile`; APS REVTeX 4.2;
AIP·IEEEtran·elsarticle; Nature/APS/IEEE/Elsevier figure 규격; COPE Authorship
and AI tools.

**AI-과학 에이전트** — AI Scientist v1/v2; Coscientist(Nature 624); ChemCrow;
Google AI co-scientist; LLaMP; VASPilot; PROV-AGENT.

---

## 관련 모듈

- [`../PLAN.md`](../PLAN.md) — 개요·아키텍처·로드맵·「문서 구성」 색인
- 부록 A–J는 전 모듈(§5–§17)의 참조 테이블 — 각 항목이 해당 절을 가리킨다.
  부록 E(기능→구현 매핑)·F(효과 피팅 레지스트리)가 구현 착수 체크리스트.
