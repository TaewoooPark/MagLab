"""Device/transport scale simulation — basic stub.

Design rationale: impl/04-P3-multiscale.md T-P3-14.

In P3 this is a placeholder that defines the basic structure so that
``ScaleSpec(scale="device")`` can be inserted into ``MultiScaleSpec``.
Substantive implementation is deferred to P4 and beyond.
"""

from __future__ import annotations

from maglab.sim.device.spec import DeviceResult, DeviceSpec

__all__ = ["DeviceSpec", "DeviceResult"]
