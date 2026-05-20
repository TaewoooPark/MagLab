# MagLab 설계 — 모델링·피팅 엔진 프로바이더

> `PLAN.md`의 **§11** 상세. 전체 개요·색인은 [`../PLAN.md`](../PLAN.md).
> 본문의 `(§N)` 교차참조는 문서 전역 절 번호이며, 절↔파일 대응표는
> `../PLAN.md` 「문서 구성」 절에 있다.

---

## 11. 모델링·피팅 엔진 프로바이더 — `analysis/`

> LLM 프로바이더·컴퓨트 백엔드와 나란한 **3번째 추상화**. 자성/스핀트로닉스가
> 다루는 모델(LLG 등)을 분야별 프로바이더로 묶고, 각 효과의 *정확한 피팅
> 포맷*을 코드로 보유한다.

### 11.1 프로바이더 아키텍처

`analysis/providers/`의 각 `ModelProvider`는 한 분야의 `EffectModel`들을 등록:

| 프로바이더 | 다루는 효과/모델 |
|---|---|
| `magnetotransport` | 일반 홀·이상 홀(AHE)·평면 홀(PHE)·토폴로지컬 홀(THE)·AMR·SMR·USMR·GMR/TMR |
| `spin_orbitronics` | SOT 하모닉 홀·ST-FMR·스핀 홀 각·**오비탈 홀(OHE)**·스핀 펌핑/ISHE |
| `ferromagnetic_resonance` | Kittel·Gilbert 댐핑·선폭·스핀혼합전도도 |
| `magnetization_dynamics` | LLG(+STT·+SOT)·매크로스핀·Walker·1D DW(q–Φ)·Thiele·2-부격자 LLG |
| `magnetometry` | 히스테리시스·포화/보자력·이방성·Curie/보상 온도 |
| `domain_walls_skyrmions` | DW 동역학·DMI·스커미온 안정성·스커미온 홀각 |

### 11.2 `EffectModel` 인터페이스

```
EffectModel = {
  name, subfield, references,
  parameters[]        # (이름, 단위, 경계)
  measurement_config  # 필요한 측정 기하·텐서 구조 (예: OHE = rank-3 텐서)
  forward(params, geometry) -> signal      # 정확한 함수형
  fit(data, geometry) -> FitResult(params, 불확실도, χ²)
  symmetry_constraints # 자기점군 허용 성분 (analysis/symmetry.py)
}
```

전체 모음 = **효과 피팅 레지스트리**. `maglab fit --effect anomalous_hall
data.csv` 식으로 호출. 플러그형. 공식·파라미터는 부록 F(구현 시 1차 문헌 확정).

### 11.3 효과 피팅 — 핵심 예시

- **이상 홀(AHE)**: `ρ_xy = R_0·B + μ₀·R_s·M(H)`; 메커니즘 판별은 Tian-Ye-Jin
  스케일링 `ρ_AHE = a·ρ_xx0 + b·ρ_xx²`.
- **SOT 하모닉 홀**: 1ω·2ω 각의존성으로 댐핑형·필드형 유효장 분리,
  `H_DL = (H_DL_raw − 2ξ·H_FL_raw)/(1−4ξ²)` PHE 보정.
- **ST-FMR**: `V_mix = S·F_sym(H) + A·F_asym(H)`, S/A 비로 스핀 홀 각.
- **오비탈 홀 효과 (OHE).** 오비탈 홀 전도도는 전하 홀(2-인덱스)과 달리
  **rank-3 텐서** `σ^{l_γ}_{α,β}` — α=전류 방향, β=가로 방향, γ=궤도 각운동량
  편극 방향. 각운동량은 벡터라 2-인덱스 처리로는 부족하다. `EffectModel`이
  `sigma_OH[α][β][γ]`(3×3×3)를 보유, `θ_OH = σ_OH/σ_xx`.

### 11.4 효과 피팅 개선 Ralph 루프 (Loop D)

피팅 → `oracle`로 잔차·물리 경계·차원 검사 → 비물리/미수렴이면 모델·초기값·
경계 조정 → 재피팅. 수렴·물리 타당까지 반복(서킷 브레이커 적용).

### 11.5 스핀트로닉스 연구자 특화 도구

대칭 분석기 · 스핀 홀 각 교차검증 · AHE/THE/OHE 분해 · FMR 스위트 · DMI 추출 ·
스택 표기 파서 · 측정 플래너 · 단위·규약 체커 · Hall bar 기하 계수 · figure
재현 · 임계지수 스케일링.

### 11.6 교정·계통오차·불확실도 예산

피팅·데이터 분석의 신뢰성 레이어 (`analysis/calibration.py`). 측정값을 그대로
피팅하지 않고, 교정·계통보정을 거친 뒤 불확실도를 전파한다.

- **교정 레지스트리** — 장비·측정 교정 인자를 날짜·유효기간과 함께 저장.
- **계통 보정 파이프라인** — 선언적 보정 단계(배경 차감·오프셋 제거·드리프트
  보정·Hall 데이터 반대칭화 등). 각 보정은 추적·provenance 기록되는 변환이며
  피팅 전 적용. 가역·명시적 — 연구자가 raw→corrected 변환을 본다.
- **불확실도 예산** — 분석 체인 전체 불확실도 전파(측정 + 교정 + 피팅
  불확실도) → GUM식 error budget 표. 최종 `DataPoint` 불확실도가 전체 예산을
  반영하므로 피팅 공분산만이 아닌 *정직한* 오차가 보고된다.
- UX: 보정은 명시적·가역적, error budget 표는 자동 생성·표시.

### 11.7 소자 성능 지표(FoM) 추정

스핀트로닉스 소자 설계 + 물질 파라미터 → 소자 figures of merit
(`analysis/device_fom.py`). 효과 피팅 레지스트리(§11.1)와 평행한 "소자 FoM
레지스트리".

- 소자: SOT-MRAM·STT-MRAM·racetrack·스핀-오비트 로직·MTJ·스핀밸브 센서·마그논.
- FoM: 스위칭 전류/에너지, write error rate(WER), 열 안정성 Δ=E_b/k_BT
  (retention), read margin(TMR 기반), endurance, 스위칭 속도, racetrack DW
  속도, 전력.
- 입력: 소자 기하 + 물질 파라미터(§11 효과 모델·§9 물질 DB·§10 시뮬에서).
  각 FoM = 출처 있는 등록 공식(부록 F식 — 구현 시 1차 문헌으로 확정).
- UX: `maglab device fom <소자-스펙>` → FoM 표 — 각 지표·사용 공식·입력·
  불확실도, + 벤치마크/타깃 대비(상용 MRAM·IRDS 타깃). 자기 소자의 위치를 한눈에.

### 11.8 이론↔시뮬 bilevel 모델 발견 루프

효과 피팅(§11.1–3)은 *알려진* 모델에 데이터를 맞춘다. 이 루프는 *새 모델 형태*
자체를 발견한다 — 2층(bilevel) 최적화다.

- **바깥 층 (LLM · 이산)** — LLM이 모델의 *형태·구조*를 제안한다: 새 스핀
  해밀토니안 항, 자기 이방성 에너지 함수형, 교환 상호작용 형태, 효과 피팅식의
  새 항. LLM은 *구조*만 제안하고 수치는 만들지 않는다.
- **안쪽 층 (결정론 · 연속)** — 제안된 형태의 *연속 파라미터*를 시뮬레이션
  (원자론/미세자기) 또는 피팅으로 데이터·시뮬 타깃에 최적화한다.
- **피드백** — 안쪽 층의 잔차·예측력·물리 타당성(`oracle`)·단순성(파라미터 수)을
  메트릭으로 바깥 층 LLM이 형태를 수정. 수렴 또는 서킷 브레이커까지 반복.
- **산출** — 새 모델 형태 + 피팅 파라미터 + provenance(어떤 데이터·시뮬로
  검증). 검증되면 §11 효과 레지스트리에 새 `EffectModel`로 등록된다.
- **무결성** — 발견된 모델은 "LLM이 형태 제안, 결정론 층이 파라미터 검증"으로
  라벨. 용도: 기존 모델로 설명 안 되는 이상 데이터(§5.11)에 새 항이 필요할 때.

---

## 관련 모듈

- [`03-physics-simulation.md`](03-physics-simulation.md) — 시뮬·물질 파라미터가 피팅 입력
- [`05-figure.md`](05-figure.md) — 피팅·분석 결과의 데이터플롯
- [`06-experiment.md`](06-experiment.md) — `measurement_config` 역참조로 측정 계획·교정
- [`10-integrity.md`](10-integrity.md) — 피팅 결과 `DataPoint`·불확실도 예산
- [`../PLAN.md`](../PLAN.md) — 개요·아키텍처·로드맵
