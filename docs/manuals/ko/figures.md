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
maglab figure primitives ingest schematics/sot-loop.svg \
  --name sot-loop --description "Spin-orbit torque loop schematic." --tag SOT

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

## Primitive ingestion

기본 catalog에 없는 schematic이 필요하면 manuscript에 임시 artwork를 붙이지
말고, 먼저 로컬 SVG 또는 JSON descriptor를 workspace review package로
ingest합니다. 결정론적 ingestion core는 다음 파일을 만듭니다.

- `.maglab/figure/primitives/catalog/<name>/PRIMITIVE.md`
- `.maglab/figure/primitives/catalog/<name>/primitive.json`
- `.maglab/figure/primitives/catalog/<name>/preview.svg`
- `.maglab/figure/primitives/catalog/<name>/quality.json`
- `.maglab/figure/primitives/catalog/<name>/REVIEW.md`

CLI 사용:

```sh
maglab figure primitives ingest schematics/sot-loop.svg \
  --name sot-loop \
  --category concept/process \
  --description "Spin-orbit torque loop schematic." \
  --tag SOT \
  --tag torque
```

자동화가 필요하면 Python API도 사용할 수 있습니다.

```python
from maglab.figure.primitives import ingest_primitive

result = ingest_primitive(
    "schematics/sot-loop.svg",
    metadata={
        "category": "concept/process",
        "tags": ["SOT", "torque"],
        "description": "Spin-orbit torque loop schematic.",
        "physics_convention": "Current along x; spin accumulation along y.",
        "references": ["doi:10.1038/nnano.2013.243"],
    },
)
print(result.status)
print(result.review_md)
```

JSON descriptor는 `svg` 또는 `svg_path`와 함께 `name`, `category`, `tags`,
`parameters`, `physics_convention`, `references`, `journal_styles` 같은
metadata를 줄 수 있습니다. Ingestion은 descriptor code를 실행하지 않고,
vector material copy, metadata normalization, quality check 기록만 수행합니다.
검사 항목에는 SVG parse, deterministic dimension, embedded raster, external
link, parameterization, reference, physics convention completeness가 포함됩니다.

`ready_for_promotion`은 자동으로 내장 catalog에 설치된다는 뜻이 아니라 review가
통과되어 승격 가능하다는 뜻입니다. 실제 승격에는 `primitive.py` 구현과 test가
필요합니다.

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
