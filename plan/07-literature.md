# MagLab 설계 — 문헌·발견 인텔리전스

> `PLAN.md`의 **§14** 상세. 전체 개요·색인은 [`../PLAN.md`](../PLAN.md).
> 본문의 `(§N)` 교차참조는 문서 전역 절 번호이며, 절↔파일 대응표는
> `../PLAN.md` 「문서 구성」 절에 있다.

---

## 14. 문헌·발견 인텔리전스 — `literature/`

### 14.1 학술 데이터 백본

| 소스 | 라이브러리 | 용도 |
|---|---|---|
| OpenAlex | `pyalex` | 1차 그래프 — 주제별 연구자·works·venue (2026-02부터 무료 키) |
| Semantic Scholar | `semanticscholar` | 저자 코퍼스·h-index·추천·SPECTER2 |
| arXiv | `arxiv` | 전문/LaTeX, `cond-mat.mes-hall` 등 |
| CrossRef | `habanero` | DOI 메타데이터 검증 |

기존 MCP 서버 래핑·재사용 — 검증된 논문검색 MCP 커넥터·다중 에이전트 리서치
오케스트레이션은 §14.7. Google Scholar는 공식 API 부재.

### 14.2 권위 연구자 탐색 (F1 1단계)

OpenAlex 토픽 ID → `authors?filter=topics.id&sort=cited_by_count` 상위 저자
→ h-index·소속·최근 활동으로 순위.

### 14.3 가중 키워드 추출 + 검색 (F3)

`maglab lit search <폴더>` — 논문 PDF 전문 추출 → 하이브리드 가중 키워드
(TF-IDF 40% + KeyBERT/specter 40% + YAKE 20%, 정규화·중복제거) → LLM 도메인
재순위 → 가중 키워드로 §14.1 소스 검색·랭킹.

### 14.4 학술지 임팩트·품질 메트릭 (F4)

진짜 JCR IF는 유료·재배포 불가. MagLab는 자유 메트릭을 명시 라벨링 — SJR+사분위
(scimagojr CSV 번들), OpenAlex `2yr_mean_citedness`(IF 유사, 실시간),
Eigenfactor(번들). "JCR IF" 오칭 금지.

### 14.5 물질 DB 자동 구축 (F5)

`maglab mat build "Ta(5)/CoFeB(1)/MgO(2)"` — 스택 파싱 → 층별 데이터(Materials
Project `mp-api`·NEMAD CSV 번들·OPTIMADE) + 문헌 추출(주요 스탯 + DOI) → 각
값을 `DataPoint`로 `materials.yaml`에 확장. LLM 기억이 아닌 DB·문헌만.

### 14.6 지식 그래프 · 인용 계보 · 문헌 무결성

§14의 발견 레이어를 평면 검색에서 *그래프·검증*으로 끌어올린다.

- **자성 지식 그래프** (`literature/graph.py`) — 노드 = 물질·현상·물성·방법·
  소자, 엣지 = 문헌이 보고한 관계. 문헌에서 자동 추출·축적한다. 그래프 경로
  탐색으로 비자명한 연결을 발견한다(예: 교환 바이어스 → IrMn 반강자성 → SOT
  소자). 가설 생성(§5.10)·물질 DB(§14.5)가 이 그래프를 공유한다.
- **관계 유형 인용 계보** — 인용을 평면 수가 아니라 *타입 그래프*로 기록:
  논문 A가 B를 extends / applies / evaluates / **contradicts**. 한 결과의
  개념 계보와 반박 이력을 추적할 수 있다.
- **문헌 무결성 검사** — 논문이 KB·인용 풀에 들어가기 전: ① **retraction 검사**
  (철회·정정 표시 논문 차단·경고) ② **모순 탐지**(논문 간 상충 보고값 플래그).
  honesty gate(§17)의 문헌 입구 단계 — 저술 인용(§16.4)이 이를 통과한 문헌만 쓴다.

### 14.7 논문 검색 MCP 커넥터 · 리서치 오케스트레이션

§14를 검증된 외부 도구와 다중 에이전트 워크플로우로 보강한다 — 실사용으로
검증된 "리서치 스택"의 통합.

**논문 검색 MCP 커넥터.** `.maglab/mcp.json`에 기본 등록(opt-in, `npx`로
구동, 라이선스 명시·출처 표기). MagLab는 이들을 §5.18 클라이언트로 흡수한다 —
코드를 포크·번들하지 않고 서브프로세스로 *구동*만 한다.

| 커넥터 | 라이선스 | 역할 |
|---|---|---|
| `paperplain` | MIT | PubMed·arXiv·Semantic Scholar 통합 초벌 검색, 제목 기반 lookup |
| `openalex` (`@cyanheads/openalex-mcp-server`) | Apache-2.0 | 서지계량 — 인용수·OA·retraction·저자/소스/토픽 필터 |
| `cite-mcp` | MIT | 다출처(S2·OpenAlex·Crossref) 병합·중복제거, DOI 상세, 추천 논문, BibTeX/APA 포맷 |

§14.1 직접 API 백본과 **상보 관계** — MCP 커넥터 우선, 미가용 시 직접 API로
폴백(검증된 운용 패턴). 셋은 역할이 갈린다: 초벌 검색은 `paperplain`,
메타데이터 품질·필터는 `openalex`, 병합·DOI 상세·인용 포맷은 `cite-mcp`.

**리서치 오케스트레이션.** 문헌 조사를 §5.16 오케스트레이터-워커 위상으로
구현한다 — 5개 서브에이전트, 각각 §5.16의 6요소 계약을 따른다:

| 서브에이전트 | 책임 | 병렬 |
|---|---|---|
| `local-context-librarian` | 로컬 노트·기존 레퍼런스에서 근거·중복을 선확인 | ○ |
| `search-scout` | MCP·스킬로 후보 논문 광역 수집 (query family 3–6개, tier 분류) | ○ |
| `citation-auditor` | DOI·메타데이터·중복·OA·retraction 검증 | ○ |
| `paper-reviewer` | 핵심 논문 3–7편 정독 — claim/evidence·방법 추출 | ○ |
| `synthesis-editor` | 주제별(논문별 아님) 합성 보고서 | ✗ |

명명 워크플로우(`harness.manifest.json`에 등록, 서브에이전트 실행 순서):
`survey` · `paper-review` · `citation-map` · `local-gap`.

**증거 매트릭스.** 후보 논문을 `evidence_matrix`에 누적한다: `ref_key`·`tier`·
`title`·`authors`·`year`·`venue`·`doi`·`url`·`openalex_id`·`s2_id`·`oa_status`·
`retraction_status`·`verification_status`·`notes`. 합성 전 검증을 끝낸다.

**품질 게이트.** 모든 사실 주장 → DOI/URL/OpenAlex ID/섹션·그림·표 근거.
DOI 우선 중복제거(없으면 정규화 제목). retraction·정정은 합성 전 플래그.
미상 항목은 추측 금지·`확인 불가` 표시. §14.6 무결성 검사·§16.7 인용 의미
검증과 연결된다.

**스킬.** OpenAlex REST 쿼리 전략·체계적 리뷰 워크플로우를 MagLab 네이티브
스킬(`literature-search`·`literature-review` — §5.17 규약, 부록 C)로 구현한다.
이 워크플로우는 방법론이라 재구현하며, 외부 스킬 파일을 그대로 번들하지 않는다.

---

## 관련 모듈

- [`01-harness.md`](01-harness.md) — 리서치 오케스트레이션 = §5.16 / 논문검색 MCP 커넥터 = §5.18
- [`08-review.md`](08-review.md) — 권위 연구자 탐색(§14.2)이 페르소나 패널에 공급
- [`09-authoring.md`](09-authoring.md) — cite-then-write 인용 파이프라인
- [`10-integrity.md`](10-integrity.md) — 문헌 무결성·retraction 검사
- [`../PLAN.md`](../PLAN.md) — 개요·아키텍처·로드맵
