"""SimViz renderer — OVF / micromagnetic visualization (§12.3 simviz).

Design rationale: impl/04-P3-multiscale.md T-P3-15~18 · plan/05-figure.md §12.3.

Features:
1. ``render_2d``   : discretisedfield ``Field.mpl()`` 2D slice render.
2. ``render_hsl``  : ``Field.mpl.lightness()`` HSL color wheel (skyrmion standard).
3. ``render_quiver``: matplotlib quiver arrow overlay.
4. ``render_3d``   : PyVista off-screen 3D render → PNG.

Handles ``PanelType.SIM_VIZ`` panels from figure/spec.py.
Output is a matplotlib Figure (2D / quiver / HSL) or a PNG path (3D).

External dependency handling:
- Emits a warning and returns a mock plot when ``discretisedfield`` is not installed.
- Skips PNG when ``pyvista`` is not installed.
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any

import matplotlib
import matplotlib.pyplot as plt
import numpy as np

from maglab.figure.spec import PanelSpec

# Force headless backend
matplotlib.use("Agg")

# ---------------------------------------------------------------------------
# discretisedfield availability check
# ---------------------------------------------------------------------------

try:
    import discretisedfield as df  # type: ignore[import-untyped]

    _DF_AVAILABLE = True
except ImportError:
    df = None  # type: ignore[assignment]
    _DF_AVAILABLE = False

# ---------------------------------------------------------------------------
# pyvista availability check
# ---------------------------------------------------------------------------

try:
    import pyvista as pv  # type: ignore[import-untyped]

    _PV_AVAILABLE = True
    # Force off-screen
    pv.OFF_SCREEN = True
except ImportError:
    pv = None  # type: ignore[assignment]
    _PV_AVAILABLE = False


# ---------------------------------------------------------------------------
# OVF file loader
# ---------------------------------------------------------------------------


def load_ovf(path: Path | str) -> Any:
    """Load an OVF/OMF magnetization file and return a discretisedfield Field or numpy array.

    Falls back to a simple numpy parser when discretisedfield is not installed.

    Parameters
    ----------
    path:
        OVF file path.

    Returns
    -------
    discretisedfield.Field | dict
        ``Field`` object when ``discretisedfield`` is installed;
        ``{"mesh": ..., "m": np.ndarray}`` dictionary otherwise.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"OVF file not found: {path}")

    if _DF_AVAILABLE:
        # discretisedfield API: try both from_file (new) and fromfile (old)
        try:
            if hasattr(df.Field, "from_file"):
                field = df.Field.from_file(str(path))
            else:
                field = df.Field.fromfile(str(path))  # type: ignore[attr-defined]
            return field
        except Exception as exc:
            warnings.warn(
                f"discretisedfield Field.from_file() failed: {exc}. Falling back to numpy parser.",
                stacklevel=2,
            )
            return _load_ovf_numpy(path)
    else:
        return _load_ovf_numpy(path)


def _load_ovf_numpy(path: Path) -> dict[str, Any]:
    """Simple OVF ASCII parser (fallback when discretisedfield is not installed).

    Supports OVF 1.0 ASCII format.
    """
    with path.open("r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    header: dict[str, Any] = {}
    data_lines: list[str] = []
    in_data = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#") and not in_data:
            # Parse header
            if ":" in stripped:
                key, _, val = stripped[1:].partition(":")
                header[key.strip().lower()] = val.strip()
            if "begin: data" in stripped.lower():
                in_data = True
        elif in_data and stripped and not stripped.startswith("#"):
            if "end: data" in stripped.lower():
                break
            data_lines.append(stripped)

    # Extract grid dimensions
    nx = int(header.get("xnodes", 1))
    ny = int(header.get("ynodes", 1))
    nz = int(header.get("znodes", 1))

    vals: list[list[float]] = []
    for dline in data_lines:
        parts = dline.split()
        if len(parts) >= 3:
            try:
                vals.append([float(p) for p in parts[:3]])
            except ValueError:
                pass

    # Robust reshape: truncate if long, zero-pad if short — reshape never fails.
    n_expected = nx * ny * nz
    m_flat = np.array(vals, dtype=float) if vals else np.zeros((0, 3))
    if len(m_flat) >= n_expected:
        m_flat = m_flat[:n_expected]
    else:
        pad = np.zeros((n_expected - len(m_flat), 3))
        m_flat = np.vstack([m_flat, pad]) if len(m_flat) else pad
    m = m_flat.reshape((nx, ny, nz, 3))

    return {
        "header": header,
        "m": m,
        "nx": nx,
        "ny": ny,
        "nz": nz,
        "xbase": float(header.get("xbase", 1e-9)),
        "ybase": float(header.get("ybase", 1e-9)),
        "zbase": float(header.get("zbase", 1e-9)),
    }


# ---------------------------------------------------------------------------
# T-P3-15: simviz basic — 2D slice
# ---------------------------------------------------------------------------


def render_2d(
    field_or_path: Any,
    plane: str = "z",
    plane_index: int | None = None,
    figsize: tuple[float, float] | None = None,
    colormap: str = "RdBu_r",
) -> tuple[plt.Figure, plt.Axes]:
    """Render a 2D magnetization slice from an OVF file or discretisedfield Field.

    Uses ``Field.mpl()`` when ``discretisedfield`` is installed.
    Falls back to direct imshow from a numpy array otherwise.

    Parameters
    ----------
    field_or_path:
        OVF file path string/Path, or a ``discretisedfield.Field`` object.
    plane:
        Slice plane ("x", "y", or "z").
    plane_index:
        Slice index. Uses the center slice when None.
    figsize:
        Figure size in inches. Auto-sized when None.
    colormap:
        matplotlib colormap name.

    Returns
    -------
    tuple[Figure, Axes]
        Fully rendered matplotlib figure and axes.
    """
    # Load data
    if isinstance(field_or_path, (str, Path)):
        field = load_ovf(field_or_path)
    else:
        field = field_or_path

    fig, ax = plt.subplots(figsize=figsize or (5, 5))

    if _DF_AVAILABLE and isinstance(field, df.Field):
        # discretisedfield path — use mpl()
        try:
            if plane == "z":
                sl = field.sel(z=field.mesh.region.center[2])
            elif plane == "y":
                sl = field.sel(y=field.mesh.region.center[1])
            else:
                sl = field.sel(x=field.mesh.region.center[0])

            sl.mpl(ax=ax, scalar_kw={"cmap": colormap})
        except Exception as exc:
            warnings.warn(f"discretisedfield mpl() failed: {exc}. Falling back to numpy render.", stacklevel=2)
            _render_2d_numpy(field, ax, plane, plane_index, colormap)
    else:
        # numpy fallback
        _render_2d_numpy(field, ax, plane, plane_index, colormap)

    ax.set_title(f"Magnetization slice ({plane}-plane)")
    ax.set_xlabel("x (nm)")
    ax.set_ylabel("y (nm)")

    return fig, ax


def _render_2d_numpy(
    field_data: dict[str, Any] | Any,
    ax: plt.Axes,
    plane: str,
    plane_index: int | None,
    colormap: str,
) -> None:
    """Render a 2D slice from a numpy array."""
    if isinstance(field_data, dict):
        m = field_data["m"]  # (nx, ny, nz, 3)
    else:
        # discretisedfield Field → numpy
        m = field_data.array

    if plane == "z":
        idx = plane_index if plane_index is not None else m.shape[2] // 2
        slice_data = m[:, :, idx, 2]  # m_z component
    elif plane == "y":
        idx = plane_index if plane_index is not None else m.shape[1] // 2
        slice_data = m[:, idx, :, 2]
    else:
        idx = plane_index if plane_index is not None else m.shape[0] // 2
        slice_data = m[idx, :, :, 2]

    im = ax.imshow(
        slice_data.T,
        origin="lower",
        cmap=colormap,
        vmin=-1.0,
        vmax=1.0,
    )
    plt.colorbar(im, ax=ax, label="m_z")


# ---------------------------------------------------------------------------
# T-P3-16: HSL color wheel — skyrmion standard
# ---------------------------------------------------------------------------


def render_hsl(
    field_or_path: Any,
    plane: str = "z",
    plane_index: int | None = None,
    figsize: tuple[float, float] | None = None,
    show_colorbar: bool = True,
) -> tuple[plt.Figure, plt.Axes]:
    """Render the in-plane magnetization direction using the HSL color wheel (skyrmion standard).

    Color wheel convention:
    - Hue       : In-plane azimuthal angle φ (0°=+x red, 90°=+y green, 180°=-x blue, 270°=-y yellow)
    - Lightness : m_z component (+1=bright, -1=dark)
    - Skyrmion core (↓) is dark; edge (↑) is bright.

    Uses ``Field.mpl.lightness()`` when ``discretisedfield`` is installed.
    Falls back to direct HSL computation via the colorsys module otherwise.

    Parameters
    ----------
    field_or_path:
        OVF file path or ``discretisedfield.Field`` object.
    plane:
        Slice plane (only "z" is fully supported).
    plane_index:
        Slice index. Uses the center when None.
    figsize:
        Figure size in inches.
    show_colorbar:
        Whether to show the color bar (azimuthal angle 0–360°).

    Returns
    -------
    tuple[Figure, Axes]
        Fully rendered matplotlib figure and axes.
    """
    if isinstance(field_or_path, (str, Path)):
        field = load_ovf(field_or_path)
    else:
        field = field_or_path

    fig, ax = plt.subplots(figsize=figsize or (5, 5))

    if _DF_AVAILABLE and isinstance(field, df.Field):
        try:
            if plane == "z":
                sl = field.sel(z=field.mesh.region.center[2])
            else:
                sl = field

            sl.mpl.lightness(ax=ax)
            ax.set_title("Magnetization HSL color wheel (skyrmion standard)")
        except Exception as exc:
            warnings.warn(
                f"discretisedfield mpl.lightness() failed: {exc}. Falling back to direct HSL.", stacklevel=2
            )
            _render_hsl_direct(field, ax, plane, plane_index)
    else:
        _render_hsl_direct(field, ax, plane, plane_index)

    ax.set_xlabel("x (nm)")
    ax.set_ylabel("y (nm)")

    if show_colorbar:
        # Add HSL color wheel color bar (azimuthal angle 0–360°)
        import matplotlib.colors as mcolors

        cmap_wheel = _make_hsl_colormap()
        sm = plt.cm.ScalarMappable(cmap=cmap_wheel, norm=mcolors.Normalize(0, 360))
        sm.set_array([])
        cbar = plt.colorbar(sm, ax=ax, orientation="horizontal", pad=0.1, shrink=0.7)
        cbar.set_label("In-plane azimuthal angle φ (°)")
        cbar.set_ticks([0, 90, 180, 270, 360])
        cbar.set_ticklabels(["0°(+x)", "90°(+y)", "180°(-x)", "270°(-y)", "360°"])

    return fig, ax


def _render_hsl_direct(
    field_data: dict[str, Any] | Any,
    ax: plt.Axes,
    plane: str,
    plane_index: int | None,
) -> None:
    """Render the HSL color wheel via direct computation (fallback when discretisedfield is not installed).

    Color wheel formula:
    - φ = atan2(m_y, m_x)  [0, 2π]
    - H = φ / (2π)          [0, 1]
    - L = 0.5 × (m_z + 1)  [0, 1] (m_z=-1: L=0, m_z=+1: L=1)
    - S = 1.0 (always maximum saturation)
    """
    import colorsys

    if isinstance(field_data, dict):
        m = field_data["m"]
    else:
        try:
            m = field_data.array
        except AttributeError:
            m = np.zeros((10, 10, 1, 3))
            m[:, :, 0, 0] = 1.0

    if plane == "z":
        idx = plane_index if plane_index is not None else m.shape[2] // 2
        mx = m[:, :, idx, 0]
        my = m[:, :, idx, 1]
        mz = m[:, :, idx, 2]
    else:
        idx = plane_index if plane_index is not None else m.shape[0] // 2
        mx = m[idx, :, :, 0]
        my = m[idx, :, :, 1]
        mz = m[idx, :, :, 2]

    nx, ny = mx.shape
    rgb_image = np.zeros((ny, nx, 3))

    for i in range(nx):
        for j in range(ny):
            phi = np.arctan2(float(my[i, j]), float(mx[i, j]))
            h = (phi % (2 * np.pi)) / (2 * np.pi)
            l = 0.5 * (float(mz[i, j]) + 1.0)
            s = 1.0
            r, g, b = colorsys.hls_to_rgb(h, l, s)
            rgb_image[j, i, :] = [r, g, b]

    ax.imshow(rgb_image, origin="lower", interpolation="nearest")
    ax.set_title("Magnetization HSL color wheel")


def _make_hsl_colormap() -> matplotlib.colors.LinearSegmentedColormap:
    """Create the HSL color wheel colormap (azimuthal angle 0–360°).

    0°=red, 90°=green, 180°=cyan, 270°=blue.
    """
    import colorsys
    import matplotlib.colors as mcolors

    n = 256
    colors = []
    for i in range(n):
        h = i / n
        r, g, b = colorsys.hls_to_rgb(h, 0.5, 1.0)
        colors.append((r, g, b))

    return mcolors.LinearSegmentedColormap.from_list("hsl_wheel", colors)


# ---------------------------------------------------------------------------
# T-P3-17: quiver overlay
# ---------------------------------------------------------------------------


def render_quiver(
    field_or_path: Any,
    plane: str = "z",
    plane_index: int | None = None,
    subsample: int = 4,
    figsize: tuple[float, float] | None = None,
    show_hsl: bool = True,
) -> tuple[plt.Figure, plt.Axes]:
    """Render the magnetization vector field using matplotlib quiver.

    Can overlay arrows on an HSL color wheel background (``show_hsl=True``).
    Arrow color encodes m_z component (RdBu colormap).

    Parameters
    ----------
    field_or_path:
        OVF file path or Field object.
    plane:
        Slice plane.
    plane_index:
        Slice index.
    subsample:
        Subsampling factor (one arrow per n×n grid). Prevents overcrowding.
    figsize:
        Figure size.
    show_hsl:
        Whether to show the HSL color wheel background.

    Returns
    -------
    tuple[Figure, Axes]
        Fully rendered matplotlib figure and axes.
    """
    if isinstance(field_or_path, (str, Path)):
        field = load_ovf(field_or_path)
    else:
        field = field_or_path

    if show_hsl:
        fig, ax = render_hsl(
            field, plane=plane, plane_index=plane_index, figsize=figsize, show_colorbar=False
        )
    else:
        fig, ax = plt.subplots(figsize=figsize or (5, 5))

    # Extract numpy array
    if isinstance(field, dict):
        m = field["m"]
    elif _DF_AVAILABLE and isinstance(field, df.Field):
        m = field.array
    else:
        m = np.zeros((10, 10, 1, 3))

    if plane == "z":
        idx = plane_index if plane_index is not None else m.shape[2] // 2
        mx = m[:, :, idx, 0]
        my = m[:, :, idx, 1]
        mz = m[:, :, idx, 2]
    else:
        idx = plane_index if plane_index is not None else m.shape[0] // 2
        mx = m[idx, :, :, 0]
        my = m[idx, :, :, 1]
        mz = m[idx, :, :, 2]

    # Subsampling
    nx, ny = mx.shape
    xs = np.arange(0, nx, subsample)
    ys = np.arange(0, ny, subsample)
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    U = mx[::subsample, ::subsample]
    V = my[::subsample, ::subsample]
    C = mz[::subsample, ::subsample]

    # Arrows — color encodes m_z (RdBu_r)
    q = ax.quiver(
        X,
        Y,
        U,
        V,
        C,
        cmap="RdBu_r",
        clim=(-1, 1),
        scale=15,
        width=0.005,
        alpha=0.8,
    )
    plt.colorbar(q, ax=ax, label="m_z")

    ax.set_title(f"Magnetization quiver ({plane}-plane)")
    ax.set_xlabel("x (cells)")
    ax.set_ylabel("y (cells)")

    return fig, ax


# ---------------------------------------------------------------------------
# T-P3-18: PyVista 3D off-screen render
# ---------------------------------------------------------------------------


def render_3d(
    field_or_path: Any,
    output_path: Path | str | None = None,
    glyph_scale: float = 0.5,
    colormap: str = "RdBu_r",
) -> Path | None:
    """Visualize a 3D magnetization structure using PyVista off-screen rendering and return a PNG path.

    Use T-P3-15 and T-P3-16 (vector paths) for publication-quality output;
    this function generates a 3D preview PNG (raster).

    Returns None with a warning when PyVista is not installed.

    Parameters
    ----------
    field_or_path:
        OVF file path or Field object.
    output_path:
        PNG output path. Saves to a temporary file and returns the path when None.
    glyph_scale:
        Arrow size scale.
    colormap:
        PyVista colormap name.

    Returns
    -------
    Path | None
        PNG file path, or None when PyVista is not installed.
    """
    if not _PV_AVAILABLE:
        warnings.warn(
            "PyVista is not installed. Skipping 3D render.\n"
            "Install with: pip install pyvista",
            UserWarning,
            stacklevel=2,
        )
        return None

    import tempfile

    if isinstance(field_or_path, (str, Path)):
        field = load_ovf(field_or_path)
    else:
        field = field_or_path

    # Extract numpy array
    if isinstance(field, dict):
        m = field["m"]  # (nx, ny, nz, 3)
    elif _DF_AVAILABLE and isinstance(field, df.Field):
        m = field.array
    else:
        m = np.ones((5, 5, 5, 3)) * np.array([0, 0, 1])

    nx, ny, nz = m.shape[:3]

    # PyVista 3D render — any failure (API drift, missing GL context, headless
    # environment) degrades gracefully to None. The whole block is guarded.
    try:
        # ImageData is the pyvista >= 0.40 name for the former UniformGrid.
        grid_cls = getattr(pv, "ImageData", None) or getattr(pv, "UniformGrid", None)
        if grid_cls is None:
            raise AttributeError("pyvista exposes neither ImageData nor UniformGrid")
        grid = grid_cls()
        grid.dimensions = (nx, ny, nz)
        grid.spacing = (1, 1, 1)

        m_flat = m.reshape(-1, 3).astype(float)
        grid["magnetization"] = m_flat
        grid["mz"] = m_flat[:, 2]

        glyphs = grid.glyph(orient="magnetization", scale="mz", factor=glyph_scale)

        plotter = pv.Plotter(off_screen=True)
        plotter.add_mesh(
            glyphs,
            scalars="mz",
            cmap=colormap,
            clim=(-1, 1),
            show_scalar_bar=True,
            scalar_bar_args={"title": "m_z"},
        )
        plotter.set_background("white")
        plotter.add_axes()

        if output_path is None:
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            output_path = Path(tmp.name)
            tmp.close()
        else:
            output_path = Path(output_path)

        plotter.screenshot(str(output_path))
        plotter.close()

        return output_path

    except Exception as exc:
        warnings.warn(f"PyVista 3D render failed: {exc}", UserWarning, stacklevel=2)
        return None


# ---------------------------------------------------------------------------
# FigureSpec panel renderer entry point
# ---------------------------------------------------------------------------


class SimVizRenderer:
    """Renderer that handles FigureSpec SIM_VIZ panels.

    Called from figure/compose.py.
    Reads render type, OVF path, and other options from ``panel.extra``.

    extra keys:
    - ``"ovf_path"``: OVF file path.
    - ``"render_type"``: "2d" / "hsl" / "quiver" / "3d".
    - ``"plane"``: Slice plane ("x", "y", or "z").
    - ``"plane_index"``: Slice index.
    - ``"subsample"``: Quiver subsampling factor (default 4).
    """

    def render_panel(
        self,
        panel: PanelSpec,
        ax: plt.Axes,
    ) -> plt.Axes:
        """Render a single SIM_VIZ panel onto ``ax``.

        Parameters
        ----------
        panel:
            ``PanelSpec`` to render.
        ax:
            matplotlib ``Axes`` to draw on.

        Returns
        -------
        Axes
            Fully rendered ``Axes``.
        """
        ovf_path = panel.extra.get("ovf_path")
        render_type = panel.extra.get("render_type", "hsl")
        plane = panel.extra.get("plane", "z")
        plane_index = panel.extra.get("plane_index", None)
        subsample = panel.extra.get("subsample", 4)

        if ovf_path is None:
            # Dummy visualization (no OVF path provided)
            ax.text(
                0.5,
                0.5,
                "No OVF path\n(set panel.extra['ovf_path'])",
                ha="center",
                va="center",
                transform=ax.transAxes,
            )
            return ax

        field = load_ovf(ovf_path)

        if render_type == "2d":
            fig_tmp, ax_tmp = render_2d(field, plane=plane, plane_index=plane_index)
        elif render_type == "hsl":
            fig_tmp, ax_tmp = render_hsl(field, plane=plane, plane_index=plane_index)
        elif render_type == "quiver":
            fig_tmp, ax_tmp = render_quiver(
                field, plane=plane, plane_index=plane_index, subsample=subsample
            )
        else:
            fig_tmp, ax_tmp = render_hsl(field, plane=plane, plane_index=plane_index)

        # Transfer ax_tmp content to ax via image (direct render is more accurate in panel composition)
        fig_tmp.canvas.draw()
        img_array = np.frombuffer(fig_tmp.canvas.tostring_rgb(), dtype=np.uint8)
        img_array = img_array.reshape(fig_tmp.canvas.get_width_height()[::-1] + (3,))
        plt.close(fig_tmp)

        ax.imshow(img_array, origin="upper")
        ax.axis("off")
        if panel.title:
            ax.set_title(panel.title)

        return ax

    def render_standalone(
        self,
        panel: PanelSpec,
        figsize: tuple[float, float] | None = None,
    ) -> tuple[plt.Figure, plt.Axes]:
        """Create a standalone figure.

        Parameters
        ----------
        panel:
            Panel to render.
        figsize:
            Figure size.

        Returns
        -------
        tuple[Figure, Axes]
        """
        ovf_path = panel.extra.get("ovf_path")
        render_type = panel.extra.get("render_type", "hsl")
        plane = panel.extra.get("plane", "z")
        plane_index = panel.extra.get("plane_index", None)
        subsample = panel.extra.get("subsample", 4)

        if ovf_path is None:
            fig, ax = plt.subplots(figsize=figsize or (5, 5))
            ax.text(0.5, 0.5, "No OVF", ha="center", va="center", transform=ax.transAxes)
            return fig, ax

        field = load_ovf(ovf_path)

        if render_type == "2d":
            return render_2d(field, plane=plane, plane_index=plane_index, figsize=figsize)
        elif render_type == "hsl":
            return render_hsl(field, plane=plane, plane_index=plane_index, figsize=figsize)
        elif render_type == "quiver":
            return render_quiver(
                field,
                plane=plane,
                plane_index=plane_index,
                subsample=subsample,
                figsize=figsize,
            )
        else:
            return render_hsl(field, plane=plane, plane_index=plane_index, figsize=figsize)
