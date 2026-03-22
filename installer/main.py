#!/usr/bin/env python3
"""
WiFi Captive Portal Installer

A GUI installer for the WiFi Captive Portal system.
Run with: sudo python3 main.py
"""

import sys
import os
import logging
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication,
    QWizard,
    QMessageBox,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QIcon

from wizard.welcome_page import WelcomePage
from wizard.system_check_page import SystemCheckPage
from wizard.network_page import NetworkPage
from wizard.security_page import SecurityPage
from wizard.install_page import InstallPage
from wizard.finish_page import FinishPage


# Setup logging
log_dir = Path("/var/log")
log_file = log_dir / "wifi-portal-installer.log"

try:
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(),
        ]
    )
except PermissionError:
    # If we can't write to /var/log, use current directory
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

logger = logging.getLogger(__name__)


class InstallerWizard(QWizard):
    """Main installer wizard."""

    # Page IDs
    PAGE_WELCOME = 0
    PAGE_SYSTEM_CHECK = 1
    PAGE_NETWORK = 2
    PAGE_SECURITY = 3
    PAGE_INSTALL = 4
    PAGE_FINISH = 5

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("WiFi Captive Portal Installer")
        self.setMinimumSize(700, 600)
        self.resize(800, 700)

        # Set wizard style
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.setOption(QWizard.WizardOption.HaveHelpButton, False)
        self.setOption(QWizard.WizardOption.CancelButtonOnLeft, True)

        # Set font
        font = QFont("Sans Serif", 10)
        self.setFont(font)

        # Add pages
        self.setPage(self.PAGE_WELCOME, WelcomePage(self))
        self.setPage(self.PAGE_SYSTEM_CHECK, SystemCheckPage(self))
        self.setPage(self.PAGE_NETWORK, NetworkPage(self))
        self.setPage(self.PAGE_SECURITY, SecurityPage(self))
        self.setPage(self.PAGE_INSTALL, InstallPage(self))
        self.setPage(self.PAGE_FINISH, FinishPage(self))

        # Set start page
        self.setStartId(self.PAGE_WELCOME)

        # Connect signals
        self.currentIdChanged.connect(self._on_page_changed)

        logger.info("Installer wizard initialized")

    def _on_page_changed(self, page_id: int):
        """Handle page change."""
        logger.info(f"Changed to page {page_id}")

        # Update button text based on page
        if page_id == self.PAGE_WELCOME:
            self.button(QWizard.WizardButton.NextButton).setText("Start")
        elif page_id == self.PAGE_INSTALL:
            self.button(QWizard.WizardButton.BackButton).setEnabled(False)
            self.button(QWizard.WizardButton.NextButton).setText("Finish")
        elif page_id == self.PAGE_FINISH:
            self.button(QWizard.WizardButton.FinishButton).setText("Close")

    def get_mode(self) -> str:
        """Get the selected installation mode."""
        welcome_page = self.page(self.PAGE_WELCOME)
        if hasattr(welcome_page, 'get_mode'):
            return welcome_page.get_mode()
        return "install"

    def reject(self):
        """Handle cancel button."""
        reply = QMessageBox.question(
            self,
            "Cancel Installation",
            "Are you sure you want to cancel the installation?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            logger.info("Installation cancelled by user")
            super().reject()


def check_root():
    """Check if running as root."""
    if os.geteuid() != 0:
        QMessageBox.critical(
            None,
            "Permission Error",
            "This installer must be run as root.\n\n"
            "Please run with: sudo python3 main.py"
        )
        sys.exit(1)


def main():
    """Main entry point."""
    logger.info("=" * 50)
    logger.info("WiFi Captive Portal Installer starting...")
    logger.info("=" * 50)

    # Check for root
    check_root()

    # Create application
    app = QApplication(sys.argv)
    app.setApplicationName("WiFi Captive Portal Installer")
    app.setApplicationVersion("1.0.0")

    # Set application style
    app.setStyle("Fusion")

    # Load stylesheet if exists
    style_file = Path(__file__).parent / "resources" / "styles.qss"
    if style_file.exists():
        with open(style_file, "r") as f:
            app.setStyleSheet(f.read())

    # Create and show wizard
    wizard = InstallerWizard()
    wizard.show()

    # Run application
    result = app.exec()

    logger.info("Installer finished with code %d", result)
    sys.exit(result)


if __name__ == "__main__":
    main()
