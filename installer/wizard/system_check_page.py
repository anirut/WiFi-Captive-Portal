"""System check page for verifying requirements."""

import platform
import shutil
import subprocess
from PyQt6.QtWidgets import (
    QWizardPage,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QGroupBox,
    QGridLayout,
    QPushButton,
    QProgressBar,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QColor


class SystemCheckWorker(QThread):
    """Worker thread for system checks."""

    check_complete = pyqtSignal(str, bool, str)  # check_name, passed, message
    all_complete = pyqtSignal(bool)  # all_passed

    def __init__(self, parent=None):
        super().__init__(parent)
        self.results = {}

    def run(self):
        checks = [
            ("os_version", self._check_os),
            ("root", self._check_root),
            ("ram", self._check_ram),
            ("disk", self._check_disk),
            ("network_interfaces", self._check_network_interfaces),
            ("internet", self._check_internet),
        ]

        all_passed = True
        for name, check_func in checks:
            passed, message = check_func()
            self.results[name] = (passed, message)
            self.check_complete.emit(name, passed, message)
            if not passed and name in ["os_version", "root", "network_interfaces"]:
                all_passed = False

        self.all_complete.emit(all_passed)

    def _check_os(self):
        """Check if running Ubuntu 22.04 or 24.04."""
        try:
            with open("/etc/os-release", "r") as f:
                content = f.read()
                if "Ubuntu" in content:
                    if "22.04" in content or "24.04" in content:
                        return True, "Ubuntu 22.04/24.04 detected"
                    return False, "Ubuntu version not supported (need 22.04 or 24.04)"
                return False, "Not running Ubuntu"
        except Exception as e:
            return False, f"Cannot detect OS: {str(e)}"

    def _check_root(self):
        """Check if running as root."""
        import os
        if os.geteuid() == 0:
            return True, "Running as root"
        return False, "Must run as root (use sudo)"

    def _check_ram(self):
        """Check available RAM (min 1GB, recommended 2GB)."""
        try:
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    if line.startswith("MemTotal"):
                        # Value is in kB
                        ram_kb = int(line.split()[1])
                        ram_gb = ram_kb / (1024 * 1024)
                        if ram_gb >= 2:
                            return True, f"{ram_gb:.1f} GB RAM (recommended)"
                        elif ram_gb >= 1:
                            return True, f"{ram_gb:.1f} GB RAM (minimum)"
                        return False, f"{ram_gb:.1f} GB RAM (need at least 1 GB)"
        except Exception as e:
            return False, f"Cannot detect RAM: {str(e)}"

    def _check_disk(self):
        """Check available disk space (min 10GB)."""
        try:
            result = subprocess.run(
                ["df", "-BG", "/"],
                capture_output=True,
                text=True,
                check=True
            )
            # Parse output: Filesystem, Size, Used, Avail, Use%, Mounted on
            lines = result.stdout.strip().split("\n")
            if len(lines) >= 2:
                parts = lines[1].split()
                available = int(parts[3].replace("G", ""))
                if available >= 20:
                    return True, f"{available} GB available (recommended)"
                elif available >= 10:
                    return True, f"{available} GB available (minimum)"
                return False, f"{available} GB available (need at least 10 GB)"
        except Exception as e:
            return False, f"Cannot detect disk space: {str(e)}"

    def _check_network_interfaces(self):
        """Check for at least 2 network interfaces."""
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
                    name = line.split(":")[1].strip().split("@")[0]
                    if name != "lo":
                        interfaces.append(name)

            if len(interfaces) >= 2:
                return True, f"Found {len(interfaces)} interfaces: {', '.join(interfaces)}"
            elif len(interfaces) == 1:
                return False, f"Only 1 interface found: {interfaces[0]} (need 2)"
            return False, "No network interfaces found"
        except Exception as e:
            return False, f"Cannot detect interfaces: {str(e)}"

    def _check_internet(self):
        """Check internet connectivity."""
        try:
            result = subprocess.run(
                ["ping", "-c", "1", "-W", "2", "8.8.8.8"],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                return True, "Internet connection available"
            return False, "No internet connection (required for installation)"
        except Exception as e:
            return False, f"Cannot check internet: {str(e)}"


class SystemCheckPage(QWizardPage):
    """Page to verify system requirements."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("System Requirements Check")
        self.setSubTitle("Verifying your system meets the minimum requirements")

        self._check_results = {}
        self._all_passed = False
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Check status group
        check_group = QGroupBox("System Checks")
        check_layout = QGridLayout(check_group)

        self.check_labels = {}
        checks = [
            ("os_version", "Operating System"),
            ("root", "Root Privileges"),
            ("ram", "Memory"),
            ("disk", "Disk Space"),
            ("network_interfaces", "Network Interfaces"),
            ("internet", "Internet Connection"),
        ]

        for row, (key, name) in enumerate(checks):
            label = QLabel(f"{name}:")
            label.setFont(QFont("Sans Serif", 10, QFont.Weight.Bold))
            check_layout.addWidget(label, row, 0)

            status_label = QLabel("Checking...")
            status_label.setProperty("check_key", key)
            check_layout.addWidget(status_label, row, 1)
            self.check_labels[key] = status_label

        layout.addWidget(check_group)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(len(checks))
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        # Summary label
        self.summary_label = QLabel("Click 'Next' to start checking system requirements.")
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet("font-weight: bold; padding: 10px;")
        layout.addWidget(self.summary_label)

        # Run checks button
        self.run_button = QPushButton("Run Checks")
        self.run_button.clicked.connect(self._run_checks)
        layout.addWidget(self.run_button)

        layout.addStretch()

    def initializePage(self):
        """Called when page is shown."""
        # Auto-run checks when page is shown
        self._run_checks()

    def _run_checks(self):
        """Run system checks in background thread."""
        self.run_button.setEnabled(False)
        self.progress_bar.setValue(0)
        self.summary_label.setText("Running system checks...")

        # Reset labels
        for label in self.check_labels.values():
            label.setText("Checking...")
            label.setStyleSheet("")

        # Start worker
        self.worker = SystemCheckWorker()
        self.worker.check_complete.connect(self._on_check_complete)
        self.worker.all_complete.connect(self._on_all_complete)
        self.worker.start()

    def _on_check_complete(self, check_name: str, passed: bool, message: str):
        """Handle individual check completion."""
        label = self.check_labels.get(check_name)
        if label:
            icon = "✅" if passed else "❌"
            label.setText(f"{icon} {message}")
            if passed:
                label.setStyleSheet("color: green;")
            else:
                label.setStyleSheet("color: red;")

        self._check_results[check_name] = (passed, message)
        self.progress_bar.setValue(self.progress_bar.value() + 1)

    def _on_all_complete(self, all_passed: bool):
        """Handle all checks completion."""
        self._all_passed = all_passed
        self.run_button.setEnabled(True)

        if all_passed:
            self.summary_label.setText("✅ All critical checks passed! Click 'Next' to continue.")
            self.summary_label.setStyleSheet("color: green; font-weight: bold; padding: 10px;")
            self.completeChanged.emit()
        else:
            failed = [name for name, (passed, _) in self._check_results.items() if not passed]
            self.summary_label.setText(
                f"❌ Some checks failed: {', '.join(failed)}\n"
                "Please fix the issues before continuing."
            )
            self.summary_label.setStyleSheet("color: red; font-weight: bold; padding: 10px;")

    def isComplete(self):
        """Check if page is complete."""
        return self._all_passed

    def get_results(self):
        """Get check results."""
        return self._check_results.copy()
