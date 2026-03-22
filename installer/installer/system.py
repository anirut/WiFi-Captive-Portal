"""System package installation and service management."""

import subprocess
import shutil
import logging
from typing import List, Tuple, Optional
from pathlib import Path


logger = logging.getLogger(__name__)


# Required system packages
SYSTEM_PACKAGES = [
    "python3",
    "python3-pip",
    "python3-venv",
    "python3-dev",
    "postgresql",
    "postgresql-contrib",
    "redis-server",
    "nftables",
    "dnsmasq",
    "iproute2",
    "curl",
    "git",
]

PYTHON_PACKAGES = [
    "fastapi",
    "uvicorn",
    "sqlalchemy",
    "asyncpg",
    "alembic",
    "redis",
    "pydantic",
    "pydantic-settings",
    "python-jose",
    "passlib",
    "bcrypt",
    "cryptography",
    "apscheduler",
    "jinja2",
    "reportlab",
    "qrcode",
    "pillow",
    "htmx",
]


class SystemInstaller:
    """Handles system-level package installation and service management."""

    def __init__(self, app_dir: str = "/opt/wifi-portal"):
        self.app_dir = Path(app_dir)
        self.venv_dir = self.app_dir / ".venv"

    def update_apt(self) -> Tuple[bool, str]:
        """Update apt package lists."""
        logger.info("Updating apt package lists...")
        try:
            result = subprocess.run(
                ["apt-get", "update"],
                capture_output=True,
                text=True,
                check=True
            )
            return True, "Package lists updated"
        except subprocess.CalledProcessError as e:
            return False, f"Failed to update apt: {e.stderr}"

    def install_system_packages(self, packages: List[str] = None) -> Tuple[bool, str]:
        """Install system packages via apt."""
        if packages is None:
            packages = SYSTEM_PACKAGES

        logger.info(f"Installing system packages: {', '.join(packages)}")
        try:
            # Use DEBIAN_FRONTEND=noninteractive for silent install
            env = {"DEBIAN_FRONTEND": "noninteractive"}
            env.update(subprocess.os.environ)

            result = subprocess.run(
                ["apt-get", "install", "-y"] + packages,
                capture_output=True,
                text=True,
                env=env,
                check=True
            )
            return True, f"Installed {len(packages)} packages"
        except subprocess.CalledProcessError as e:
            return False, f"Failed to install packages: {e.stderr}"

    def create_app_directory(self) -> Tuple[bool, str]:
        """Create the application directory structure."""
        logger.info(f"Creating application directory: {self.app_dir}")
        try:
            self.app_dir.mkdir(parents=True, exist_ok=True)

            # Create subdirectories
            (self.app_dir / "app").mkdir(exist_ok=True)
            (self.app_dir / "logs").mkdir(exist_ok=True)
            (self.app_dir / "data").mkdir(exist_ok=True)

            return True, str(self.app_dir)
        except Exception as e:
            return False, str(e)

    def create_virtualenv(self) -> Tuple[bool, str]:
        """Create Python virtual environment."""
        logger.info(f"Creating virtual environment: {self.venv_dir}")
        try:
            result = subprocess.run(
                ["python3", "-m", "venv", str(self.venv_dir)],
                capture_output=True,
                text=True,
                check=True
            )
            return True, str(self.venv_dir)
        except subprocess.CalledProcessError as e:
            return False, f"Failed to create venv: {e.stderr}"

    def install_python_packages(self, packages: List[str] = None, requirements_file: str = None) -> Tuple[bool, str]:
        """Install Python packages in virtual environment."""
        pip_path = self.venv_dir / "bin" / "pip"

        if packages is None:
            packages = PYTHON_PACKAGES

        logger.info(f"Installing Python packages: {len(packages)} packages")
        try:
            if requirements_file:
                # Install from requirements file
                result = subprocess.run(
                    [str(pip_path), "install", "-r", requirements_file],
                    capture_output=True,
                    text=True,
                    check=True
                )
            else:
                # Install packages directly
                result = subprocess.run(
                    [str(pip_path), "install"] + packages,
                    capture_output=True,
                    text=True,
                    check=True
                )
            return True, f"Installed {len(packages)} Python packages"
        except subprocess.CalledProcessError as e:
            return False, f"Failed to install Python packages: {e.stderr}"

    def copy_application_files(self, source_dir: str) -> Tuple[bool, str]:
        """Copy application files to install directory."""
        import shutil

        source = Path(source_dir)
        logger.info(f"Copying application files from {source} to {self.app_dir}")

        try:
            # Copy app directory
            if (source / "app").exists():
                if (self.app_dir / "app").exists():
                    shutil.rmtree(self.app_dir / "app")
                shutil.copytree(source / "app", self.app_dir / "app")

            # Copy alembic directory
            if (source / "alembic").exists():
                if (self.app_dir / "alembic").exists():
                    shutil.rmtree(self.app_dir / "alembic")
                shutil.copytree(source / "alembic", self.app_dir / "alembic")

            # Copy alembic.ini
            if (source / "alembic.ini").exists():
                shutil.copy(source / "alembic.ini", self.app_dir / "alembic.ini")

            # Copy requirements.txt
            if (source / "requirements.txt").exists():
                shutil.copy(source / "requirements.txt", self.app_dir / "requirements.txt")

            return True, "Application files copied"
        except Exception as e:
            return False, str(e)

    def create_systemd_service(self, service_name: str = "wifi-portal") -> Tuple[bool, str]:
        """Create and enable systemd service."""
        service_content = f"""[Unit]
Description=WiFi Captive Portal
After=network.target postgresql.service redis.service

[Service]
Type=simple
User=root
WorkingDirectory={self.app_dir}
ExecStart={self.venv_dir}/bin/uvicorn app.main:app --host 0.0.0.0 --port 8080
Restart=always
RestartSec=5
StandardOutput=append:{self.app_dir}/logs/portal.log
StandardError=append:{self.app_dir}/logs/portal.log

[Install]
WantedBy=multi-user.target
"""

        service_path = Path(f"/etc/systemd/system/{service_name}.service")

        logger.info(f"Creating systemd service: {service_path}")
        try:
            service_path.write_text(service_content)

            # Reload systemd
            subprocess.run(["systemctl", "daemon-reload"], capture_output=True, check=True)

            # Enable service (but don't start yet)
            subprocess.run(["systemctl", "enable", service_name], capture_output=True, check=True)

            return True, str(service_path)
        except Exception as e:
            return False, str(e)

    def start_service(self, service_name: str = "wifi-portal") -> Tuple[bool, str]:
        """Start a systemd service."""
        logger.info(f"Starting service: {service_name}")
        try:
            result = subprocess.run(
                ["systemctl", "start", service_name],
                capture_output=True,
                text=True,
                check=True
            )
            return True, f"Service {service_name} started"
        except subprocess.CalledProcessError as e:
            return False, f"Failed to start service: {e.stderr}"

    def stop_service(self, service_name: str = "wifi-portal") -> Tuple[bool, str]:
        """Stop a systemd service."""
        logger.info(f"Stopping service: {service_name}")
        try:
            subprocess.run(
                ["systemctl", "stop", service_name],
                capture_output=True,
                text=True
            )
            return True, f"Service {service_name} stopped"
        except subprocess.CalledProcessError as e:
            return False, f"Failed to stop service: {e.stderr}"

    def get_service_status(self, service_name: str = "wifi-portal") -> Tuple[bool, str]:
        """Get status of a systemd service."""
        try:
            result = subprocess.run(
                ["systemctl", "is-active", service_name],
                capture_output=True,
                text=True
            )
            is_active = result.returncode == 0
            return is_active, "active" if is_active else "inactive"
        except Exception:
            return False, "unknown"

    def is_root(self) -> bool:
        """Check if running as root."""
        return subprocess.os.geteuid() == 0
