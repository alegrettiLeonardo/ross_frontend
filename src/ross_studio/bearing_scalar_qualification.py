import numpy as np
import ross as rs
from ross_studio.app import RossStudioWindow
from ross_studio.domain import (
    RotorProject,
    ShaftSection,
    BearingSpec,
    BearingCoefficientPoint,
    DiskSpec,
    LoadSpec,
    ProbeSpec,
    OperatingCase,
)
from ross_studio.models import ProjectModel
from ross_studio.project_file_controller import ProjectFileController
from ross_studio.project_file_service import ProjectOpenResult
from ross_studio.project_io import save_project
from ross_studio.ross_backend import RossBackend


from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from ross_studio.analysis_pipeline import AnalysisPipelineService, AnalysisPolicy
from ross_studio.solver_console import SolverConsole
from tempfile import TemporaryDirectory
from pathlib import Path
from copy import deepcopy


_COEFFICIENT_NAMES = ("Kxx", "Kxy", "Kyx", "Kyy", "Cxx", "Cxy", "Cyx", "Cyy")


def _run_window_analysis(window):
    """Invoke the real application handler; only reduce the requested grid size."""
    errors = []
    watch = QTimer()
    watch.setInterval(20)
    timeout = QTimer()
    timeout.setSingleShot(True)

    def configure():
        console = QApplication.activeModalWidget()
        if not isinstance(console, SolverConsole):
            errors.append("Expected the real SolverConsole")
            if console:
                console.reject()
            return
        console.service = AnalysisPipelineService(
            policy=AnalysisPolicy(
                modal_num_modes=12,
                campbell_frequencies=4,
                campbell_points=7,
                response_points=7,
            )
        )

        def finish():
            if console._thread is None:
                if console.analysis_result is None:
                    errors.append(console.status_detail.text())
                console.open_results.click() if console.analysis_result is not None else console.reject()

        def expired():
            errors.append("Native GUI analysis exceeded 120 s")
            console._stop()

        watch.timeout.connect(finish)
        timeout.timeout.connect(expired)
        watch.start()
        timeout.start(120000)

    QTimer.singleShot(0, configure)
    try:
        window.run_analysis()
    finally:
        watch.stop()
        timeout.stop()
    assert not errors, errors
    assert window.results_page.result is not None
    assert window.stack.currentWidget() is window.results_page
    return window.results_page.result


def _kc_values(element, omega):
    k = np.asarray(element.K(float(omega)), dtype=float)
    c = np.asarray(element.C(float(omega)), dtype=float)
    return (k[0, 0], k[0, 1], k[1, 0], k[1, 1], c[0, 0], c[0, 1], c[1, 0], c[1, 1])


def _display_quantization_tolerance(text, value):
    """Return half one displayed ULP for the table's scientific ``.2e`` format.

    The scientific parity remains governed by the much tighter rtol/atol checks
    below. This tolerance applies only to the intentionally rounded GUI text and
    prevents a binary interpolation round-off at an exact tabulated station from
    flipping the last displayed digit (for example 2.345 around a rounding tie).
    """
    if value == 0.0:
        return 0.0
    if "e" not in text.lower():
        raise AssertionError(f"Expected scientific-notation K/C display, received {text!r}")
    exponent = int(text.lower().split("e", 1)[1])
    return 0.5000001 * 10.0 ** (exponent - 2)


def _coefficient_evidence(table, applied, expected, speeds_rpm, *, rtol=1e-12, atol=1e-9):
    """Audit all eight displayed/applied coefficients at every solved speed station."""
    assert table.rowCount() == len(speeds_rpm)
    rows = []
    for row, rpm in enumerate(speeds_rpm):
        omega = float(rpm) * np.pi / 30.0
        studio_values = _kc_values(applied, omega)
        reference_values = _kc_values(expected, omega)
        gui_rpm_text = table.item(row, 0).text()
        # The production results table intentionally renders RPM with the Python
        # ``:g`` presentation contract.  Audit that contract exactly, while all
        # solver/interpolation comparisons below continue to use the unrounded
        # engineering speed and tight numerical tolerances.
        assert gui_rpm_text == f"{float(rpm):g}", (
            f"GUI RPM row {row} does not match the declared :g display contract: "
            f"text={gui_rpm_text!r}, engineering_rpm={float(rpm)!r}"
        )
        for col, (name, studio, reference) in enumerate(
            zip(_COEFFICIENT_NAMES, studio_values, reference_values), 1
        ):
            studio = float(studio)
            reference = float(reference)
            gui_text = table.item(row, col).text()
            gui_value = float(gui_text)
            display_tolerance = _display_quantization_tolerance(gui_text, studio)
            display_roundoff = np.finfo(float).eps * max(1.0, abs(studio))
            assert abs(gui_value - studio) <= display_tolerance + display_roundoff, (
                f"{name} GUI display at {rpm:g} rpm differs from the Studio value beyond the declared .2e display precision: "
                f"text={gui_text!r}, gui={gui_value!r}, studio={studio!r}, display_tolerance={display_tolerance!r}"
            )
            np.testing.assert_allclose(studio, reference, rtol=rtol, atol=atol, err_msg=f"{name} at {rpm:g} rpm")
            absolute_error = abs(studio - reference)
            relative_error = 0.0 if reference == 0.0 and absolute_error == 0.0 else (
                float("inf") if reference == 0.0 else absolute_error / abs(reference)
            )
            tolerance = atol + rtol * abs(reference)
            rows.append(
                {
                    "rpm": float(rpm),
                    "frequency_rad_s": omega,
                    "gui_rpm_display": gui_rpm_text,
                    "coefficient": name,
                    "gui_display": gui_text,
                    "gui_value": gui_value,
                    "gui_display_tolerance": display_tolerance,
                    "studio_value": studio,
                    "reference_value": reference,
                    "absolute_error": absolute_error,
                    "relative_error": relative_error,
                    "rtol": rtol,
                    "atol": atol,
                    "tolerance": tolerance,
                    "status": "PASS",
                }
            )
    return rows


def _base_project():
    return RotorProject(
        name="scalar display",
        shaft_sections=[ShaftSection(1, 500.0, 40.0, fe_elements=4)],
        bearings=[
            BearingSpec("L", 0.0, kxx=1e7, kyy=1e7, cxx=100.0, cyy=100.0),
            BearingSpec("R", 500.0, kxx=2e7, kyy=3e7, cxx=200.0, cyy=300.0),
        ],
        disks=[DiskSpec("D", 250.0, 5.123456, 0.023456, 0.034567)],
        loads=[LoadSpec("U", "unbalance", 250.0, 0.000012345678, 12.345678)],
        probes=[ProbeSpec("P", 250.0, 1, 34.56789)],
        operating_cases=[OperatingCase("B", 1800.345, 900.123, 4500.789, 30.0)],
    )


def _reference_rotor(expected):
    return rs.Rotor(
        [
            rs.ShaftElement(
                L=0.125,
                idl=0.0,
                odl=0.04,
                n=n,
                material=rs.Material(name="Steel", rho=7850.0, E=207e9, Poisson=0.3),
            )
            for n in range(4)
        ],
        [rs.DiskElement(n=2, m=5.123456, Id=0.023456, Ip=0.034567)],
        [expected, rs.BearingElement(n=4, kxx=2e7, kyy=3e7, cxx=200.0, cyy=300.0)],
    )


def _solver_and_reopen_evidence(window, controller, tmp_path, rotor, reference, applied, expected, speeds, model):
    evidence = []

    def compare(name, a, b, rtol=1e-7, atol=1e-10):
        a, b = np.asarray(a), np.asarray(b)
        np.testing.assert_allclose(a, b, rtol=rtol, atol=atol, err_msg=model + " " + name)
        evidence.append(
            dict(
                quantity=name,
                max_absolute_error=float(np.max(abs(a - b))),
                reference_max_abs=float(np.max(abs(b))),
                rtol=rtol,
                atol=atol,
                status="PASS",
            )
        )

    for omega in np.linspace(900.123, 4500.789, 9) * np.pi / 30:
        compare(f"element K {omega}", applied.K(omega), expected.K(omega), 1e-12, 1e-9)
        compare(f"element C {omega}", applied.C(omega), expected.C(omega), 1e-12, 1e-9)
        compare(f"assembled K {omega}", rotor.K(omega), reference.K(omega), 1e-12, 1e-8)
        compare(f"assembled C {omega}", rotor.C(omega), reference.C(omega), 1e-12, 1e-8)

    result = _run_window_analysis(window)
    native = reference.run_modal(1800.345 * np.pi / 30, num_modes=12)
    compare("modal wn", result.modal.wn, native.wn, 1e-7, 1e-7)
    ub = reference.run_unbalance_response(
        2,
        0.000012345678,
        12.345678 * np.pi / 180,
        result.speed_rpm * np.pi / 30,
    )
    compare("unbalance complex", result.unbalance.forced_resp, ub.forced_resp, 1e-7, 1e-13)
    page = window.results_page
    page._select_analysis("modal")
    for row, freq in enumerate(native.wn):
        assert page.table.item(row, 1).text() == f"{freq / (2 * np.pi):.3f}"

    saved = save_project(window.project, tmp_path / "saved.rossproj")
    assert controller.open_path(saved)
    reopened = RossBackend().build_rotor(window.project.engineering).rotor.bearing_elements[0]
    np.testing.assert_array_equal(reopened.K(123.456), applied.K(123.456))
    np.testing.assert_array_equal(reopened.C(123.456), applied.C(123.456))
    _coefficient_evidence(window.bearing_page.kc_table, reopened, expected, speeds)
    again = _run_window_analysis(window)
    compare("reopened modal", again.modal.wn, result.modal.wn, 1e-7, 1e-7)
    compare("reopened unbalance", again.unbalance.forced_resp, result.unbalance.forced_resp, 1e-7, 1e-13)
    return evidence


def run_scalar_bearing_case(model, tmp_path):
    app = QApplication.instance() or QApplication([])
    if model == "BallBearingElement":
        size_key, count_key, native_size, native_count = "d_balls_mm", "n_balls", "d_balls", "n_balls"
    elif model == "RollerBearingElement":
        size_key, count_key, native_size, native_count = "roller_length_mm", "n_rollers", "l_rollers", "n_rollers"
    elif model == "CylindricalBearing":
        pass
    else:
        raise ValueError(f"Unsupported qualification model {model}")

    p = _base_project()
    window = RossStudioWindow()
    try:
        controller = ProjectFileController(window)
        assert controller.new()
        assert window.project.engineering is None
        controller._replace_project(
            ProjectOpenResult(ProjectModel.from_engineering(p), tmp_path / "fixture.rossproj", None, "qualification", False),
            clean=False,
        )
        window._refresh_bearing_page(selected_class=model)
        if model == "CylindricalBearing":
            values = {
                "speed_min_rpm": 900.123,
                "speed_max_rpm": 4500.789,
                "speed_points": 5,
                "weight_n": 525.123456,
                "bearing_length_mm": 30.123456,
                "journal_diameter_mm": 100.234567,
                "radial_clearance_mm": 0.123456789,
                "oil_viscosity_pa_s": 0.123456789,
            }
            speeds = np.linspace(900.123, 4500.789, 5)
            expected = rs.CylindricalBearing(
                n=0,
                speed=speeds * np.pi / 30,
                weight=525.123456,
                bearing_length=0.030123456,
                journal_diameter=0.100234567,
                radial_clearance=0.000123456789,
                oil_viscosity=0.123456789,
            )
            input_units = {
                "speed_min_rpm": "rpm",
                "speed_max_rpm": "rpm",
                "weight_n": "N",
                "bearing_length_mm": "mm",
                "journal_diameter_mm": "mm",
                "radial_clearance_mm": "mm",
                "oil_viscosity_pa_s": "Pa*s",
            }
            native_inputs = {
                "speed_rad_s": [float(v) for v in speeds * np.pi / 30],
                "weight_n": 525.123456,
                "bearing_length_m": 0.030123456,
                "journal_diameter_m": 0.100234567,
                "radial_clearance_m": 0.000123456789,
                "oil_viscosity_pa_s": 0.123456789,
            }
        else:
            values = {
                size_key: 23.456789,
                count_key: 9,
                "static_load_n": 1234.56789,
                "contact_angle_deg": 13.456789,
            }
            speeds = np.asarray([1800.345])
            expected = getattr(rs, model)(
                n=0,
                **{native_size: 0.023456789, native_count: 9},
                fs=1234.56789,
                alpha=13.456789 * np.pi / 180,
            )
            input_units = {
                size_key: "mm",
                count_key: "count",
                "static_load_n": "N",
                "contact_angle_deg": "deg",
            }
            native_inputs = {
                native_size: 0.023456789,
                native_count: 9,
                "fs_n": 1234.56789,
                "alpha_rad": float(13.456789 * np.pi / 180),
            }

        for key, value in values.items():
            window.bearing_page.input_panel.fields[key].setValue(value)
        window._calculate_bearing()
        assert window.bearing_calculation is not None

        # A changed visible input must invalidate preview before a user can Apply.
        changed_key = "weight_n" if model == "CylindricalBearing" else "static_load_n"
        field = window.bearing_page.input_panel.fields[changed_key]
        field.setValue(values[changed_key] + 1.0)
        assert not window.bearing_page.apply_button.isEnabled(), "Changed input leaves stale Apply enabled"
        window._apply_bearing()
        assert p.bearings[0].ross_class == "BearingElement", "Stale calculation was committed"
        field.setValue(0.0)
        window._calculate_bearing()
        assert window.bearing_calculation is None
        assert not window.bearing_page.apply_button.isEnabled()
        assert p.bearings[0].ross_class == "BearingElement"
        field.setValue(values[changed_key])
        window._calculate_bearing()
        assert window.bearing_calculation is not None

        # The Apply boundary must also reject changed inputs if notifications
        # were suppressed by another UI operation; no scientific solver is mocked.
        field.blockSignals(True)
        field.setValue(values[changed_key] + 2.0)
        window._apply_bearing()
        assert p.bearings[0].ross_class == "BearingElement"
        field.blockSignals(False)
        field.setValue(values[changed_key])
        window._calculate_bearing()
        assert window.bearing_calculation is not None
        window._apply_bearing()
        assert p.bearings[0].ross_class == model


        parameters = (
            {
                "speed_rpm": np.linspace(900.123, 4500.789, 5),
                "weight_n": 525.123456,
                "bearing_length_m": 0.030123456,
                "journal_diameter_m": 0.100234567,
                "radial_clearance_m": 0.000123456789,
                "oil_viscosity_pa_s": 0.123456789,
            }
            if model == "CylindricalBearing"
            else {
                count_key: 9,
                ("d_balls_m" if model == "BallBearingElement" else "roller_length_m"): 0.023456789,
                "static_load_n": 1234.56789,
                "contact_angle_rad": 13.456789 * np.pi / 180,
            }
        )
        for key, value in parameters.items():
            np.testing.assert_allclose(p.bearings[0].metadata[key], value, rtol=1e-14, atol=1e-15, err_msg=key)

        rotor = RossBackend().build_rotor(p).rotor
        applied = rotor.bearing_elements[0]
        assert type(applied).__name__ == model
        np.testing.assert_allclose(applied.K(123.456), expected.K(123.456), rtol=1e-12, atol=1e-12)
        np.testing.assert_allclose(applied.C(123.456), expected.C(123.456), rtol=1e-12, atol=1e-12)
        coefficient_rows = _coefficient_evidence(window.bearing_page.kc_table, applied, expected, speeds)

        reference = _reference_rotor(expected)
        evidence = _solver_and_reopen_evidence(window, controller, tmp_path, rotor, reference, applied, expected, speeds, model)
        return {
            "comparisons": evidence,
            "coefficient_comparisons": coefficient_rows,
            "status": "PASS",
            "model": model,
            "native_class": type(applied).__name__,
            "gui_inputs": {key: float(value) if isinstance(value, np.floating) else value for key, value in values.items()},
            "input_units": input_units,
            "native_inputs": native_inputs,
            "kxx": float(expected.kxx[0]),
            "cxx": float(expected.cxx[0]),
            "scope": "Existing station: GUI Calculate/Apply, native element and assembly K/C, main-window solver, modal table, complex unbalance, controller reopen/recompute",
        }
    finally:
        window.close()
        window.deleteLater()
        QApplication.instance().processEvents()


def run_direct_kc_case(tmp_path):
    """Full Direct K/C Bearing Studio transaction, including interpolation and stale gates."""
    app = QApplication.instance() or QApplication([])
    p = _base_project()
    speeds = np.linspace(900.123, 4500.789, 5)

    # Project starts from deliberately different coefficients. Editing the GUI must
    # remain preview-only until Apply commits the sentinel table below.
    p.bearings[0].coefficients = [
        BearingCoefficientPoint(float(rpm), 1.0e7, 0.0, 0.0, 1.1e7, 100.0, 0.0, 0.0, 110.0)
        for rpm in speeds
    ]
    before = deepcopy(p.bearings[0])

    sentinel = []
    for i, rpm in enumerate(speeds):
        sentinel.append(
            BearingCoefficientPoint(
                rpm=float(rpm),
                kxx=11111110.0 + 123456.7 * i,
                kxy=22222.2 + 111.1 * i,
                kyx=-33333.3 - 222.2 * i,
                kyy=14444440.0 + 234567.8 * i,
                cxx=123.456 + 1.111 * i,
                cxy=2.345 + 0.111 * i,
                cyx=-3.456 - 0.222 * i,
                cyy=234.567 + 2.222 * i,
            )
        )

    arrays = {name.lower(): np.asarray([getattr(point, name.lower()) for point in sentinel]) for name in _COEFFICIENT_NAMES}
    expected = rs.BearingElement(
        n=0,
        kxx=arrays["kxx"],
        kxy=arrays["kxy"],
        kyx=arrays["kyx"],
        kyy=arrays["kyy"],
        cxx=arrays["cxx"],
        cxy=arrays["cxy"],
        cyx=arrays["cyx"],
        cyy=arrays["cyy"],
        frequency=speeds * np.pi / 30,
    )

    window = RossStudioWindow()
    try:
        controller = ProjectFileController(window)
        assert controller.new()
        assert window.project.engineering is None
        controller._replace_project(
            ProjectOpenResult(ProjectModel.from_engineering(p), tmp_path / "fixture-direct.rossproj", None, "qualification", False),
            clean=False,
        )
        window._refresh_bearing_page(selected_class="BearingElement")
        input_table = window.bearing_page.input_panel.kc_table
        assert input_table is not None and input_table.rowCount() == len(sentinel)
        for row, point in enumerate(sentinel):
            values = (
                point.rpm,
                point.kxx,
                point.kxy,
                point.kyx,
                point.kyy,
                point.cxx,
                point.cxy,
                point.cyx,
                point.cyy,
            )
            for col, value in enumerate(values):
                input_table.item(row, col).setText(f"{value:.17g}")

        window._calculate_bearing()
        assert window.bearing_calculation is not None
        assert p.bearings[0] == before, "Calculate mutated Direct K/C before Apply"

        # Normal notification path: edit after Calculate immediately invalidates preview.
        original_text = input_table.item(0, 1).text()
        input_table.item(0, 1).setText(f"{sentinel[0].kxx + 1.0:.17g}")
        assert not window.bearing_page.apply_button.isEnabled()
        window._apply_bearing()
        assert p.bearings[0] == before
        input_table.item(0, 1).setText(original_text)
        window._calculate_bearing()
        assert window.bearing_calculation is not None

        # Boundary path: even with Qt notifications suppressed, stale inputs cannot commit.
        input_table.blockSignals(True)
        input_table.item(0, 1).setText(f"{sentinel[0].kxx + 2.0:.17g}")
        window._apply_bearing()
        assert p.bearings[0] == before
        input_table.item(0, 1).setText(original_text)
        input_table.blockSignals(False)
        window._calculate_bearing()
        assert window.bearing_calculation is not None
        window._apply_bearing()

        assert p.bearings[0] != before
        assert p.bearings[0].ross_class == "BearingElement"
        assert p.bearings[0].coefficients == sentinel
        rotor = RossBackend().build_rotor(p).rotor
        applied = rotor.bearing_elements[0]
        assert type(applied).__name__ == "BearingElement"
        coefficient_rows = _coefficient_evidence(window.bearing_page.kc_table, applied, expected, speeds)
        reference = _reference_rotor(expected)
        evidence = _solver_and_reopen_evidence(
            window, controller, tmp_path, rotor, reference, applied, expected, speeds, "BearingElement"
        )
        return {
            "comparisons": evidence,
            "coefficient_comparisons": coefficient_rows,
            "status": "PASS",
            "model": "BearingElement",
            "native_class": type(applied).__name__,
            "gui_inputs": [
                {
                    "rpm": point.rpm,
                    **{name.lower(): float(getattr(point, name.lower())) for name in _COEFFICIENT_NAMES},
                }
                for point in sentinel
            ],
            "input_units": {"rpm": "rpm", "K": "N/m", "C": "N*s/m"},
            "native_inputs": {"frequency_rad_s": [float(v) for v in speeds * np.pi / 30]},
            "scope": "Direct speed-dependent K/C table: GUI edit/Calculate/preview/Apply, interpolation, native BearingElement assembly/solver, stale rejection, save/reopen/recompute",
        }
    finally:
        window.close()
        window.deleteLater()
        QApplication.instance().processEvents()


def run_scalar_bearing_qualification():
    with TemporaryDirectory() as directory:
        path = Path(directory)
        direct = run_direct_kc_case(path)
        cases = [
            run_scalar_bearing_case(model, path)
            for model in ("BallBearingElement", "RollerBearingElement", "CylindricalBearing")
        ]
    return {
        "status": "PASS",
        "ross_version": rs.__version__,
        "direct_kc": direct,
        "cases": cases,
        "feature_status": "Source scope tested; require exact frozen Linux/Windows evidence; other bearing models and flexible support excluded",
    }
