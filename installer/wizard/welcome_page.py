"""Welcome page for the installer wizard."""

from PyQt6.QtWidgets import (
    QWizardPage,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QButtonGroup,
    QFrame,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont


class WelcomePage(QWizardPage):
    """Welcome page with mode selection."""

    # Signal emitted when mode changes
    mode_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("WiFi Captive Portal Installer")
        self.setSubTitle("Welcome to the installation wizard")

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(20)

        # Logo/Header
        header_label = QLabel("🏨 WiFi Captive Portal")
        header_label.setFont(QFont("Sans Serif", 24, QFont.Weight.Bold))
        header_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header_label)

        # Description
        desc_label = QLabel(
            "This wizard will help you install and configure the WiFi Captive Portal "
            "for your hotel or business.\n\n"
            "The portal provides:\n"
            "• Guest authentication via room number + last name\n"
            "• Voucher code authentication\n"
            "• Bandwidth management\n"
            "• Session tracking and management\n"
            "• PMS integration support"
        )
        desc_label.setWordWrap(True)
        desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(desc_label)

        # Separator
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(line)

        # Mode selection
        mode_label = QLabel("Select operation mode:")
        mode_label.setFont(QFont("Sans Serif", 12, QFont.Weight.Bold))
        layout.addWidget(mode_label)

        self.mode_group = QButtonGroup(self)

        modes = [
            ("install", "Install", "Fresh installation of WiFi Captive Portal", True),
            ("update", "Update", "Update existing installation to latest version", False),
            ("reconfigure", "Reconfigure", "Modify network or security settings", False),
            ("uninstall", "Uninstall", "Remove WiFi Captive Portal completely", False),
        ]

        for mode_id, label, description, is_default in modes:
            radio = QRadioButton(f"{label} - {description}")
            radio.setProperty("mode", mode_id)
            self.mode_group.addButton(radio)
            if is_default:
                radio.setChecked(True)
            layout.addWidget(radio)

        # Connect mode change signal
        self.mode_group.buttonClicked.connect(self._on_mode_changed)

        # Warning label for non-install modes
        self.warning_label = QLabel("")
        self.warning_label.setStyleSheet("color: orange; font-weight: bold;")
        self.warning_label.setWordWrap(True)
        self.warning_label.hide()
        layout.addWidget(self.warning_label)

        # Spacer
        layout.addStretch()

        # Requirements note
        req_label = QLabel(
            "⚠️ Note: This installer must be run as root (sudo).\n"
            "Required: Ubuntu 22.04 or 24.04 LTS, 2 network interfaces"
        )
        req_label.setStyleSheet("color: gray;")
        req_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(req_label)

    def _on_mode_changed(self, button):
        mode = button.property("mode")
        self.mode_changed.emit(mode)

        # Show warning for non-install modes
        if mode == "uninstall":
            self.warning_label.setText(
                "⚠️ Warning: Uninstall will remove all data including database and configuration!"
            )
            self.warning_label.show()
        elif mode == "reconfigure":
            self.warning_label.setText(
                "ℹ️ Reconfigure will restart services and may briefly disconnect guests."
            )
            self.warning_label.show()
        else:
            self.warning_label.hide()

    def get_mode(self) -> str:
        """Get the selected mode."""
        checked = self.mode_group.checkedButton()
        if checked:
            return checked.property("mode")
        return "install"

    def nextId(self):
        """Determine next page based on mode."""
        mode = self.get_mode()
        # Map modes to page IDs
        # 0: Welcome, 1: SystemCheck, 2: Network, 3: Security, 4: Install, 5: Finish
        if mode == "install":
            return 1  # System check
        elif mode == "update":
            return 4  # Go directly to install
        elif mode == "reconfigure":
            return 2  # Network config
        elif mode == "uninstall":
            return 4  # Go to install (will show uninstall progress)
        return 1
