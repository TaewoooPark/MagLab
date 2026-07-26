"""maglab.analysis.calibration tests — calibration factors must persist intact.

Every entry here corrects real measurement data (``corrected = value × factor +
offset``), so losing or truncating the registry does not fail loudly — it makes
later numbers quietly wrong.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from maglab.analysis.calibration import CalibrationEntry, CalibrationRegistry


def _entry(instrument: str = "keithley-2400", **kwargs: object) -> CalibrationEntry:
    params: dict[str, object] = {
        "instrument": instrument,
        "channel": "a",
        "factor": 1.05,
        "offset": 0.002,
        "uncertainty": 0.001,
    }
    params.update(kwargs)
    return CalibrationEntry(**params)  # type: ignore[arg-type]


class TestCalibrationEntry:
    def test_apply_and_unapply_round_trip(self) -> None:
        entry = _entry()
        raw = np.array([0.0, 1.0, 2.5])

        corrected = entry.apply(raw)
        assert np.allclose(corrected, raw * 1.05 + 0.002)
        assert np.allclose(entry.unapply(corrected), raw)

    def test_unapply_rejects_a_zero_factor(self) -> None:
        with pytest.raises(ValueError, match="cannot inverse-apply"):
            _entry(factor=0.0).unapply(1.0)

    def test_validity_window(self) -> None:
        now = datetime.now(UTC)
        entry = _entry(
            valid_from=(now - timedelta(days=1)).isoformat(),
            valid_until=(now + timedelta(days=1)).isoformat(),
        )

        assert entry.is_valid(now)
        assert not entry.is_valid(now - timedelta(days=2))
        assert not entry.is_valid(now + timedelta(days=2))


class TestCalibrationRegistryPersistence:
    def test_entries_round_trip_through_a_file(self, tmp_path: Path) -> None:
        path = tmp_path / "calibration.json"
        registry = CalibrationRegistry(path)
        entry_id = registry.add(_entry())

        reloaded = CalibrationRegistry(path)
        found = reloaded.get("keithley-2400", "a")

        assert found is not None
        assert found.id == entry_id
        assert found.factor == pytest.approx(1.05)
        assert found.offset == pytest.approx(0.002)
        assert found.uncertainty == pytest.approx(0.001)

    def test_get_returns_the_most_recent_valid_entry(self, tmp_path: Path) -> None:
        now = datetime.now(UTC)
        registry = CalibrationRegistry(tmp_path / "calibration.json")
        registry.add(_entry(factor=1.0, valid_from=(now - timedelta(days=10)).isoformat()))
        registry.add(_entry(factor=2.0, valid_from=(now - timedelta(days=1)).isoformat()))

        found = registry.get("keithley-2400", "a")
        assert found is not None and found.factor == pytest.approx(2.0)

    def test_check_expired_when_nothing_registered(self, tmp_path: Path) -> None:
        registry = CalibrationRegistry(tmp_path / "calibration.json")
        assert registry.check_expired("unknown-instrument") is True

    def test_failed_save_keeps_the_previous_registry_loadable(self, tmp_path: Path) -> None:
        """A truncated file makes CalibrationRegistry(path) raise from __init__."""
        path = tmp_path / "calibration.json"
        registry = CalibrationRegistry(path)
        registry.add(_entry(factor=1.05))
        before = path.read_text(encoding="utf-8")

        with (
            patch(
                "maglab.analysis.calibration.atomic_write_text", side_effect=OSError("disk full")
            ),
            pytest.raises(OSError),
        ):
            registry.add(_entry(factor=9.99))

        assert path.read_text(encoding="utf-8") == before
        reloaded = CalibrationRegistry(path)
        found = reloaded.get("keithley-2400", "a")
        assert found is not None and found.factor == pytest.approx(1.05)

    def test_save_leaves_no_scratch_files(self, tmp_path: Path) -> None:
        path = tmp_path / "calibration.json"
        registry = CalibrationRegistry(path)
        for factor in (1.0, 1.1, 1.2):
            registry.add(_entry(factor=factor))

        assert sorted(p.name for p in tmp_path.iterdir()) == ["calibration.json"]

    def test_stored_file_is_valid_json(self, tmp_path: Path) -> None:
        path = tmp_path / "calibration.json"
        CalibrationRegistry(path).add(_entry())

        payload = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(payload, list) and payload[0]["instrument"] == "keithley-2400"
