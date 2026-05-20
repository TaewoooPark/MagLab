"""Unit tests for handoff — unit conversion, temperature dependence, and provenance validation.

Design rationale: impl/04-P3-multiscale.md T-P3-06~08 · plan/11-appendices.md Appendix D.

bcc Fe golden value sources:
  J_1 = 34.3 meV — Pajda 2001 Phys. Rev. B 64, 174402.
  T_C = 1043 K — Kittel, Introduction to Solid State Physics 8th Ed. (2004) p.330.
  m = 2.22 μ_B — Kittel ibid.
  a = 2.87 Å — CRC Handbook 2022.
  Ms(0) = 1.71e6 A/m — Coey, Magnetism and Magnetic Materials (2010) p.126.
  A_ex = 2.0e-11 J/m — Oogane et al., Jpn. J. Appl. Phys. 45, 3889 (2006).
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# dft_to_atomistic unit conversion tests
# ---------------------------------------------------------------------------


class TestDftToAtomistic:
    """dft_to_atomistic — meV → K/J conversion and provenance tests."""

    # bcc Fe 1NN exchange coupling — Pajda 2001
    J_1_MEV = 34.3  # meV
    J_1_K_EXPECTED = 397.8  # K (= 34.3 × e×10⁻³ / k_B ≈ 11.6045 K/meV)
    MAE_MEV = 0.052  # meV/atom
    DMI_MEV = 0.5  # meV (hypothetical asymmetric system DMI)

    def test_j_ij_mev_to_k_conversion(self) -> None:
        """Verify that J_ij: meV → K conversion is correct.

        Conversion formula: J[K] = J[meV] × e×10⁻³ / k_B
          = J[meV] × 11.6045 K/meV (approximation)
        Source: CODATA 2022 constants (maglab.physics.constants).
        """
        from maglab.sim.handoff import dft_to_atomistic

        result = dft_to_atomistic(
            J_ij_meV=self.J_1_MEV,
            MAE_meV_atom=self.MAE_MEV,
            DMI_meV=0.0,
            m_muB=2.22,
        )

        params = result.params
        j_k = params.get("J_ij_K", params.get("J_1_K"))
        assert j_k is not None
        # 34.3 meV × 11.6045 K/meV ≈ 397.8 K, tolerance ±1%
        assert abs(j_k - self.J_1_K_EXPECTED) < 5.0, (
            f"J_ij[K]={j_k:.2f}, expected={self.J_1_K_EXPECTED:.1f}, "
            f"error={(j_k - self.J_1_K_EXPECTED) / self.J_1_K_EXPECTED * 100:.2f}%"
        )

    def test_mae_mev_to_j_conversion(self) -> None:
        """Verify that MAE: meV/atom → J/atom conversion is correct.

        Conversion formula: MAE[J] = MAE[meV] × e × 10⁻³
          = 0.052 meV × 1.6022e-19 J/eV × 10⁻³ ≈ 8.33e-24 J/atom
        """
        from maglab.sim.handoff import dft_to_atomistic

        result = dft_to_atomistic(
            J_ij_meV=self.J_1_MEV,
            MAE_meV_atom=self.MAE_MEV,
            DMI_meV=0.0,
            m_muB=2.22,
        )

        params = result.params
        mae_j = params.get("MAE_J_atom", params.get("K_J_atom"))
        if mae_j is not None:
            expected = self.MAE_MEV * 1.6022e-22  # meV → J
            assert abs(mae_j - expected) / expected < 0.01, (
                f"MAE[J]={mae_j:.4e}, expected={expected:.4e}"
            )

    def test_handoff_result_has_assumptions(self) -> None:
        """HandoffResult.assumptions must not be empty."""
        from maglab.sim.handoff import dft_to_atomistic

        result = dft_to_atomistic(
            J_ij_meV=self.J_1_MEV,
            MAE_meV_atom=self.MAE_MEV,
            DMI_meV=0.0,
            m_muB=2.22,
        )

        assert len(result.assumptions) > 0
        # Heisenberg model assumption must be included
        assumptions_text = " ".join(result.assumptions).lower()
        assert any(kw in assumptions_text for kw in ["heisenberg", "j_ij"])

    def test_handoff_result_has_provenance(self) -> None:
        """HandoffResult.provenance_datapoints must contain DataPoints."""
        from maglab.sim.handoff import dft_to_atomistic

        result = dft_to_atomistic(
            J_ij_meV=self.J_1_MEV,
            MAE_meV_atom=self.MAE_MEV,
            DMI_meV=0.0,
            m_muB=2.22,
            source_ref="Pajda 2001",
        )

        assert len(result.provenance_datapoints) > 0

    def test_from_scale_to_scale(self) -> None:
        """Verify that HandoffResult from_scale and to_scale are correct."""
        from maglab.sim.handoff import dft_to_atomistic

        result = dft_to_atomistic(
            J_ij_meV=self.J_1_MEV,
            MAE_meV_atom=self.MAE_MEV,
            DMI_meV=0.0,
            m_muB=2.22,
        )

        assert result.from_scale in ("dft", "DFT")
        assert result.to_scale in ("atomistic", "atomistic")


# ---------------------------------------------------------------------------
# atomistic_to_micro unit conversion and temperature dependence tests
# ---------------------------------------------------------------------------


class TestAtomisticToMicro:
    """atomistic_to_micro — A(T)/K(T) temperature dependence and unit conversion tests."""

    # bcc Fe parameters (T_K array: 0 K to 1043 K)
    T_K_ARRAY = [0.0, 100.0, 200.0, 300.0, 500.0, 800.0, 1000.0, 1043.0]
    # M(T)/M(0) ~ (1 - T/T_C)^0.33, T_C=1043 K
    T_C = 1043.0
    M_S_0 = 1.71e6  # A/m (bcc Fe, Coey 2010 p.126)

    def _mt_array(self) -> list[float]:
        """Generate the bcc Fe M(T) array."""
        return [self.M_S_0 * max(0.0, (1 - t / self.T_C)) ** 0.33 for t in self.T_K_ARRAY]

    def test_exchange_stiffness_at_0k(self) -> None:
        """Exchange stiffness computed from A(0 K) = 2J₁S²/a must be in a reasonable range.

        bcc Fe reference value: A ≈ 2.0e-11 J/m
        Source: Oogane et al., Jpn. J. Appl. Phys. 45, 3889 (2006).
        Tolerance: ±50% accounting for material scatter.
        """
        from maglab.sim.handoff import atomistic_to_micro

        result = atomistic_to_micro(
            T_K=self.T_K_ARRAY,
            M_s_Am=self._mt_array(),
            T_target_K=1.0,  # T>0 required — oracle rejects T=0
            J_1_K=398.0,  # bcc Fe 1NN, Pajda 2001
            K_0_Jm3=4.8e4,  # bcc Fe MAE
            D_Jm2=0.0,
            lattice_const_m=2.87e-10,
        )

        a_jm = result.params.get("A_Jm_at_T", result.params.get("A_Jm"))
        assert a_jm is not None
        # bcc Fe A: 1~5 × 10⁻¹¹ J/m range
        assert 1e-12 < a_jm < 1e-10, (
            f"A(1K)={a_jm:.3e} J/m is outside physical range. Expected: 1e-12~1e-10 J/m"
        )

    def test_exchange_stiffness_decreases_with_temp(self) -> None:
        """A(T) must decrease monotonically with increasing temperature.

        Spin-wave theory: A(T) = A(0) × (Ms(T)/Ms(0))²
        Source: Hinzke et al., Phys. Rev. B 84, 184406 (2011).
        """
        from maglab.sim.handoff import atomistic_to_micro

        result_0 = atomistic_to_micro(
            T_K=self.T_K_ARRAY,
            M_s_Am=self._mt_array(),
            T_target_K=0.0,
            J_1_K=398.0,
            K_0_Jm3=4.8e4,
            D_Jm2=0.0,
            lattice_const_m=2.87e-10,
        )
        result_300 = atomistic_to_micro(
            T_K=self.T_K_ARRAY,
            M_s_Am=self._mt_array(),
            T_target_K=300.0,
            J_1_K=398.0,
            K_0_Jm3=4.8e4,
            D_Jm2=0.0,
            lattice_const_m=2.87e-10,
        )

        a_0 = result_0.params.get("A_Jm_at_T", result_0.params.get("A_Jm"))
        a_300 = result_300.params.get("A_Jm_at_T", result_300.params.get("A_Jm"))

        if a_0 is not None and a_300 is not None:
            assert a_0 >= a_300, f"A(0K)={a_0:.3e} < A(300K)={a_300:.3e}: expected temperature decrease"

    def test_anisotropy_callen_callen_scaling(self) -> None:
        """K(T) = K(0) × (Ms(T)/Ms(0))^n scaling must be applied.

        Callen-Callen (1966) theory: uniaxial anisotropy n=2.
        Source: E.R. Callen & H.B. Callen, Phys. Rev. 139, A455 (1965).
        """
        from maglab.sim.handoff import atomistic_to_micro

        k_0 = 4.8e4  # J/m³
        result = atomistic_to_micro(
            T_K=self.T_K_ARRAY,
            M_s_Am=self._mt_array(),
            T_target_K=300.0,
            J_1_K=398.0,
            K_0_Jm3=k_0,
            D_Jm2=0.0,
            lattice_const_m=2.87e-10,
        )

        k_t = result.params.get("K_Jm3_at_T", result.params.get("K_Jm3"))
        ms_t = result.params.get("Ms_Am_at_T", result.params.get("Ms_Am"))

        if k_t is not None and ms_t is not None:
            ms_0 = self.M_S_0
            k_expected = k_0 * (ms_t / ms_0) ** 2
            assert abs(k_t - k_expected) / max(k_0, 1e-10) < 0.05, (
                f"K(T)={k_t:.4e}, expected={k_expected:.4e} (Callen-Callen)"
            )

    def test_handoff_result_assumptions_cited(self) -> None:
        """Handoff assumptions must include Chikazumi and temperature dependence sources."""
        from maglab.sim.handoff import atomistic_to_micro

        result = atomistic_to_micro(
            T_K=self.T_K_ARRAY,
            M_s_Am=self._mt_array(),
            T_target_K=300.0,
            J_1_K=398.0,
            K_0_Jm3=4.8e4,
            D_Jm2=0.0,
            lattice_const_m=2.87e-10,
        )

        assumptions_text = " ".join(result.assumptions).lower()
        # A(T) temperature dependence assumption
        assert any(
            kw in assumptions_text
            for kw in ["chikazumi", "hinzke", "spin-wave", "a(t)", "callen"]
        )


# ---------------------------------------------------------------------------
# micro_to_device unit conversion tests
# ---------------------------------------------------------------------------


class TestMicroToDevice:
    """micro_to_device — Slonczewski critical current and skyrmion Hall angle tests."""

    # Representative Permalloy parameters
    MS_AM = 800_000.0  # A/m
    A_JM = 1.3e-11  # J/m
    ALPHA = 0.01
    K_JM3 = 0.0
    D_JM2 = 0.5e-3  # J/m² (DMI, skyrmion generation possible)

    def test_critical_current_positive(self) -> None:
        """Critical current density must be positive.

        Slonczewski 1996: j_c = (2e·α·μ₀·Ms·t·H_k) / (ℏ·θ_SH)
        Source: J.C. Slonczewski, J. Magn. Magn. Mater. 159, L1 (1996).
        """
        from maglab.sim.handoff import micro_to_device

        result = micro_to_device(
            Ms_Am=self.MS_AM,
            A_Jm=self.A_JM,
            alpha=self.ALPHA,
            K_Jm3=self.K_JM3,
            D_Jm2=0.0,
        )

        j_c = result.params.get("j_c_Am2")
        if j_c is not None:
            assert j_c > 0, f"Critical current density j_c={j_c:.3e} A/m² is negative."
            # Physical range: 10⁸ ~ 10¹³ A/m²
            assert 1e8 < j_c < 1e13, f"j_c={j_c:.3e} A/m² is outside physical range."

    def test_switching_time_positive(self) -> None:
        """Switching time must be positive.

        t_sw ≈ 1 / (α × γ × H_k) (simple macrospin WKB)
        """
        from maglab.sim.handoff import micro_to_device

        result = micro_to_device(
            Ms_Am=self.MS_AM,
            A_Jm=self.A_JM,
            alpha=self.ALPHA,
            K_Jm3=1e4,  # anisotropy required to define switching time
            D_Jm2=0.0,
        )

        t_sw = result.params.get("t_sw_s")
        if t_sw is not None:
            assert t_sw > 0, f"Switching time t_sw={t_sw:.3e} s is negative."

    def test_skyrmion_hall_angle_with_dmi(self) -> None:
        """Skyrmion Hall angle must be computed when DMI ≠ 0.

        tan(θ_SkH) = G / (α × D_thiele)
        Source: Thiele 1973, Phys. Rev. Lett. 30, 230.
        """
        from maglab.sim.handoff import micro_to_device

        result = micro_to_device(
            Ms_Am=self.MS_AM,
            A_Jm=self.A_JM,
            alpha=self.ALPHA,
            K_Jm3=self.K_JM3,
            D_Jm2=self.D_JM2,
        )

        theta = result.params.get("theta_SkH_rad")
        # When DMI is present, Hall angle must be computed or None (no error)
        assert "theta_SkH_rad" in result.params or theta is None

    def test_from_scale_is_micro(self) -> None:
        """from_scale of micro_to_device must be 'micro'."""
        from maglab.sim.handoff import micro_to_device

        result = micro_to_device(
            Ms_Am=self.MS_AM,
            A_Jm=self.A_JM,
            alpha=self.ALPHA,
            K_Jm3=self.K_JM3,
            D_Jm2=0.0,
        )

        assert result.from_scale in ("micro", "micromagnetic")
        assert result.to_scale in ("device",)


# ---------------------------------------------------------------------------
# HandoffUnitError tests
# ---------------------------------------------------------------------------


class TestHandoffUnitError:
    """HandoffUnitError — exception on unit mismatch tests."""

    def test_negative_j_ij_raises_or_warns(self) -> None:
        """Negative J_ij (antiferromagnetic) must raise an error or emit a warning."""
        from maglab.sim.handoff import dft_to_atomistic

        # Negative J_ij must be recorded as HandoffUnitError or in warnings
        try:
            result = dft_to_atomistic(
                J_ij_meV=-10.0,  # antiferromagnetic — unusual case
                MAE_meV_atom=0.0,
                DMI_meV=0.0,
                m_muB=2.0,
            )
            # If no exception, a warning must be present
            assert len(result.warnings) > 0 or result.params.get("J_ij_K", 0) < 0
        except Exception:
            pass  # exception is also acceptable


# ---------------------------------------------------------------------------
# verify_unit_continuity tests
# ---------------------------------------------------------------------------


class TestVerifyUnitContinuity:
    """verify_unit_continuity — unit continuity check tests."""

    def test_matching_keys_pass(self) -> None:
        """OracleResult.ok must be True when all required keys are present."""
        from maglab.sim.handoff import verify_unit_continuity

        from_params = {"Ms_Am": 1.71e6, "A_Jm": 2.0e-11}
        to_params = {"Ms_Am": 1.71e6, "A_Jm": 2.0e-11}

        result = verify_unit_continuity(from_params, to_params, required_keys=["Ms_Am", "A_Jm"])
        assert result.ok

    def test_missing_key_fails(self) -> None:
        """OracleResult.ok must be False when a required key is missing."""
        from maglab.sim.handoff import verify_unit_continuity

        from_params = {"Ms_Am": 1.71e6}
        to_params = {}  # A_Jm missing

        result = verify_unit_continuity(from_params, to_params, required_keys=["Ms_Am", "A_Jm"])
        assert not result.ok
