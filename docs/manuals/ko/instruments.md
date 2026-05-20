# 계측기

[매뉴얼 인덱스](index.md) · [English](../en/instruments.md)

실험 아이디어를 안전하고 검토 가능한 instrument workflow로 바꿔야 할 때
사용합니다. MagLab은 script를 생성하고 검사하지만, 실제 hardware execution은
연구자가 통제하는 Tier 3 action입니다.

## 설치

```sh
uv pip install -e ".[instr]"
```

## 명령

```sh
maglab instr scaffold "Keithley 2400" --iface GPIB --gpib-addr 24
maglab instr scpi "*IDN?" "SOUR:VOLT 0.1" "READ?"
maglab instr script "Keithley 2400" --description "field sweep Hall voltage measurement" --output hall_sweep.py
maglab instr check hall_sweep.py

maglab instr ingest "Keithley 2400" --manufacturer Keithley --manual-path manuals/keithley_2400.pdf
maglab instr skillgen "Keithley 2400" --manufacturer Keithley --safety-model keithley-2400
maglab instr implement "Measure Hall voltage while sweeping field" --instruments "Keithley 2400,Lakeshore 335"
```

## Safety model

Instrument 명령은 의도적으로 보수적으로 설계되어 있습니다.

- Instrument model name은 사용자가 확인해야 합니다.
- 생성된 script는 자동 실행되지 않습니다.
- hardware와 접촉하기 전 `maglab instr check`를 통과해야 합니다.
- SCPI sequence는 static inspection을 거칩니다.
- 생성 output에는 review warning이 포함됩니다.

## 일반적인 workflow

1. `instr ingest`로 instrument manual을 수집합니다.
2. `instr skillgen`으로 현재 workspace 전용 instrument skill을 생성합니다.
3. driver를 scaffold하거나 measurement script를 생성합니다.
4. 생성 script에 `instr check`를 실행합니다.
5. address, current/voltage/temperature limit, timing, shutdown을 검토합니다.
6. 실제 lab environment에 맞게 수정한 뒤 실행합니다.

## Manual RAG

Manual ingest는 PDF에서 local index를 만듭니다. instrument command name이나
safety constraint가 애매할 때 유용합니다.

```sh
maglab instr ingest "SR830" --manufacturer Stanford --manual-path manuals/sr830.pdf
maglab instr skillgen "SR830" --manufacturer Stanford
```

생성된 skill은 기본적으로 `.maglab/skills`에 저장됩니다. 따라서 전역 설치된
MagLab package를 수정하지 않고, 현재 연구 workspace와 함께 이동합니다.

## 다음 단계

```sh
maglab lab note "Generated first Hall sweep script" --instrument "Keithley 2400"
maglab lab plan "Hall measurement for anomalous Hall effect"
maglab analyze load measured_hall.csv
```
