# 연구노트와 계획

[매뉴얼 인덱스](index.md) · [English](../en/lab-planning.md)

MagLab이 실험 기록을 기억하고, 연구 목표를 measurement plan으로 바꾸게 하고
싶을 때 사용합니다.

## 명령

```sh
maglab lab note "Measured Pt/CoFeB/MgO Hall bar after anneal" --sample SOT-042 --instrument "PPMS" --type magnetotransport --tag anneal --tag hall
maglab lab note-list --sample SOT-042
maglab lab note-list --date-from 2026-05-01 --tag hall
maglab lab plan "SOT efficiency in Pt/CoFeB/MgO" --doe latin_hypercube --n-doe 16 --output sot_plan.yaml
```

## ELN entry

`maglab lab note`는 metadata가 포함된 구조화된 Markdown entry를 씁니다.

- Entry ID.
- Date.
- Sample.
- Instrument.
- Measurement type.
- Tags.
- Draft status.

아직 사람이 확인하지 않은 rough observation은 `--draft`로 표시하세요.

## Measurement planning

`maglab lab plan`은 research goal을 measurement step, geometry hint,
instrument hint, estimated hours, optional DOE point로 바꿉니다.

예시:

```sh
maglab lab plan "FMR damping in Py/Pt" --n-doe 12
maglab lab plan "temperature dependence of anomalous Hall in CoFeB" --doe full_factorial
```

## 실무 workflow

1. 실험 직후 바로 기록합니다.
2. sample ID와 tag를 일관되게 유지합니다.
3. instrument script 작성 전에 plan을 생성합니다.
4. note body에 output file과 provenance ID를 붙입니다.
5. 논문 작성이나 revision 때 note filter를 사용합니다.

## 다음 단계

```sh
maglab instr script "Keithley 2400" --description "measurement step from sot_plan.yaml"
maglab analyze load data/sot_042.csv
maglab write "Use ELN entries for sample SOT-042 and verified fit outputs..."
```
