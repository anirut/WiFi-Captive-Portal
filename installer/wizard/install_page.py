"""Installation progress page."""

import logging
from PyQt6.QtWidgets import (
    QWizardPage,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QTextEdit,
    QPushButton,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QTextCursor

from ..installer.system import SystemInstaller
from ..installer.database import DatabaseInstaller
from ..installer.redis import RedisInstaller
from ..installer.network import NetworkConfigurator
from ..installer.app import AppInstaller
from ..utils.config import ConfigGenerator
from ..utils.rollback import RollbackManager


class InstallWorker(QThread):
    """Worker thread for installation process."""

    progress = pyqtSignal(int, str)  # percent, message
    log_message = pyqtSignal(str)  # log line
    finished_with_result = pyqtSignal(bool, str)  # success, message

    def __init__(self, mode: str, config: dict, parent=None):
        super().__init__(parent)
        self.mode = mode
        self.config = config
        self.rollback_manager = RollbackManager()

    def run(self):
        """Execute installation steps."""
        try:
            if self.mode == "install":
                self._run_install()
            elif self.mode == "update":
                self._run_update()
            elif self.mode == "reconfigure":
                self._run_reconfigure()
            elif self.mode == "uninstall":
                self._run_uninstall()
        except Exception as e:
            logging.exception("Installation error")
            self.finished_with_result.emit(False, str(e))

    def _run_install(self):
        """Run full installation."""
        self.log_message.emit("Starting installation...")
        self.progress.emit(0, "Initializing...")

        # Step 1: System packages (20%)
        self.progress.emit(5, "Installing system packages...")
        self.log_message.emit("Installing system packages...")
        system = SystemInstaller()

        ok, msg = system.update_apt()
        if not ok:
            self._fail(msg)
            return
        self.log_message.emit(f"  {msg}")

        ok, msg = system.install_system_packages()
        if not ok:
            self._fail(msg)
            return
        self.log_message.emit(f"  {msg}")
        self.rollback_manager.register_step("apt_packages", lambda: (True, ""))
        self.progress.emit(20, "System packages installed")

        # Step 2: PostgreSQL (40%)
        self.progress.emit(25, "Setting up PostgreSQL...")
        self.log_message.emit("Setting up PostgreSQL...")
        db = DatabaseInstaller(
            db_name=self.config.get("db_name", "wifi_portal"),
            db_user=self.config.get("db_user", "wifi_portal"),
            db_password=self.config.get("db_password", ""),
        )

        ok, msg = db.setup_complete(
            password=self.config.get("db_password")
        )
        if not ok:
            self._fail(msg)
            return
        self.log_message.emit(f"  {msg}")
        self.rollback_manager.register_step(
            "database",
            lambda: db.drop_database() and db.drop_user()
        )
        self.progress.emit(40, "PostgreSQL configured")

        # Step 3: Redis (50%)
        self.progress.emit(45, "Setting up Redis...")
        self.log_message.emit("Setting up Redis...")
        redis = RedisInstaller()

        ok, msg = redis.setup_complete()
        if not ok:
            self._fail(msg)
            return
        self.log_message.emit(f"  {msg}")
        self.progress.emit(50, "Redis configured")

        # Step 4: Application directory and venv (70%)
        self.progress.emit(55, "Setting up application...")
        self.log_message.emit("Creating application directory...")

        ok, msg = system.create_app_directory()
        if not ok:
            self._fail(msg)
            return
        self.log_message.emit(f"  {msg}")

        ok, msg = system.create_virtualenv()
        if not ok:
            self._fail(msg)
            return
        self.log_message.emit(f"  {msg}")
        self.rollback_manager.register_step(
            "venv",
            lambda: (True, "")  # Keep venv for potential reinstall
        )

        ok, msg = system.install_python_packages(
            requirements_file=self.config.get("requirements_file")
        )
        if not ok:
            self._fail(msg)
            return
        self.log_message.emit(f"  {msg}")
        self.progress.emit(70, "Application setup complete")

        # Step 5: Generate config (75%)
        self.progress.emit(72, "Generating configuration...")
        self.log_message.emit("Generating .env file...")

        config_gen = ConfigGenerator()
        full_config = config_gen.generate_default_config(
            db_user=self.config.get("db_user", "wifi_portal"),
            db_password=self.config.get("db_password"),
            wifi_interface=self.config.get("wifi_interface", "wlan0"),
            wan_interface=self.config.get("wan_interface", "eth0"),
            portal_ip=self.config.get("portal_ip", "192.168.4.1"),
            portal_port=self.config.get("portal_port", 8080),
            jwt_expire_hours=self.config.get("jwt_expire_hours", 24),
        )
        # Override with provided keys
        full_config["SECRET_KEY"] = self.config.get("secret_key", full_config["SECRET_KEY"])
        full_config["ENCRYPTION_KEY"] = self.config.get("encryption_key", full_config["ENCRYPTION_KEY"])

        ok, msg = config_gen.write_env_file(full_config)
        if not ok:
            self._fail(msg)
            return
        self.log_message.emit(f"  {msg}")
        self.rollback_manager.register_step(
            "env_file",
            lambda: (True, "")
        )
        self.progress.emit(75, "Configuration generated")

        # Step 6: Run migrations (85%)
        self.progress.emit(78, "Running database migrations...")
        self.log_message.emit("Running database migrations...")

        app = AppInstaller()
        ok, msg = app.run_migrations()
        if not ok:
            self._fail(msg)
            return
        self.log_message.emit(f"  {msg}")
        self.progress.emit(85, "Migrations complete")

        # Step 7: Create admin user (88%)
        self.progress.emit(86, "Creating admin user...")
        self.log_message.emit("Creating admin user...")

        ok, msg = app.create_admin_user(
            self.config.get("admin_username", "admin"),
            self.config.get("admin_password", "")
        )
        if not ok:
            self._fail(msg)
            return
        self.log_message.emit(f"  {msg}")
        self.progress.emit(88, "Admin user created")

        # Step 8: Network configuration (95%)
        self.progress.emit(90, "Configuring network...")
        self.log_message.emit("Configuring network rules...")

        network = NetworkConfigurator(
            wifi_interface=self.config.get("wifi_interface", "wlan0"),
            wan_interface=self.config.get("wan_interface", "eth0"),
            portal_ip=self.config.get("portal_ip", "192.168.4.1"),
            portal_port=self.config.get("portal_port", 8080),
            dhcp_start=self.config.get("dhcp_start", "192.168.4.10"),
            dhcp_end=self.config.get("dhcp_end", "192.168.4.254"),
        )

        ok, msg = network.setup_complete()
        if not ok:
            self._fail(msg)
            return
        self.log_message.emit(f"  {msg}")
        self.rollback_manager.register_step(
            "network",
            lambda: network.rollback()
        )
        self.progress.emit(95, "Network configured")

        # Step 9: Create and start service (100%)
        self.progress.emit(96, "Creating service...")
        self.log_message.emit("Creating systemd service...")

        ok, msg = system.create_systemd_service()
        if not ok:
            self._fail(msg)
            return
        self.log_message.emit(f"  {msg}")

        ok, msg = system.start_service()
        if not ok:
            self._fail(msg)
            return
        self.log_message.emit(f"  {msg}")
        self.rollback_manager.register_step(
            "service",
            lambda: system.stop_service()
        )

        self.progress.emit(100, "Installation complete!")
        self.log_message.emit("\n✅ Installation completed successfully!")
        self.finished_with_result.emit(True, "Installation completed successfully!")

    def _run_update(self):
        """Run update process."""
        self.log_message.emit("Starting update...")
        self.progress.emit(0, "Updating application...")

        app = AppInstaller()

        # Pull latest code
        self.progress.emit(30, "Pulling latest code...")
        self.log_message.emit("Pulling latest code...")
        ok, msg = app.pull_latest()
        if not ok:
            self._fail(msg)
            return
        self.log_message.emit(f"  {msg}")

        # Update dependencies
        self.progress.emit(60, "Updating dependencies...")
        self.log_message.emit("Updating Python dependencies...")
        ok, msg = app.update_dependencies()
        if not ok:
            self._fail(msg)
            return
        self.log_message.emit(f"  {msg}")

        # Run migrations
        self.progress.emit(80, "Running migrations...")
        self.log_message.emit("Running database migrations...")
        ok, msg = app.run_migrations()
        if not ok:
            self._fail(msg)
            return
        self.log_message.emit(f"  {msg}")

        # Restart service
        self.progress.emit(90, "Restarting service...")
        self.log_message.emit("Restarting service...")
        ok, msg = app.restart_service()
        if not ok:
            self._fail(msg)
            return
        self.log_message.emit(f"  {msg}")

        self.progress.emit(100, "Update complete!")
        self.log_message.emit("\n✅ Update completed successfully!")
        self.finished_with_result.emit(True, "Update completed successfully!")

    def _run_reconfigure(self):
        """Run reconfiguration process."""
        self.log_message.emit("Starting reconfiguration...")
        self.progress.emit(0, "Updating configuration...")

        # Update config file
        config_gen = ConfigGenerator()
        existing = config_gen.read_env_file()

        # Update with new values
        updates = {}
        if self.config.get("wifi_interface"):
            updates["WIFI_INTERFACE"] = self.config["wifi_interface"]
        if self.config.get("wan_interface"):
            updates["WAN_INTERFACE"] = self.config["wan_interface"]
        if self.config.get("portal_ip"):
            updates["PORTAL_IP"] = self.config["portal_ip"]
        if self.config.get("portal_port"):
            updates["PORTAL_PORT"] = str(self.config["portal_port"])

        if updates:
            ok, msg = config_gen.update_env_file(updates)
            if not ok:
                self._fail(msg)
                return
            self.log_message.emit(f"Configuration updated: {msg}")
            self.progress.emit(30, "Configuration updated")

        # Reconfigure network
        self.progress.emit(50, "Reconfiguring network...")
        self.log_message.emit("Reconfiguring network...")

        network = NetworkConfigurator(
            wifi_interface=self.config.get("wifi_interface", existing.get("WIFI_INTERFACE", "wlan0")),
            wan_interface=self.config.get("wan_interface", existing.get("WAN_INTERFACE", "eth0")),
            portal_ip=self.config.get("portal_ip", existing.get("PORTAL_IP", "192.168.4.1")),
            portal_port=self.config.get("portal_port", int(existing.get("PORTAL_PORT", "8080"))),
        )

        ok, msg = network.rollback()  # Remove old config first
        self.log_message.emit(f"  Removed old config: {msg}")

        ok, msg = network.setup_complete()
        if not ok:
            self._fail(msg)
            return
        self.log_message.emit(f"  {msg}")
        self.progress.emit(80, "Network reconfigured")

        # Restart service
        self.progress.emit(90, "Restarting service...")
        app = AppInstaller()
        ok, msg = app.restart_service()
        if not ok:
            self._fail(msg)
            return
        self.log_message.emit(f"  {msg}")

        self.progress.emit(100, "Reconfiguration complete!")
        self.log_message.emit("\n✅ Reconfiguration completed successfully!")
        self.finished_with_result.emit(True, "Reconfiguration completed successfully!")

    def _run_uninstall(self):
        """Run uninstallation process."""
        self.log_message.emit("Starting uninstallation...")
        self.progress.emit(0, "Stopping services...")

        # Stop services
        app = AppInstaller()
        ok, msg = app.stop_service()
        self.log_message.emit(f"  {msg}")

        system = SystemInstaller()
        ok, msg = system.stop_service("postgresql")
        self.log_message.emit(f"  {msg}")

        self.progress.emit(20, "Removing network configuration...")

        # Remove network config
        network = NetworkConfigurator()
        ok, msg = network.rollback()
        self.log_message.emit(f"  {msg}")

        self.progress.emit(40, "Removing database...")

        # Drop database
        db = DatabaseInstaller()
        ok, msg = db.drop_database()
        self.log_message.emit(f"  {msg}")
        ok, msg = db.drop_user()
        self.log_message.emit(f"  {msg}")

        self.progress.emit(60, "Removing application files...")

        # Remove application directory
        import shutil
        import os
        app_dir = "/opt/wifi-portal"
        if os.path.exists(app_dir):
            shutil.rmtree(app_dir)
            self.log_message.emit(f"  Removed {app_dir}")

        self.progress.emit(80, "Removing service...")

        # Remove systemd service
        service_path = "/etc/systemd/system/wifi-portal.service"
        if os.path.exists(service_path):
            os.remove(service_path)
            system.stop_service()  # Disable
            self.log_message.emit(f"  Removed {service_path}")

        self.progress.emit(100, "Uninstallation complete!")
        self.log_message.emit("\n✅ Uninstallation completed successfully!")
        self.finished_with_result.emit(True, "Uninstallation completed successfully!")

    def _fail(self, message: str):
        """Handle failure with rollback."""
        self.log_message.emit(f"\n❌ Error: {message}")
        self.log_message.emit("Rolling back changes...")
        success, successful, failed = self.rollback_manager.rollback_all()
        if failed:
            self.log_message.emit(f"  Rollback errors: {failed}")
        else:
            self.log_message.emit("  Rollback completed")
        self.finished_with_result.emit(False, message)


class InstallPage(QWizardPage):
    """Page showing installation progress."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Installation Progress")
        self.setSubTitle("Please wait while the installation completes")

        self._is_complete = False
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # Current step label
        self.step_label = QLabel("Preparing...")
        self.step_label.setFont(QFont("Sans Serif", 11, QFont.Weight.Bold))
        layout.addWidget(self.step_label)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        # Log output
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Monospace", 9))
        self.log_text.setMaximumHeight(300)
        layout.addWidget(self.log_text)

        layout.addStretch()

    def initializePage(self):
        """Called when page is shown - start installation."""
        # Get configuration from previous pages
        wizard = self.wizard()

        # Get mode
        mode = "install"
        if hasattr(wizard, 'get_mode'):
            mode = wizard.get_mode()

        # Collect config from wizard fields
        config = {
            "wifi_interface": self.field("wifi_interface") or "wlan0",
            "wan_interface": self.field("wan_interface") or "eth0",
            "portal_ip": self.field("portal_ip") or "192.168.4.1",
            "portal_port": int(self.field("portal_port") or 8080),
            "dhcp_start": self.field("dhcp_start") or "192.168.4.10",
            "dhcp_end": self.field("dhcp_end") or "192.168.4.254",
            "admin_username": self.field("admin_username") or "admin",
            "admin_password": self.field("admin_password") or "",
            "secret_key": self.field("secret_key") or "",
            "encryption_key": self.field("encryption_key") or "",
            "jwt_expire_hours": int(self.field("jwt_expire_hours") or 24),
            "db_name": "wifi_portal",
            "db_user": "wifi_portal",
            "db_password": None,  # Will be auto-generated
        }

        # Start worker
        self.worker = InstallWorker(mode, config)
        self.worker.progress.connect(self._on_progress)
        self.worker.log_message.connect(self._on_log_message)
        self.worker.finished_with_result.connect(self._on_finished)
        self.worker.start()

    def _on_progress(self, percent: int, message: str):
        """Handle progress update."""
        self.progress_bar.setValue(percent)
        self.step_label.setText(message)

    def _on_log_message(self, message: str):
        """Handle log message."""
        self.log_text.append(message)
        # Scroll to bottom
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.log_text.setTextCursor(cursor)

    def _on_finished(self, success: bool, message: str):
        """Handle installation completion."""
        self._is_complete = success
        self.completeChanged.emit()

        if success:
            self.step_label.setText("✅ " + message)
            self.step_label.setStyleSheet("color: green;")
        else:
            self.step_label.setText("❌ " + message)
            self.step_label.setStyleSheet("color: red;")

    def isComplete(self):
        """Check if page is complete."""
        return self._is_complete

    def nextId(self):
        """Always go to finish page."""
        return -1  # This is handled by wizard
