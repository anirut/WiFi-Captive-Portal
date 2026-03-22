"""Network configuration page."""

import subprocess
from PyQt6.QtWidgets import (
    QWizardPage,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QGroupBox,
    QGridLayout,
    QSpinBox,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from ..utils.validators import validate_ip_address, validate_dhcp_range


class NetworkPage(QWizardPage):
    """Page for network configuration."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Network Configuration")
        self.setSubTitle("Configure network interfaces and IP settings")

        self._setup_ui()
        self._detect_interfaces()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # Interface selection group
        interface_group = QGroupBox("Network Interfaces")
        interface_layout = QGridLayout(interface_group)

        # WiFi Interface
        interface_layout.addWidget(QLabel("WiFi Interface:"), 0, 0)
        self.wifi_combo = QComboBox()
        self.wifi_combo.setMinimumWidth(200)
        interface_layout.addWidget(self.wifi_combo, 0, 1)

        wifi_hint = QLabel("(for guest devices)")
        wifi_hint.setStyleSheet("color: gray;")
        interface_layout.addWidget(wifi_hint, 0, 2)

        # WAN Interface
        interface_layout.addWidget(QLabel("WAN Interface:"), 1, 0)
        self.wan_combo = QComboBox()
        self.wan_combo.setMinimumWidth(200)
        interface_layout.addWidget(self.wan_combo, 1, 1)

        wan_hint = QLabel("(for internet connection)")
        wan_hint.setStyleSheet("color: gray;")
        interface_layout.addWidget(wan_hint, 1, 2)

        layout.addWidget(interface_group)

        # Portal IP configuration
        portal_group = QGroupBox("Portal Settings")
        portal_layout = QGridLayout(portal_group)

        # Portal IP
        portal_layout.addWidget(QLabel("Portal IP:"), 0, 0)
        self.portal_ip_edit = QLineEdit("192.168.4.1")
        self.portal_ip_edit.setPlaceholderText("e.g., 192.168.4.1")
        portal_layout.addWidget(self.portal_ip_edit, 0, 1)

        portal_hint = QLabel("(guests connect to this IP)")
        portal_hint.setStyleSheet("color: gray;")
        portal_layout.addWidget(portal_hint, 0, 2)

        # Portal Port
        portal_layout.addWidget(QLabel("Portal Port:"), 1, 0)
        self.portal_port_spin = QSpinBox()
        self.portal_port_spin.setRange(1, 65535)
        self.portal_port_spin.setValue(8080)
        portal_layout.addWidget(self.portal_port_spin, 1, 1)

        port_hint = QLabel("(default: 8080)")
        port_hint.setStyleSheet("color: gray;")
        portal_layout.addWidget(port_hint, 1, 2)

        layout.addWidget(portal_group)

        # DHCP configuration
        dhcp_group = QGroupBox("DHCP Configuration")
        dhcp_layout = QGridLayout(dhcp_group)

        # DHCP Start
        dhcp_layout.addWidget(QLabel("DHCP Start:"), 0, 0)
        self.dhcp_start_edit = QLineEdit("192.168.4.10")
        self.dhcp_start_edit.setPlaceholderText("e.g., 192.168.4.10")
        dhcp_layout.addWidget(self.dhcp_start_edit, 0, 1)

        # DHCP End
        dhcp_layout.addWidget(QLabel("DHCP End:"), 1, 0)
        self.dhcp_end_edit = QLineEdit("192.168.4.254")
        self.dhcp_end_edit.setPlaceholderText("e.g., 192.168.4.254")
        dhcp_layout.addWidget(self.dhcp_end_edit, 1, 1)

        dhcp_hint = QLabel("(IP range for guest devices)")
        dhcp_hint.setStyleSheet("color: gray;")
        dhcp_layout.addWidget(dhcp_hint, 1, 2)

        # Lease time
        dhcp_layout.addWidget(QLabel("Lease Time:"), 2, 0)
        self.lease_time_combo = QComboBox()
        self.lease_time_combo.addItems(["1 hour", "6 hours", "12 hours", "24 hours"])
        self.lease_time_combo.setCurrentText("12 hours")
        dhcp_layout.addWidget(self.lease_time_combo, 2, 1)

        layout.addWidget(dhcp_group)

        # Validation status
        self.validation_label = QLabel("")
        self.validation_label.setWordWrap(True)
        self.validation_label.setStyleSheet("padding: 5px;")
        layout.addWidget(self.validation_label)

        # Connect validators
        self.portal_ip_edit.textChanged.connect(self._validate)
        self.dhcp_start_edit.textChanged.connect(self._validate)
        self.dhcp_end_edit.textChanged.connect(self._validate)
        self.wifi_combo.currentIndexChanged.connect(self._validate)
        self.wan_combo.currentIndexChanged.connect(self._validate)

        layout.addStretch()

        # Register fields for wizard
        self.registerField("wifi_interface", self.wifi_combo, "currentText")
        self.registerField("wan_interface", self.wan_combo, "currentText")
        self.registerField("portal_ip", self.portal_ip_edit)
        self.registerField("portal_port", self.portal_port_spin)
        self.registerField("dhcp_start", self.dhcp_start_edit)
        self.registerField("dhcp_end", self.dhcp_end_edit)

    def _detect_interfaces(self):
        """Detect available network interfaces."""
        try:
            result = subprocess.run(
                ["ip", "-o", "link", "show"],
                capture_output=True,
                text=True,
                check=True
            )

            interfaces = []
            for line in result.stdout.strip().split("\n"):
                if line:
                    # Format: "2: eth0: ..."
                    parts = line.split(":")
                    if len(parts) >= 2:
                        name = parts[1].strip().split("@")[0]
                        if name != "lo":
                            interfaces.append(name)

            self.wifi_combo.clear()
            self.wan_combo.clear()
            self.wifi_combo.addItems(interfaces)
            self.wan_combo.addItems(interfaces)

            # Try to auto-select based on naming
            for i, iface in enumerate(interfaces):
                if iface.startswith(("wlan", "wl", "wlp")):
                    self.wifi_combo.setCurrentIndex(i)
                elif iface.startswith(("eth", "en", "em")):
                    self.wan_combo.setCurrentIndex(i)

        except Exception as e:
            print(f"Error detecting interfaces: {e}")

    def _validate(self):
        """Validate network configuration."""
        errors = []

        # Validate portal IP
        portal_ip = self.portal_ip_edit.text()
        ok, msg = validate_ip_address(portal_ip)
        if not ok:
            errors.append(f"Portal IP: {msg}")

        # Validate DHCP range
        dhcp_start = self.dhcp_start_edit.text()
        dhcp_end = self.dhcp_end_edit.text()
        ok, msg = validate_dhcp_range(dhcp_start, dhcp_end, portal_ip)
        if not ok:
            errors.append(f"DHCP Range: {msg}")

        # Check interfaces are different
        if self.wifi_combo.currentText() == self.wan_combo.currentText():
            errors.append("WiFi and WAN interfaces must be different")

        if errors:
            self.validation_label.setText("❌ " + "\n".join(errors))
            self.validation_label.setStyleSheet("color: red; padding: 5px;")
        else:
            self.validation_label.setText("✅ Configuration valid")
            self.validation_label.setStyleSheet("color: green; padding: 5px;")

        self.completeChanged.emit()

    def isComplete(self):
        """Check if page is complete."""
        portal_ip = self.portal_ip_edit.text()
        ok, _ = validate_ip_address(portal_ip)
        if not ok:
            return False

        dhcp_start = self.dhcp_start_edit.text()
        dhcp_end = self.dhcp_end_edit.text()
        ok, _ = validate_dhcp_range(dhcp_start, dhcp_end, portal_ip)
        if not ok:
            return False

        if self.wifi_combo.currentText() == self.wan_combo.currentText():
            return False

        return True

    def get_config(self):
        """Get network configuration."""
        return {
            "wifi_interface": self.wifi_combo.currentText(),
            "wan_interface": self.wan_combo.currentText(),
            "portal_ip": self.portal_ip_edit.text(),
            "portal_port": self.portal_port_spin.value(),
            "dhcp_start": self.dhcp_start_edit.text(),
            "dhcp_end": self.dhcp_end_edit.text(),
            "lease_time": self.lease_time_combo.currentText(),
        }
