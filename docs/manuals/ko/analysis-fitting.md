# 분석과 피팅

[매뉴얼 인덱스](index.md) · [English](../en/analysis-fitting.md)

측정 데이터나 시뮬레이션 데이터가 있고, 임시 notebook이 아니라 모델을 알고
있는 피팅이 필요할 때 사용합니다.

## 설치

```sh
uv pip install -e .
```

NumPy, SciPy, pandas, lmfit은 core dependency에 포함되어 있습니다.

## 명령

```sh
maglab analyze load data/stfmr.csv
maglab analyze model
maglab analyze model stfmr
maglab fit --effect stfmr data/stfmr.csv --method least_squares
maglab fit --discover --effect ordinary_hall data/hall.csv --init-grid '{"R_H":[-1e-10,0,1e-10]}'

maglab analyze consistency anomalous_hall ahe.csv ordinary_hall ohe.csv
maglab analyze symmetry 4/mmm
maglab analyze symmetry ignored --list

maglab device fom list
maglab device fom sot-mram --Ms 8e5 --t 2e-9 --Ku 4e5 --theta-sh 0.1
```

## 지원 작업

- CSV/HDF5 데이터를 로드하고 column summary를 출력합니다.
- effect model, required columns, parameter bounds, reference를 확인합니다.
- provider system을 통해 spintronic effect model을 피팅합니다.
- 알려진 effect model form 위에서 deterministic bilevel inner-loop discovery를
  실행하고, multi-start 초기값과 AIC/BIC를 확인합니다.
- 독립 fit 사이의 consistency를 확인합니다.
- symmetry-allowed tensor component를 확인합니다.
- SOT-MRAM, STT-MRAM, racetrack device의 figure of merit을 계산합니다.

## Effect family

Registry에는 AMR, AHE, ordinary Hall, planar Hall, SMR, USMR, GMR/TMR,
orbital Hall, topological Hall, FMR/Kittel, Gilbert damping, ST-FMR,
SOT harmonic Hall, spin pumping/ISHE, DMI, 1D domain-wall, macrospin/LLG,
Thiele/skyrmion dynamics, Curie temperature, hysteresis 모델이 포함됩니다.

## 데이터 준비

각 effect model은 required column을 선언합니다. 피팅 전에 확인하세요.

```sh
maglab analyze model EFFECT_NAME
```

그다음 CSV header를 모델에 맞춥니다. fit이 실패하면 다음을 확인합니다.

- Required columns.
- Unit consistency.
- Geometry JSON.
- Parameter bounds.
- Reduced chi-square와 warning.

## Discover mode

`maglab fit --discover`는 `plan/04-analysis.md`의 bilevel model discovery 중
결정론적 inner layer에 해당하는 CLI 진입점입니다. 현재 터미널 UX에서는 LLM이
방정식이나 숫자를 발명하게 두지 않습니다. 선택한 registered effect model을
model form으로 사용하고, deterministic initial-value candidate를 시도하며,
동일한 물리 parameter bound를 적용한 뒤 `chi2`, reduced `chi2`, AIC, BIC,
provenance를 출력합니다.

두 column짜리 effect model은 첫 required column을 `x`, 마지막 required
column을 `y`로 사용합니다. 더 복잡한 데이터에서는 `--x-col`, `--y-col`을
명시하세요.

## 다음 단계

```sh
maglab figure render fit_figure.json --datapoints fit_datapoints.json
maglab explain "ST-FMR symmetric component changes sign after annealing"
maglab write "Fit summary with provenance IDs..." --journal prl
```
