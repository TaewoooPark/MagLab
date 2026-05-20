# MagLab 설계 — 학술 저술 & 커뮤니케이션 에이전트 스위트

> `PLAN.md`의 **§16** 상세. 전체 개요·색인은 [`../PLAN.md`](../PLAN.md).
> 본문의 `(§N)` 교차참조는 문서 전역 절 번호이며, 절↔파일 대응표는
> `../PLAN.md` 「문서 구성」 절에 있다.

---

## 16. 학술 저술 & 커뮤니케이션 에이전트 스위트 — `authoring/`

### 16.1 개념

검증된 결과 → 학술지 양식 논문 + 각종 학술 서신을 *전용 에이전트+스킬*로
작성. **AI가 초안, 사람이 저자.** 모든 산출물에 `HUMAN REVIEW REQUIRED` 표식.

### 16.2 학술지 템플릿

`templates/`에 양식별 최소 작동 `.tex` 프리앰블. 전체 표 = 부록 G.
figure는 §12 엔진이 저널 스타일 프로파일에 맞춰 공급.

| 출판사군 | 클래스 | 대상 저널 |
|---|---|---|
| Nature Portfolio | `sn-jnl` | Nature, Nature Physics/Materials/Nanotechnology/Electronics/Communications, npj Spintronics 등 |
| Science/AAAS | `scifile` | Science, Science Advances |
| APS | `revtex4-2` | PRL·PRB·PRX·PR Applied·PR Materials·RMP |
| AIP | `revtex4-2`(aip) | APL·JAP·APL Materials |
| IEEE | `IEEEtran` | IEEE Magnetics Letters·Trans. Magnetics |
| Elsevier | `elsarticle` | JMMM·Acta Materialia |
| Wiley | (Word/PDF) | Advanced Materials 계열 |

### 16.3 커뮤니케이션 에이전트 스위트

`authoring/comms/`의 *에이전트 + SKILL.md 스킬* 쌍:

| 에이전트/스킬 | 입력 | 산출 |
|---|---|---|
| `revision-letter` | 리뷰 결정문 + 원고(원/수정본) + 코멘트별 노트 + 톤 | 포인트별 응답 레터 — 코멘트 축자 인용 → 응답 → 변경 위치(쪽·줄) |
| `cover-letter` | 대상 저널·제목·핵심 결과·관련 게재 논문 | 250단어 커버 레터 |
| `academic-email` | 유형(협업/질문/면담/추천서/지원)·교수·관련 논문·용건 | 200단어 이하 메일 + 제목 + 후속, `[FILL]` 표식, 자동발송 없음 |
| `conference-abstract` | 학회명·결과 | 글자수 한계 내 초록 |
| `grant-text` | 기관·메커니즘(NSF·DOE)·specific aims | 양식별 섹션, 분량 강제 |
| `rebuttal` | 학회 리뷰 + 노트 | 1쪽 반박(기존 결과 명확화만) |

공통: 사용자 본인 결과·문장이 1차 입력, AI는 구조화·다듬기만 — 날조 금지.

### 16.4 인용 파이프라인 — cite-then-write

작성 *전* 후보 문헌 검색 → DOI·제목·저자 검증 → 검증된 `.bib`(`bibtexparser`
v2) → LLM은 검증 키만 인용 → 초안 후 `citation_auditor.py`가 전 `\cite{}`를
대조. **데이터 볼트**: 모든 정량 주장은 provenance의 잠긴 `DataPoint`에서만.

### 16.5 저술 Ralph 루프 (Loop C)

섹션 순서 Methods→Results→Discussion→Conclusion→Intro→Abstract→Title. 초안 →
도메인 인식 critic → 수정 → `tectonic` 컴파일 → PDF readback → 반복(max 6).
섹션마다 사람 사인오프. figure는 §12 엔진이 삽입. AI 사용 고지문 자동 첨부.

### 16.6 발표 자료 — 슬라이드·포스터

검증된 결과 → 학회 슬라이드·포스터 (`authoring/present/`). figure 엔진(§12)의
figure와 §16 저술의 서사를 활용한다.

- 슬라이드: 덱(beamer LaTeX / `python-pptx` / Marp 마크다운). 포스터: 대형 단일
  레이아웃(beamerposter / a0poster / SVG).
- UX: `maglab present slides "<결과>"` / `maglab present poster ...`. MagLab가
  구조화 덱을 초안(제목·동기·방법·결과[§12 figure]·결론). 연구자가 반복.
  포맷별 템플릿(APS March Meeting 12분 토크·세미나·A0 포스터).
- 무결성: figure는 figure 엔진(실데이터), 주장은 provenance — §17 honesty
  gate 동일 적용. 사람이 발표자·저자.

### 16.7 인용 의미 검증 — 지지 분류

§16.4의 cite-then-write를 *의미 수준*으로 강화한다. "인용이 존재하는가"를 넘어
"인용된 논문이 *실제로 이 주장을 뒷받침하는가*"를 검증한다.

- 생성 텍스트의 각 인용에 대해, 주장 문장 + 피인용 논문 전문을 대조해 **4분류**:
  지지 / 부분 지지 / 불지지 / 불확실 + 신뢰도(0–1).
- 근거 — 피인용 논문에서 지지·반박 증거 스니펫을 순위화해 제시(쪽·섹션 위치 포함).
- 불지지·불확실 인용은 §5.15 차단 게이트가 잡아 저술 진행을 막고 연구자에게
  표시한다. `citation_auditor`(§16.4)의 확장 — 존재 검증 → 의미 검증.

---

## 관련 모듈

- [`05-figure.md`](05-figure.md) — figure 엔진이 저널 스타일 figure 공급
- [`07-literature.md`](07-literature.md) — cite-then-write 인용 파이프라인·의미 검증
- [`08-review.md`](08-review.md) — 페르소나 리뷰 피드백 → 리비전
- [`10-integrity.md`](10-integrity.md) — 데이터 볼트·honesty gate
- [`../PLAN.md`](../PLAN.md) — 개요·아키텍처·로드맵
