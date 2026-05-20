# MagLab 구현 — 검증 전략 · 골든값 · CI

> 설계 근거: PLAN.md §20 테스트/검증 · §3 설계 원칙 · plan/11-appendices.md 부록 D
> 횡단 문서 — 각 Phase의 `PX.4 검증 게이트`가 따르는 공통 검증 체계.
> 규약: impl/README.md

## 1. 검증 철학 (§3 · §20)

MagLab은 **검증 가능한 오케스트레이터**다. 검증도 같은 원칙을 따른다 —
**결정론 우선**, LLM 판단은 비정량 영역에 한정.

**LLM-as-judge 금지 영역 (절대)**:
- 수치 정확도 — 시뮬·물리식·계산 결과.
- 인용 — 존재·DOI·의미 지지 여부.
- 피팅 — 파라미터 복원·χ²·불확실도.
- figure 데이터 일치 — 플롯 값이 입력 데이터와 같은가.

**LLM 판단 허용 (보조, 비정량)**:
- 서술 텍스트 명료성·구조(저술 critic §16.5).
- figure 비전 critic — 축 라벨 유무·가독성·패널 라벨(§12.5 Loop E). **단,
  데이터-출처 일치는 결정론 검사**(figure는 코드가 실데이터로 렌더).

원칙: 검증 게이트가 결정론으로 통과/실패를 내고, LLM은 *제안*만 한다.

## 2. 테스트 계층

`tests/` 하위에 계층별 디렉터리를 둔다(`00-foundation.md` T-F-09).

| 계층 | 디렉터리 | 대상 | 도입 Phase |
|---|---|---|---|
| 단위 | `tests/unit/` | 결정론 함수 — `units`·`oracle`·`formulas`·`EffectModel.forward` | P0~ |
| 골든값 | `tests/golden/` | 외부 기준 재현 — µMAG·VAMPIRE·문헌값 | P0~ |
| 라운드트립 | `tests/golden/fitting/` | 합성 데이터 → 피팅 파라미터 복원 | P2~ |
| 통합 | `tests/integration/` | 파이프라인 — `gen→validate→run→parse→fit`·핸드오프 | P1~ |
| 무결성 | `tests/integrity/` | honesty gate·인용 주입·promise-check·figure 미태그 | P0~ |
| 스모크 | `tests/smoke/` | CLI·MCP·게이트웨이 기동 | P0~ |
| 하네스 eval | `tests/harness/` | 서브에이전트·라우팅·Ralph 서킷 브레이커 | P0~ |
| UI | `tests/ui/` | 배너 반응형·`NO_COLOR`·비-TTY·테마 로드 | P0~ |

테스트는 **네트워크·하드웨어·실제 LLM에 의존하지 않는다** — 외부 호출은
캐시·VCR·mock로 결정론화(§8).

## 3. 골든값 데이터셋 — 출처 · 획득

| 데이터셋 | 용도 | Phase | 출처 / 생성법 |
|---|---|---|---|
| µMAG 표준문제 #1–#5 | 미세자기 솔버 검증 | P1 | NIST µMAG 공개 명세·참조 해답을 `tests/golden/data/mumag/`에 픽스처로 적재 |
| VAMPIRE bcc Fe `T_C` | 원자론 검증 | P3 | VAMPIRE 예제·문헌의 `T_C`(≈1043 K) 기대 범위 |
| `formulas.py` 문헌값 | 물리 코어 검증 | P0 | CODATA + 1차 문헌(교환 길이·DW 폭·Walker 장 등) |
| 효과 피팅 합성 데이터 | `EffectModel` 라운드트립 | P2 | **in-repo 생성** — 효과의 `forward()`로 알려진 파라미터+노이즈 데이터 생성 → `fit()`이 복원 검증 |
| 핸드오프 골든값 | 스케일 변환 검증 | P3 | 스케일 N 출력 → N+1 입력 단위·차원 기대표(부록 D) |
| 인용 주입 픽스처 | 무결성 검증 | P0~P6 | 가짜 DOI·미존재 논문·불지지 인용 픽스처를 `tests/integrity/data/`에 |
| 장비 SCPI 안전 케이스 | 안전 검증 | P4 | 한계 초과·순서 위반 명령 픽스처 |

골든 데이터는 git에 커밋(`.gitignore`가 제외하지 않음). 외부 명세 데이터는
출처·라이선스를 `tests/golden/data/<set>/SOURCE.md`에 기록.

## 4. Phase별 검증 게이트 (요약)

각 Phase 문서 `PX.4`의 종료 기준을 모은 표 — §19 로드맵 종료 기준에 직결.

| Phase | §19 종료 기준 | 핵심 테스트 |
|---|---|---|
| Foundation | `pip install -e .` 성공·`maglab --help` | 코어 설치·import·스텁 lint/type |
| **P0** | Mac에서 GPU 없이 동작·볼드 블록 배너·golden-value 통과 | `formulas` 골든값·UI 배너 3단·인증 3 백엔드 스모크·honesty gate·CLI/MCP 스모크·하네스 eval |
| **P1** | µMAG 표준문제 #1–#5 재현·저널 스타일 벡터 figure | µMAG #1–5 골든값·데이터플롯 값 일치·벡터/폰트 임베딩·저널 치수 |
| **P2** | AHE·SMR·하모닉 홀·ST-FMR·FMR·OHE 합성 데이터 피팅 | 효과별 라운드트립 복원(부록 F 전수)·OHE rank-3 텐서·대칭 제약 |
| **P3** | bcc Fe `T_C`·핸드오프 골든값·스커미온 시각화 | VAMPIRE `T_C`·핸드오프 단위/차원·`simviz` HSL 컬러휠 렌더 |
| **P4** | 매뉴얼→스킬·실험코드 Ralph·자성 스키매틱 figure | 스킬 A/B 평가·Ralph 서킷 브레이커·재개·SCPI 안전 envelope·SVG→PDF·Loop E critic |
| **P5** | 키워드 검색·임팩트·물질DB·페르소나 리뷰 | 키워드 추출·임팩트 메트릭 라벨링·물질 DataPoint·페르소나 7대 안전장치·retraction |
| **P6** | `maglab write`·리비전/메일·Slack/Telegram/Discord 연동 | cite-then-write·인용 의미 4분류·데이터 볼트 차단 게이트·게이트웨이 스모크 |

## 5. CI 파이프라인

`.github/workflows/ci.yml`(T-F-11) — **게이트는 순서대로, 하나라도 실패 시
머지 차단**.

```
lint(ruff) → type(mypy) → unit → golden → integrity → smoke → integration
```

- **matrix**: macOS·Linux × Python 3.11·3.12.
- **코어 설치 검증**: extras 없이 `import maglab`·`maglab --help` 동작(§18
  "코어 설치는 GPU·LLM 없이" 회귀 방지).
- **점진 성장**: Phase 머지 때마다 그 Phase의 골든 잡을 CI에 추가 —
  P1 머지 → µMAG 잡, P2 → 효과 피팅 라운드트립 잡, P3 → 핸드오프·`T_C` 잡 등.
- **외부 솔버 부재 대응**: CI 러너에 시뮬 바이너리·실 LLM이 없으므로 P1·P3
  시뮬 테스트는 골든 픽스처·mock 백엔드로 실행. 실 솔버 검증은 로컬·HPC에서.
- **느린 잡 분리**: 임베딩·RAG 등 무거운 통합 테스트는 `nightly` 워크플로로.

## 6. 무결성 테스트 상세 (§17 · §5.15)

`tests/integrity/` — honesty gate가 *실제로 차단*하는지 단언한다.

- [ ] **무태그 수치 차단** — `provenance_type` 없는 숫자가 산출에 들어가면 차단.
- [ ] **인용 주입 탐지** — 가짜 DOI·미존재 논문·LLM 환각 인용 픽스처를
  `citation_auditor`가 탐지(§16.4). 주입 케이스 전수 차단.
- [ ] **인용 의미 검증** — 불지지·불확실 인용(§16.7 4분류)을 차단 게이트가
  잡아 저술 진행 정지(경고 아닌 정지, §5.15).
- [ ] **데이터 볼트** — 데이터 볼트 밖 수치를 쓴 저술 산출 차단.
- [ ] **figure 미태그 데이터** — `DataPoint`에 바인딩되지 않은 데이터를 담은
  figure 생성 차단(§12.6).
- [ ] **페르소나 고지** — 리뷰어 출력에 고지 라벨 누락·1인칭 귀속 시 차단(§15.2).
- [ ] **promise-check** — 에이전트가 "X를 실행/기억했다"는 *주장*을 실제 도구
  호출 로그·provenance와 대조, 불일치 시 플래그(§5.15).

## 7. 도메인 안전 테스트

- [ ] **SCPI 안전 envelope**(P4) — 하드웨어 한계 초과·순서 위반 SCPI 명령을
  `safety.py`가 정적 거부(§13.1, 부록 D).
- [ ] **핸드오프 단위/차원**(P3) — 스케일 N 출력 단위 ≠ N+1 입력 단위면 검증
  차단(부록 D).
- [ ] **효과 피팅 경계**(P2) — 텐서 rank 불일치·파라미터 물리 경계 위반 거부.
- [ ] **`oracle` 경계**(P0) — 비물리 결과(α>1·M>M_s·T≤0 등) 거부.
- [ ] **Ralph 서킷 브레이커**(P4) — 3회 무진전·동일오류 5회·출력 유사도
  >0.95·비용 초과 시 중단·에스컬레이션(§6.2).

## 8. 검증 안티패턴 — 하지 말 것

- LLM-as-judge로 수치·인용·피팅 채점 — **금지**(§1).
- figure를 픽셀 비교로 검증 — **금지**. 입력 데이터 대비 *값*을 검증.
- 실제 하드웨어 VISA 세션 — **금지**. `mock.py` 가상 계측기만(§13.1).
- 실제 LLM·학술 API에 의존하는 테스트 — **금지**. 캐시·VCR·mock로 결정론화.
- 골든값을 코드가 산출한 값으로 갱신 — **금지**(외부 기준만이 골든의 출처).
- 테스트 과적합 — 스킬 A/B 평가는 트리거 쿼리를 일반화해 평가(§5.17).

## 관련 문서

- 테스트 인프라 구축: [`00-foundation.md`](00-foundation.md) T-F-09·T-F-11
- 도구·패키지: [`08-skills-and-tools.md`](08-skills-and-tools.md)
- Phase별 게이트 상세: `01`~`07` Phase 문서의 `PX.4` 절
- 설계: [`../PLAN.md`](../PLAN.md) §20 · [`../plan/11-appendices.md`](../plan/11-appendices.md) 부록 D
