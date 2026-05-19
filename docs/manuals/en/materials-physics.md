# Materials and Physics

[Manual index](index.md) · [한국어](../ko/materials-physics.md)

This is the deterministic core of MagLab. Use it when you need material
parameters, SI-safe quantities, unit conversion, formula evaluation, or basic
physical plausibility checks before simulation or fitting.

## What It Does

- Lists and shows curated magnetic materials.
- Builds layer-stack property tables from stack strings.
- Computes common magnetism and spintronics formulae.
- Converts magnetic units.
- Runs the physics oracle on user-provided parameters.

## Commands

```sh
maglab mat list
maglab mat show Permalloy
maglab mat build "Ta(5)/CoFeB(1)/MgO(2)"

maglab physics compute exchange_length A=13e-12 Ms=860e3
maglab physics compute bloch_wall_width A=13e-12 K=5e4
maglab physics units 1000 Oe T
maglab physics oracle alpha=0.01 Ms=860000 T=300
```

## Recommended Workflow

1. Start with `maglab mat show <material>` or `maglab mat build <stack>`.
2. Convert all incoming quantities to SI units.
3. Run `maglab physics oracle` before simulation, fitting, or reporting.
4. Use the returned values as inputs to `sim`, `fit`, `device`, and `figure`.

## Data Contract

MagLab's physics layer is built around typed quantities and `DataPoint` records.
When a result moves into downstream workflows, keep its source, unit, and
provenance attached. The point is not just to compute a number but to know where
the number came from.

## Common Use Cases

**Check a proposed material parameter set**

```sh
maglab physics oracle Ms=800000 A=13e-12 alpha=0.008 T=300
```

**Compute a scale before choosing mesh size**

```sh
maglab physics compute exchange_length A=13e-12 Ms=860e3
```

**Build a stack before planning measurements**

```sh
maglab mat build "Pt(4)/CoFeB(1.2)/MgO(2)" --save
```

## Handoff

Use the checked parameters in:

```sh
maglab sim micro --material Permalloy --cell-nm 4
maglab device fom sot-mram --Ms 8e5 --t 2e-9 --Ku 4e5
maglab lab plan "FMR damping in Py/Pt"
```
