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
maglab sim doctor
maglab sim doctor --explain
maglab sim doctor --backend ssh-gpu --host gpu.cluster.edu --user alice
maglab sim doctor --backend ssh-hpc --host login.cluster.edu --user alice --probe-ssh

maglab sim micro --material Permalloy --nx 64 --ny 64 --nz 1 --cell-nm 4
maglab sim validate spec.json
maglab sim plot data.csv --journal nature --format pdf --output figure.pdf
maglab sim job

maglab sim dft --structure bcc_fe --engine qe --calc-type jij --output-dir runs/dft_fe
maglab sim atomistic --engine vampire --j-ij-k 398 --t-max-k 1300
maglab sim pipeline --structure bcc_fe --scales dft,atomistic,micro,device --backend mock
```

## 환경 진단

실제 solver, GPU, cluster 시간을 쓰기 전에 `maglab sim doctor`를 먼저
실행합니다. 이 명령은 MagLab의 Python simulation package, local solver
binary, GPU visibility, SSH/HPC utility, 현재 권장 backend를 한 번에
점검합니다.

doctor는 사람이 읽는 checklist와 자동화용 JSON 계약을 같이 제공합니다.
JSON에는 `backend_paths`가 들어 있고 각 path는 `status`, `next_command`,
`setup_commands`, note를 갖습니다. 즉 terminal 안에서 다음에 무엇을 해야
하는지 보여주되, 사용자가 요청하지 않은 SSH 연결이나 remote module 추정은
하지 않습니다.

`maglab sim doctor --explain`을 쓰면 no-GPU mock, local CPU fallback, local
GPU, SSH GPU, SSH HPC를 한 표로 분리해서 보여줍니다. 여러 실행 경로를 하나의
모호한 ready 상태로 뭉개지 않습니다.

실행 위치에 따라 다음처럼 사용합니다.

- GPU나 solver가 없는 노트북: `maglab sim pipeline --backend mock`으로 먼저
  workflow artifact와 provenance 흐름을 검증합니다.
- CPU fallback: `maglab[sim]`을 설치하고 mesh를 작게 유지한 뒤 doctor가
  `magnumnp` 같은 CPU engine을 감지하는지 확인합니다.
- Local GPU: MuMax3와 NVIDIA driver를 설치한 뒤 `mumax3`, `nvidia-smi`가
  모두 ready인지 확인합니다.
- SSH GPU/HPC: `--host`, `--user`를 넣고, terminal에서 SSH key가 동작하는
  것이 확인된 뒤에만 `--probe-ssh`를 붙입니다. 기본 doctor 명령은 원격
  연결을 열지 않습니다.

### 설정 흐름

**GPU 없는 노트북 / fresh install**

```sh
maglab sim doctor --backend auto
maglab sim pipeline --structure bcc_fe --scales dft,atomistic,micro,device --backend mock --json
```

mock pipeline은 work directory에 `pipeline_result.json`을 씁니다. 이 파일은
schema/provenance artifact이며, 실제 물리 solver 결과라고 주장하지 않습니다.

**Local CPU fallback**

```sh
pipx inject maglab "maglab[sim]"
maglab sim doctor --backend cpu
maglab sim micro --material Permalloy --nx 64 --ny 64 --nz 1 --cell-nm 4
```

**Local NVIDIA GPU**

```sh
mumax3 -h
nvidia-smi
maglab sim doctor --backend local-gpu
```

**SSH GPU / HPC**

```sh
maglab sim doctor --backend ssh-gpu --host gpu.cluster.edu --user alice
ssh alice@gpu.cluster.edu
maglab sim doctor --backend ssh-gpu --host gpu.cluster.edu --user alice --probe-ssh
```

HPC login node는 `--backend ssh-hpc`를 사용합니다. MagLab은
`--probe-ssh`가 있을 때만 SSH를 probe하며, local machine 상태만 보고 remote
CUDA, MuMax3, Slurm module availability를 추정하지 않습니다.

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
