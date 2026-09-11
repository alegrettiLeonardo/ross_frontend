from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
)

from .domain import ShaftSection
from .shaft_geometry import (
    CUSTOM_LEGACY_LABEL,
    GUIDED_SHAFT_GEOMETRIES,
    ShaftGeometryType,
    classify_shaft_geometry,
    guided_diameters,
    tutorial_contract,
)


def _double(value: float, *, minimum: float = 0.0, maximum: float = 1.0e12) -> QDoubleSpinBox:
    widget = QDoubleSpinBox()
    widget.setDecimals(6)
    widget.setRange(minimum, maximum)
    widget.setValue(float(value))
    widget.setKeyboardTracking(False)
    return widget


class GuidedShaftSectionEditorDialog(QDialog):
    """ROSS-tutorial guided editor for one physical shaft section.

    Section length remains read-only in the current topology gate so editing one
    section cannot silently translate every downstream absolute coordinate. The
    user explicitly selects one of the four shaft families documented by ROSS; the
    resulting OD/ID values are then passed through the existing strict-Ross preview
    and commit transaction.
    """

    def __init__(self, section: ShaftSection, parent=None) -> None:
        super().__init__(parent)
        self.section = section
        self._initial_geometry = classify_shaft_geometry(section)
        self.setWindowTitle(f"Edit Shaft Section {section.section}")
        self.resize(520, 420)

        root = QVBoxLayout(self)
        note = QLabel(
            "Select a ROSS shaft geometry. The guided contracts follow the Modeling tutorial: "
            "solid/hollow controls ID and cylindrical/conical controls whether OD is constant. "
            "Length remains read-only in this gate; Apply still requires strict ROSS assembly."
        )
        note.setWordWrap(True)
        root.addWidget(note)

        form = QFormLayout()
        self.geometry = QComboBox()
        if self._initial_geometry is None:
            self.geometry.addItem(CUSTOM_LEGACY_LABEL, "__legacy__")
        for geometry in GUIDED_SHAFT_GEOMETRIES:
            self.geometry.addItem(geometry.value, geometry.value)

        if self._initial_geometry is None:
            self.geometry.setCurrentIndex(0)
        else:
            index = self.geometry.findData(self._initial_geometry.value)
            self.geometry.setCurrentIndex(max(0, index))

        self.contract = QLabel()
        self.contract.setWordWrap(True)
        self.contract.setObjectName("muted")

        self.length = _double(section.length_mm, minimum=1.0e-9)
        self.length.setEnabled(False)
        self.od_left = _double(section.od_left_mm, minimum=1.0e-9)
        self.od_right = _double(section.odr_mm, minimum=1.0e-9)
        self.id_left = _double(section.id_left_mm, minimum=0.0)
        self.id_right = _double(section.idr_mm, minimum=0.0)
        self.fe_elements = QSpinBox()
        self.fe_elements.setRange(1, 1000)
        self.fe_elements.setValue(section.fe_elements)
        self.material = QLineEdit(section.material)
        self.material.setReadOnly(True)

        form.addRow("ROSS shaft type", self.geometry)
        form.addRow("Tutorial contract", self.contract)
        form.addRow("Length (mm)", self.length)
        form.addRow("OD left / odl (mm)", self.od_left)
        form.addRow("OD right / odr (mm)", self.od_right)
        form.addRow("ID left / idl (mm)", self.id_left)
        form.addRow("ID right / idr (mm)", self.id_right)
        form.addRow("Base FE elements", self.fe_elements)
        form.addRow("Material", self.material)
        root.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self.geometry.currentIndexChanged.connect(self._geometry_changed)
        self.od_left.valueChanged.connect(self._mirror_guided_values)
        self.id_left.valueChanged.connect(self._mirror_guided_values)
        self._geometry_changed()

    @property
    def geometry_type(self) -> ShaftGeometryType | None:
        value = self.geometry.currentData()
        if value == "__legacy__" or value is None:
            return None
        return ShaftGeometryType(str(value))

    def _geometry_changed(self) -> None:
        geometry = self.geometry_type
        if geometry is None:
            self.contract.setText(
                "Imported/custom geometry retained exactly. Choose one of the four guided ROSS types to normalize this section."
            )
            for widget in (self.od_left, self.od_right, self.id_left, self.id_right):
                widget.setEnabled(True)
            return

        self.contract.setText(tutorial_contract(geometry))
        cylindrical = geometry in {
            ShaftGeometryType.SOLID_CYLINDRICAL,
            ShaftGeometryType.HOLLOW_CYLINDRICAL,
        }
        solid = geometry in {
            ShaftGeometryType.SOLID_CYLINDRICAL,
            ShaftGeometryType.SOLID_CONICAL,
        }

        self.od_left.setEnabled(True)
        self.od_right.setEnabled(not cylindrical)
        self.id_left.setEnabled(not solid)
        self.id_right.setEnabled(False)
        self._mirror_guided_values()

    def _mirror_guided_values(self) -> None:
        geometry = self.geometry_type
        if geometry is None:
            return
        cylindrical = geometry in {
            ShaftGeometryType.SOLID_CYLINDRICAL,
            ShaftGeometryType.HOLLOW_CYLINDRICAL,
        }
        solid = geometry in {
            ShaftGeometryType.SOLID_CYLINDRICAL,
            ShaftGeometryType.SOLID_CONICAL,
        }
        if cylindrical and self.od_right.value() != self.od_left.value():
            self.od_right.blockSignals(True)
            self.od_right.setValue(self.od_left.value())
            self.od_right.blockSignals(False)
        if solid:
            for widget in (self.id_left, self.id_right):
                if widget.value() != 0.0:
                    widget.blockSignals(True)
                    widget.setValue(0.0)
                    widget.blockSignals(False)
        elif self.id_right.value() != self.id_left.value():
            self.id_right.blockSignals(True)
            self.id_right.setValue(self.id_left.value())
            self.id_right.blockSignals(False)

    def changes(self) -> dict[str, object]:
        geometry = self.geometry_type
        if geometry is None:
            od_left = self.od_left.value()
            od_right = self.od_right.value()
            id_left = self.id_left.value()
            id_right = self.id_right.value()
        else:
            od_left, od_right, id_left, id_right = guided_diameters(
                geometry,
                od_left_mm=self.od_left.value(),
                od_right_mm=self.od_right.value(),
                id_left_mm=self.id_left.value(),
                id_right_mm=self.id_right.value(),
            )
        return {
            "od_left_mm": od_left,
            "od_right_mm": od_right,
            "id_left_mm": id_left,
            "id_right_mm": id_right,
            "fe_elements": self.fe_elements.value(),
        }

    @classmethod
    def guided_labels(cls) -> tuple[str, ...]:
        return tuple(item.value for item in GUIDED_SHAFT_GEOMETRIES)


# Production composition patches the historical global to this class so existing
# automation monkeypatching ``pages.rotor_model.ShaftSectionEditorDialog`` remains
# compatible.
ShaftSectionEditorDialog = GuidedShaftSectionEditorDialog


__all__ = ["GuidedShaftSectionEditorDialog", "ShaftSectionEditorDialog"]
