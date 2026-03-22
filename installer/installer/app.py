"""Application installation and migration management."""

import subprocess
import logging
from typing import Tuple, Optional
from pathlib import Path


logger = logging.getLogger(__name__)


class AppInstaller:
    """Handles application-level installation tasks."""

    def __init__(self, app_dir: str = "/opt/wifi-portal"):
        self.app_dir = Path(app_dir)
        self.venv_dir = self.app_dir / ".venv"
        self.venv_python = self.venv_dir / "bin" / "python"
        self.venv_pip = self.venv_dir / "bin" / "pip"
        self.venv_alembic = self.venv_dir / "bin" / "alembic"

    def run_migrations(self) -> Tuple[bool, str]:
        """Run database migrations with Alembic."""
        logger.info("Running database migrations...")
        try:
            result = subprocess.run(
                [str(self.venv_alembic), "upgrade", "head"],
                cwd=str(self.app_dir),
                capture_output=True,
                text=True,
                check=True
            )
            return True, f"Migrations applied:\n{result.stdout}"
        except subprocess.CalledProcessError as e:
            return False, f"Migration failed:\n{e.stderr}"

    def create_admin_user(self, username: str, password: str) -> Tuple[bool, str]:
        """Create admin user in the database."""
        logger.info(f"Creating admin user: {username}")
        try:
            # Create a temporary script to create the admin user
            script = f'''
import asyncio
from passlib.context import CryptContext
from sqlalchemy import create_engine, text
import os

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Get database URL from environment
db_url = os.environ.get("DATABASE_URL", "postgresql://wifi_portal:password@localhost/wifi_portal")
# Convert async URL to sync for this script
db_url = db_url.replace("+asyncpg", "")

engine = create_engine(db_url)

password_hash = pwd_context.hash("{password}")

with engine.connect() as conn:
    # Check if user exists
    result = conn.execute(text("SELECT id FROM admin_users WHERE username = :username"), {{"username": "{username}"}})
    if result.fetchone():
        # Update password
        conn.execute(text("UPDATE admin_users SET password_hash = :hash WHERE username = :username"), {{"hash": password_hash, "username": "{username}"}})
        print("Admin user password updated")
    else:
        # Create user
        conn.execute(text("INSERT INTO admin_users (username, password_hash, is_active) VALUES (:username, :hash, true)"), {{"username": "{username}", "hash": password_hash}})
        print("Admin user created")
    conn.commit()
'''

            script_path = self.app_dir / "create_admin.py"
            script_path.write_text(script)

            # Read .env file and set environment
            import os
            env = os.environ.copy()
            env_file = self.app_dir / ".env"
            if env_file.exists():
                for line in env_file.read_text().splitlines():
                    if "=" in line and not line.startswith("#"):
                        key, value = line.split("=", 1)
                        env[key.strip()] = value.strip()

            result = subprocess.run(
                [str(self.venv_python), str(script_path)],
                cwd=str(self.app_dir),
                capture_output=True,
                text=True,
                env=env,
                check=True
            )

            # Clean up script
            script_path.unlink()

            return True, result.stdout.strip()
        except subprocess.CalledProcessError as e:
            return False, f"Failed to create admin user:\n{e.stderr}"
        except Exception as e:
            return False, str(e)

    def start_service(self, service_name: str = "wifi-portal") -> Tuple[bool, str]:
        """Start the application service."""
        logger.info(f"Starting {service_name} service...")
        try:
            subprocess.run(
                ["systemctl", "start", service_name],
                capture_output=True,
                text=True,
                check=True
            )
            return True, f"Service {service_name} started"
        except subprocess.CalledProcessError as e:
            return False, f"Failed to start service: {e.stderr}"

    def stop_service(self, service_name: str = "wifi-portal") -> Tuple[bool, str]:
        """Stop the application service."""
        logger.info(f"Stopping {service_name} service...")
        try:
            subprocess.run(
                ["systemctl", "stop", service_name],
                capture_output=True,
                text=True
            )
            return True, f"Service {service_name} stopped"
        except subprocess.CalledProcessError as e:
            return False, f"Failed to stop service: {e.stderr}"

    def restart_service(self, service_name: str = "wifi-portal") -> Tuple[bool, str]:
        """Restart the application service."""
        logger.info(f"Restarting {service_name} service...")
        try:
            subprocess.run(
                ["systemctl", "restart", service_name],
                capture_output=True,
                text=True,
                check=True
            )
            return True, f"Service {service_name} restarted"
        except subprocess.CalledProcessError as e:
            return False, f"Failed to restart service: {e.stderr}"

    def get_service_status(self, service_name: str = "wifi-portal") -> Tuple[bool, str]:
        """Get the status of the application service."""
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

    def check_health(self, host: str = "localhost", port: int = 8080) -> Tuple[bool, str]:
        """Check application health endpoint."""
        import socket
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex((host, port))
            sock.close()
            if result == 0:
                return True, f"Application is listening on {host}:{port}"
            return False, f"Application is not listening on {host}:{port}"
        except Exception as e:
            return False, str(e)

    def get_logs(self, lines: int = 50, service_name: str = "wifi-portal") -> Tuple[bool, str]:
        """Get recent application logs."""
        try:
            result = subprocess.run(
                ["journalctl", "-u", service_name, "-n", str(lines), "--no-pager"],
                capture_output=True,
                text=True,
                check=True
            )
            return True, result.stdout
        except subprocess.CalledProcessError as e:
            return False, f"Failed to get logs: {e.stderr}"

    def pull_latest(self, repo_url: str = None, branch: str = "main") -> Tuple[bool, str]:
        """Pull latest code from git repository."""
        logger.info(f"Pulling latest code from {branch}...")
        try:
            if repo_url:
                # Clone if not exists
                result = subprocess.run(
                    ["git", "clone", "-b", branch, repo_url, "."],
                    cwd=str(self.app_dir),
                    capture_output=True,
                    text=True
                )
            else:
                # Pull if already cloned
                result = subprocess.run(
                    ["git", "pull", "origin", branch],
                    cwd=str(self.app_dir),
                    capture_output=True,
                    text=True,
                    check=True
                )
            return True, "Code updated"
        except subprocess.CalledProcessError as e:
            return False, f"Failed to pull code: {e.stderr}"

    def update_dependencies(self) -> Tuple[bool, str]:
        """Update Python dependencies."""
        logger.info("Updating Python dependencies...")
        try:
            requirements_file = self.app_dir / "requirements.txt"
            if requirements_file.exists():
                result = subprocess.run(
                    [str(self.venv_pip), "install", "-r", str(requirements_file), "--upgrade"],
                    cwd=str(self.app_dir),
                    capture_output=True,
                    text=True,
                    check=True
                )
                return True, "Dependencies updated"
            return False, "requirements.txt not found"
        except subprocess.CalledProcessError as e:
            return False, f"Failed to update dependencies: {e.stderr}"
