# Figures

[Manual index](index.md) · [한국어](../ko/figures.md)

Use this module when a figure needs to be a reproducible research artifact:
data-bound, journal-aware, vector-exportable, and inspectable.

## Install

```sh
uv pip install -e ".[figure]"
```

## Commands

```sh
maglab figure primitives list
maglab figure primitives show hall-bar

maglab figure spec --journal nature --kind hysteresis --output figspec.json
maglab figure render figspec.json --datapoints datapoints.json --output figure.pdf
maglab figure compose multipanel.json --output multipanel.svg --format svg
maglab figure export multipanel.json --output figures/panel --format pdf --format svg

maglab sim plot data.csv --journal aps --format pdf --output data_plot.pdf
```

## FigureSpec Workflow

1. Create or edit a `FigureSpec` JSON.
2. Bind the spec to `DataPoint` records.
3. Render locally and inspect the output.
4. Export journal-ready vector formats.
5. Keep the spec next to the manuscript or data directory.

## Primitive Catalog

The schematic catalog contains reusable spintronics and magnetism primitives:
Hall bars, MTJ pillars, multilayer stacks, Bloch and Neel domain walls,
skyrmions, LLG precession, coordinate axes, measurement geometries, and
spin-texture color wheels.

Use the catalog to avoid redrawing the same schematic from scratch:

```sh
maglab figure primitives list --search skyrmion
maglab figure primitives show skyrmion-bloch
```

## Journal Styles

Figure rendering supports journal profiles such as APS, Nature, IEEE, and
Elsevier. These profiles should be treated as starting points: verify final
font sizes, labels, and export requirements against the target journal.

## Handoff

Figures are usually consumed by:

```sh
maglab write "Results with FigureSpec path figures/figspec.json"
maglab present slides "Use figures/stfmr.pdf and figures/device.svg"
maglab present poster "Use verified figure exports from figures/"
```
