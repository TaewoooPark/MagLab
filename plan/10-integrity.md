# MagLab 설계 — 정직한 리포팅 · Provenance · 무결성

> `PLAN.md`의 **§17** 상세. 전체 개요·색인은 [`../PLAN.md`](../PLAN.md).
> 본문의 `(§N)` 교차참조는 문서 전역 절 번호이며, 절↔파일 대응표는
> `../PLAN.md` 「문서 구성」 절에 있다.

---

## 17. 정직한 리포팅 · Provenance · 무결성

- **`DataPoint`** — `{value, units, uncertainty, provenance_type:
  enum{SIMULATED, MEASURED, THEORY, LITERATURE, FITTED}, source_ref,
  timestamp, conditions}`.
- **W3C PROV 감사 레이어** — 모든 Entity에 `wasGeneratedBy`·`wasDerivedFrom`·
  `wasAttributedTo`. LLM 호출도 1급 엔티티. figure도 엔티티(어떤 DataPoint에서
  렌더됐는지 기록). SQLite, JSON-LD 내보내기.
- **Honesty Gate** — 무태그 숫자·미검증 인용·페르소나 고지 누락·1인칭 귀속·
  데이터 볼트 밖 수치·**figure의 미태그 데이터**를 스캔해 산출 차단.
- 리포트·UI의 모든 수치에 `[SIM]`/`[MEAS]`/`[PRED]`/`[LIT]`/`[FIT]` 배지(§7.6).

---

## 관련 모듈

- [`01-harness.md`](01-harness.md) — honesty gate 능동 차단·promise-check(§5.15)
- [`04-analysis.md`](04-analysis.md) — `DataPoint`·교정·불확실도 예산(§11.6)
- [`09-authoring.md`](09-authoring.md) — 데이터 볼트·인용 의미 검증
- 전 모듈 — 모든 수치·인용·figure가 provenance를 거친다
- [`../PLAN.md`](../PLAN.md) — 개요·아키텍처·로드맵
