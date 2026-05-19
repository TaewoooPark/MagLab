# 시뮬레이션

[매뉴얼 인덱스](index.md) · [English](../en/simulation.md)

이 모듈은 물질 파라미터에서 micromagnetic, DFT, atomistic, device scale의
simulation input/output으로 이동할 때 사용합니다.

## 설치

```sh
uv pip install -e ".[sim]"
```

OOMMF, MuMax3, magnum.np, VAMPIRE, VASP, Quantum ESPRESSO, HPC/GPU 실행 도구는
별도 설치가 필요할 수 있습니다.

## 명령

```sh
maglab sim micro --material Permalloy --nx 64 --ny 64 --nz 1 --cell-nm 4
maglab sim validate spec.json
maglab sim plot data.csv --journal nature --format pdf --output figure.pdf
maglab sim job

maglab sim dft --structure bcc_fe --engine qe --calc-type jij --output-dir runs/dft_fe
maglab sim atomistic --engine vampire --j-ij-k 398 --t-max-k 1300
maglab sim pipeline --structure bcc_fe --scales dft,atomistic,micro,device --backend mock
```

## workflow 패턴

**Micromagnetic 준비**

1. `mat show` 또는 `mat build`로 물질 파라미터를 확인합니다.
2. `physics compute exchange_length`로 mesh size 기준을 잡습니다.
3. micromagnetic spec을 만들고 검증합니다.
4. 선택한 backend를 실행하거나 생성된 spec을 handoff artifact로 사용합니다.

**Multiscale handoff**

1. exchange, MAE, DMI 추출을 위한 DFT 입력을 생성합니다.
2. DFT-derived parameter를 atomistic input으로 변환합니다.
3. atomistic run에서 temperature-dependent parameter를 추출합니다.
4. micromagnetic 또는 device-level analysis로 넘깁니다.

## Mock mode

몇몇 명령은 live solver 없이 mock path를 지원합니다. GPU/cluster 시간을 쓰기
전에 file generation, schema validation, provenance flow를 먼저 디버깅할 수
있습니다.

## 출력

Simulation 명령은 다음을 만들 수 있습니다.

- 외부 solver용 input directory.
- 파싱된 parameter record.
- warning과 validation error.
- 생성/파싱된 값의 provenance chain.
- quick-look plot과 FigureSpec-compatible artifact.

## 다음 단계

```sh
maglab analyze load simulation_output.csv
maglab figure spec --journal aps --kind xy
maglab device fom racetrack --j-drive 1e11 --alpha 0.01
```
