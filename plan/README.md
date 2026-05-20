# MagLab 설계 계획서 — `plan/` 모듈 상세

이 디렉터리는 MagLab(자성·스핀트로닉스 연구 생애주기 코파일럿, 독립 CLI
에이전트) 설계 계획서의 **모듈별 상세 설계 문서**다. 최상위 개요·아키텍처·
로드맵은 상위 [`../PLAN.md`](../PLAN.md)에 있다.

## 읽는 순서

1. **먼저 [`../PLAN.md`](../PLAN.md)** — 메타·배경·제품 정의·설계 원칙·시스템
   아키텍처·기술 스택·로드맵·테스트·리스크. 전체 그림을 잡는다.
2. 그다음 아래 모듈 파일 중 작업 대상을 연다.

## 파일 구성

| 파일 | 절 | 내용 |
|---|---|---|
| [`01-harness.md`](01-harness.md) | §5–§6 | 에이전트 하네스·오케스트레이션 · 서브에이전트·스킬·MCP 디자인(§5.16–§5.18) · Ralph 루프 |
| [`02-delivery.md`](02-delivery.md) | §7–§8 | 전달·인증·CLI 디자인 · 메시징 게이트웨이 |
| [`03-physics-simulation.md`](03-physics-simulation.md) | §9–§10 | 결정론적 물리 코어 · 멀티스케일 시뮬레이션 |
| [`04-analysis.md`](04-analysis.md) | §11 | 모델링·피팅 엔진 프로바이더 · 효과 피팅 레지스트리 |
| [`05-figure.md`](05-figure.md) | §12 | Figure 제작 엔진 |
| [`06-experiment.md`](06-experiment.md) | §13 | 실험 워크플로 — 장비 코드·ELN·측정 계획 |
| [`07-literature.md`](07-literature.md) | §14 | 문헌·발견 인텔리전스 · 논문검색 MCP·리서치 오케스트레이션(§14.7) |
| [`08-review.md`](08-review.md) | §15 | 원고 리뷰 — 전문가 페르소나 패널 |
| [`09-authoring.md`](09-authoring.md) | §16 | 학술 저술·커뮤니케이션 에이전트 스위트 |
| [`10-integrity.md`](10-integrity.md) | §17 | 정직한 리포팅·Provenance·무결성 |
| [`11-appendices.md`](11-appendices.md) | 부록 A–J | CLI 트리·MCP/스킬 카탈로그·정적검증·기능 매핑·효과 레지스트리·저널 템플릿·하네스 패턴·용어집·참고자료 |

## 규약

- **절 번호 §N은 문서 전역에서 고유**하다. 파일이 분리돼도 번호는 바뀌지 않으므로,
  어느 파일에서든 본문의 `(§N)` 교차참조가 그대로 유효하다. 절↔파일 대응은 위 표
  또는 [`../PLAN.md`](../PLAN.md)의 「문서 구성」 절로 찾는다.
- 각 모듈 파일 끝의 **「관련 모듈」** 절에 인접 파일로의 링크가 있다.
- 본 문서군은 **구현 명세서**다 — 코드는 별도 세션에서 Phase(P0–P6, §19) 단위로
  작성한다. 본 세션들은 문서만 작성하고 코드는 생성하지 않았다.

## 구현 착수 시

[`../PLAN.md`](../PLAN.md) §19 로드맵의 Phase 순서를 따른다. **부록 E**(핵심
기능 → 구현 매핑)와 **부록 F**(효과 피팅 레지스트리)가 착수 체크리스트다 —
둘 다 [`11-appendices.md`](11-appendices.md)에 있다.

- **P0 코어** — [`01-harness.md`](01-harness.md)(하네스·서브에이전트·스킬·MCP) +
  [`02-delivery.md`](02-delivery.md)(CLI·인증) + [`03-physics-simulation.md`](03-physics-simulation.md)의 물리 코어.
- 이후 P1–P6은 figure·analysis·시뮬 멀티스케일·instrument·literature·reviewer·
  authoring 순으로 모듈을 채운다.
