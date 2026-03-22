"""Finish page for the installer wizard."""

import webbrowser
from PyQt6.QtWidgets import (
    QWizardPage,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QGroupBox,
    QGridLayout,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont


class FinishPage(QWizardPage):
    """Final page showing installation summary."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Installation Complete")
        self.setSubTitle("Your WiFi Captive Portal is ready to use")

        self._portal_url = ""
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(20)

        # Success message
        success_label = QLabel("🎉 Installation Completed Successfully!")
        success_label.setFont(QFont("Sans Serif", 16, QFont.Weight.Bold))
        success_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        success_label.setStyleSheet("color: green; padding: 20px;")
        layout.addWidget(success_label)

        # Summary group
        summary_group = QGroupBox("Installation Summary")
        summary_layout = QGridLayout(summary_group)

        labels = [
            ("Portal URL:", "portal_url_label"),
            ("Admin URL:", "admin_url_label"),
            ("WiFi Interface:", "wifi_label"),
            ("WAN Interface:", "wan_label"),
            ("Portal IP:", "ip_label"),
            ("Database:", "db_label"),
            ("Status:", "status_label"),
        ]

        for row, (text, attr) in enumerate(labels):
            label = QLabel(text)
            label.setFont(QFont("Sans Serif", 10, QFont.Weight.Bold))
            summary_layout.addWidget(label, row, 0)

            value_label = QLabel("-")
            setattr(self, attr, value_label)
            summary_layout.addWidget(value_label, row, 1)

        layout.addWidget(summary_group)

        # Quick actions group
        actions_group = QGroupBox("Quick Actions")
        actions_layout = QVBoxLayout(actions_group)

        # Open Portal button
        self.open_portal_btn = QPushButton("🌐 Open Portal")
        self.open_portal_btn.setMinimumHeight(40)
        self.open_portal_btn.clicked.connect(self._open_portal)
        actions_layout.addWidget(self.open_portal_btn)

        # Open Admin button
        self.open_admin_btn = QPushButton("⚙️ Open Admin Panel")
        self.open_admin_btn.setMinimumHeight(40)
        self.open_admin_btn.clicked.connect(self._open_admin)
        actions_layout.addWidget(self.open_admin_btn)

        layout.addWidget(actions_group)

        # Next steps
        next_steps = QGroupBox("Next Steps")
        next_layout = QVBoxLayout(next_steps)

        steps = [
            "1. Connect a device to your WiFi network",
            "2. The device should be redirected to the portal automatically",
            "3. Test authentication with a room number or voucher code",
            "4. Access the admin panel to manage sessions and vouchers",
            "5. Configure your PMS adapter in the admin settings",
        ]

        for step in steps:
            step_label = QLabel(step)
            step_label.setWordWrap(True)
            next_layout.addWidget(step_label)

        layout.addWidget(next_steps)

        # Documentation link
        doc_label = QLabel(
            "📚 For more information, see the documentation in the docs/ directory"
        )
        doc_label.setStyleSheet("color: gray; padding: 10px;")
        doc_label.setWordWrap(True)
        layout.addWidget(doc_label)

        layout.addStretch()

    def initializePage(self):
        """Called when page is shown - populate summary."""
        wizard = self.wizard()

        # Get values from wizard fields
        portal_ip = self.field("portal_ip") or "192.168.4.1"
        portal_port = self.field("portal_port") or "8080"
        wifi = self.field("wifi_interface") or "wlan0"
        wan = self.field("wan_interface") or "eth0"
        admin_user = self.field("admin_username") or "admin"

        self._portal_url = f"http://{portal_ip}:{portal_port}"
        admin_url = f"{self._portal_url}/admin"

        # Update labels
        self.portal_url_label.setText(self._portal_url)
        self.portal_url_label.setStyleSheet("color: blue;")
        self.admin_url_label.setText(admin_url)
        self.admin_url_label.setStyleSheet("color: blue;")
        self.wifi_label.setText(wifi)
        self.wan_label.setText(wan)
        self.ip_label.setText(portal_ip)
        self.db_label.setText("PostgreSQL (wifi_portal)")
        self.status_label.setText("✅ Running")
        self.status_label.setStyleSheet("color: green;")

    def _open_portal(self):
        """Open portal URL in browser."""
        if self._portal_url:
            webbrowser.open(self._portal_url)

    def _open_admin(self):
        """Open admin URL in browser."""
        if self._portal_url:
            webbrowser.open(f"{self._portal_url}/admin")
