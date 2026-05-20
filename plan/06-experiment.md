# MagLab 설계 — 실험 워크플로 (장비 코드 · ELN · 측정 계획)

> `PLAN.md`의 **§13** 상세. 전체 개요·색인은 [`../PLAN.md`](../PLAN.md).
> 본문의 `(§N)` 교차참조는 문서 전역 절 번호이며, 절↔파일 대응표는
> `../PLAN.md` 「문서 구성」 절에 있다.

---

## 13. 실험 워크플로 — 장비 코드·실험노트·측정 계획 — `instrument/` · `lab/`

> 에이전트는 장비를 실시간 제어하지 않는다. 코드를 생성·정적검증하고 사람이
> 실행한다.

### 13.1 코드 생성 기반

`scaffold.py`(PyVISA 백엔드 골격) · `scpi.py`(SCPI 시퀀스 생성·정적검증) ·
`script.py`(측정 스크립트) · `safety.py`(하드웨어 안전 envelope 정적검증) ·
`mock.py`(가상 계측기 — 하드웨어 없이 드라이런) · `templates/`(안전 SCPI 순서
내장 Jinja2).

### 13.2 매뉴얼 자동 검색·판독

장비를 다루려 할 때 MagLab는 **반드시 정확한 품명을 묻는다**(모델명 추측 금지).
정확 모델 확보 후: ① `manual_search.py` — 웹 검색으로 매뉴얼 PDF 검색·다운로드
② PDF 스킬로 판독(텍스트·표 추출) ③ `manual_rag.py` — 구조 인식 청킹(SCPI
명령당 1청크), 임베딩(`voyage-code-2`/로컬 `nomic-embed-text`), LanceDB 인덱스
④ `skillgen.py` — 계측기 SKILL.md 자동 생성.

### 13.3 스킬 자동 생성

`skills/<instrument>/`에 `SKILL.md` + `SCPI_REFERENCE.md` + `LIMITS.md` +
`scripts/retrieve_scpi.py` 생성. 본문은 RAG 검색을 인라인 호출. SKILL.md 오픈
표준이라 Claude Code·Codex에서도 재사용. 자동 생성·A/B 평가·반복 개선
파이프라인은 §5.17.

### 13.4 실험 코드 Ralph 구현 (Loop B)

`maglab instrument implement` — 실험 자연어 설명 + 장비 목록 → §13.2로 매뉴얼
스킬화 → 작업 분해 → Ralph Loop B(생성 스킬로 코드 구현 → 목 계측기 `pytest`
→ 실패 파싱 → 수정 → 반복). `safety.py` 통과 필수. 실제 실행은 Tier 3.

### 13.5 전자 실험노트 (ELN) — `lab/notebook`

측정·시료·관찰을 기록하는 provenance 연결 노트. 실시간 장비 제어가 아닌
*기록·관리*다.

- 구조: `notebook/`에 날짜별 Markdown 엔트리, frontmatter(date·sample·
  instrument·tags·datapoints). grep + 문헌식 색인으로 검색.
- **자동 초안**: MagLab가 측정을 분석·피팅하면 ELN 엔트리를 자동 초안(무엇을
  분석했는지·결과·provenance) → 연구자가 편집·확인. 노트가 부분적으로 스스로
  쓰인다.
- provenance 연결: 모든 엔트리가 provenance 엔티티(어느 데이터·피팅·시료)에
  연결. 엔트리는 시료 ID/스택을 인라인 참조.
- UX: `maglab lab note "..."` 또는 분석 직후 에이전트가 "기록할까요?" 제안.
  측정 유형별 템플릿, 일·주간 다이제스트, FAIR 포맷 내보내기(공유·아카이브).

### 13.6 측정 계획 / DOE — `lab/planning`

연구 목표 → 측정 캠페인 설계: 무엇을·파라미터 범위·스윕 순서·예상 결과.

- **물리 인식**: §11 효과 레지스트리의 `measurement_config`를 *역으로* 사용 —
  "물리량 X를 원함" → "측정 Y·기하 Z" (예: 스핀 홀 각 → 하모닉 홀 또는
  ST-FMR; 댐핑 → 광대역 FMR).
- **DOE**: 다파라미터면 완전/부분 요인배치·반응표면·Latin hypercube 설계를
  제안, 시간·비용 추정. (적응형 베이지안 캠페인은 향후 확장.)
- 산출: 측정 목록 — 각 측정의 타깃 물리량·장비·스윕(변수·범위·스텝)·예상
  신호·선행조건. 편집 가능한 living 체크리스트.
- UX: `maglab lab plan "<목표>"` → 구조화 계획. 측정이 완료되면 ELN(§13.5)이
  계획 대비 진행을 기록. "다음 측정은 X" 프롬프트.

### 13.7 능동학습·다중 정밀도 측정 최적화

§13.6의 측정 계획을 *정적 그리드 스윕*에서 *능동학습 루프*로 끌어올린다.

- **theorist↔experimentalist 분리** — theorist는 현 데이터에 현상학 모델을
  피팅(§11)하고, experimentalist는 그 모델들을 *가장 잘 구별하는* 다음 측정
  조건을 선택한다. 둘이 공유 상태(`StandardState` — 측정 조건·수집 데이터·현
  최적 모델)를 두고 교대한다.
- **정보이득 기준** — 다음 측정점은 정보이득(모델 불확실도·모델 간 예측 분산이
  최대인 곳)으로 선택. 베이지안 최적화.
- **다중 정밀도** — 정밀도 사다리(DFT 저비용 · 원자론 중간 · 실험 고비용).
  저비용 정밀도로 후보 영역을 좁히고 고비용 측정은 아껴 쓴다 — 비용 대비
  정보이득으로 정밀도를 선택.
- **미지 제약 처리** — 실현 가능 영역(박막 증착 공정 윈도우, 자석·저온장치
  사양 한계 등)을 캠페인 중 학습해, 사전 명시 없이도 비실현 조건을 회피한다.
- 산출 — 적응형 측정 계획. 각 측정 후 결과를 반영해 다음 조건을 갱신하고
  §13.5 ELN에 진행을 기록.

---

## 관련 모듈

- [`01-harness.md`](01-harness.md) — 스킬 자동 생성(§5.17)·실험코드 Ralph(Loop B)
- [`04-analysis.md`](04-analysis.md) — 측정 계획↔효과 레지스트리·교정·피팅
- [`07-literature.md`](07-literature.md) — 능동학습 DOE의 가설·문헌 근거
- [`../PLAN.md`](../PLAN.md) — 개요·아키텍처·로드맵
