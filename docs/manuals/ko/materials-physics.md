# 물질과 물리

[매뉴얼 인덱스](index.md) · [English](../en/materials-physics.md)

이 모듈은 MagLab의 deterministic core입니다. 물질 파라미터, SI-safe quantity,
단위 변환, 공식 계산, 기본 물리 plausibility check가 필요할 때 사용합니다.

## 하는 일

- curated magnetic material을 list/show합니다.
- layer stack string에서 property table을 만듭니다.
- 자성/스핀트로닉스의 공통 공식을 계산합니다.
- 자기 단위를 변환합니다.
- 사용자가 준 파라미터에 대해 physics oracle을 실행합니다.

## 명령

```sh
maglab mat list
maglab mat show Permalloy
maglab mat build "Ta(5)/CoFeB(1)/MgO(2)"

maglab physics compute exchange_length A=13e-12 Ms=860e3
maglab physics compute bloch_wall_width A=13e-12 K=5e4
maglab physics units 1000 Oe T
maglab physics oracle alpha=0.01 Ms=860000 T=300
```

## 추천 workflow

1. `maglab mat show <material>` 또는 `maglab mat build <stack>`으로 시작합니다.
2. 모든 입력 quantity를 SI 단위로 정리합니다.
3. simulation, fitting, reporting 전에 `maglab physics oracle`을 실행합니다.
4. 반환된 값을 `sim`, `fit`, `device`, `figure`의 입력으로 사용합니다.

## 데이터 계약

MagLab의 physics layer는 typed quantity와 `DataPoint` record를 중심으로
구성됩니다. 값이 downstream workflow로 넘어갈 때 source, unit, provenance를
함께 유지하세요. 중요한 것은 숫자를 계산하는 것만이 아니라 그 숫자의 출처를
알 수 있게 만드는 것입니다.

## 자주 쓰는 예시

**제안한 물질 파라미터 체크**

```sh
maglab physics oracle Ms=800000 A=13e-12 alpha=0.008 T=300
```

**mesh size 선택 전 length scale 계산**

```sh
maglab physics compute exchange_length A=13e-12 Ms=860e3
```

**측정 계획 전 stack 구성**

```sh
maglab mat build "Pt(4)/CoFeB(1.2)/MgO(2)" --save
```

## 다음 단계

```sh
maglab sim micro --material Permalloy --cell-nm 4
maglab device fom sot-mram --Ms 8e5 --t 2e-9 --Ku 4e5
maglab lab plan "FMR damping in Py/Pt"
```
