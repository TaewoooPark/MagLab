# 그림

[매뉴얼 인덱스](index.md) · [English](../en/figures.md)

그림이 단순한 이미지가 아니라 data-bound, journal-aware, vector-exportable,
inspectable research artifact가 되어야 할 때 사용합니다.

## 설치

```sh
uv pip install -e ".[figure]"
```

## 명령

```sh
maglab figure primitives list
maglab figure primitives show hall-bar

maglab figure spec --journal nature --kind hysteresis --output figspec.json
maglab figure render figspec.json --datapoints datapoints.json --output figure.pdf
maglab figure compose multipanel.json --output multipanel.svg --format svg
maglab figure export multipanel.json --output figures/panel --format pdf --format svg

maglab sim plot data.csv --journal aps --format pdf --output data_plot.pdf
```

## FigureSpec workflow

1. `FigureSpec` JSON을 만들거나 수정합니다.
2. spec을 `DataPoint` record에 연결합니다.
3. 로컬에서 렌더링하고 결과를 확인합니다.
4. journal-ready vector format으로 export합니다.
5. spec을 manuscript 또는 data directory 옆에 보관합니다.

## Primitive catalog

Schematic catalog에는 Hall bar, MTJ pillar, multilayer stack, Bloch/Neel
domain wall, skyrmion, LLG precession, coordinate axes, measurement geometry,
spin-texture color wheel 같은 primitive가 포함됩니다.

같은 schematic을 매번 새로 그리지 않기 위해 catalog를 사용합니다.

```sh
maglab figure primitives list --search skyrmion
maglab figure primitives show skyrmion-bloch
```

## Journal style

APS, Nature, IEEE, Elsevier 같은 journal profile을 지원합니다. 다만 최종 font
size, label, export requirement는 항상 target journal guideline과 대조해야
합니다.

## 다음 단계

```sh
maglab write "Results with FigureSpec path figures/figspec.json"
maglab present templates
maglab present slides "Use figures/stfmr.pdf and figures/device.svg"
maglab present poster "Use verified figure exports from figures/"
```
