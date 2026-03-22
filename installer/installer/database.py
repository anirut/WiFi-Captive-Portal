"""PostgreSQL database installation and configuration."""

import subprocess
import logging
from typing import Tuple, Optional
from pathlib import Path


logger = logging.getLogger(__name__)


class DatabaseInstaller:
    """Handles PostgreSQL installation and configuration."""

    def __init__(
        self,
        db_name: str = "wifi_portal",
        db_user: str = "wifi_portal",
        db_password: str = None,
    ):
        self.db_name = db_name
        self.db_user = db_user
        self.db_password = db_password

    def is_postgresql_installed(self) -> bool:
        """Check if PostgreSQL is installed."""
        try:
            result = subprocess.run(
                ["which", "psql"],
                capture_output=True,
                text=True
            )
            return result.returncode == 0
        except Exception:
            return False

    def is_postgresql_running(self) -> bool:
        """Check if PostgreSQL service is running."""
        try:
            result = subprocess.run(
                ["systemctl", "is-active", "postgresql"],
                capture_output=True,
                text=True
            )
            return result.returncode == 0
        except Exception:
            return False

    def start_postgresql(self) -> Tuple[bool, str]:
        """Start PostgreSQL service."""
        logger.info("Starting PostgreSQL service...")
        try:
            subprocess.run(
                ["systemctl", "start", "postgresql"],
                capture_output=True,
                text=True,
                check=True
            )
            subprocess.run(
                ["systemctl", "enable", "postgresql"],
                capture_output=True,
                text=True,
                check=True
            )
            return True, "PostgreSQL started"
        except subprocess.CalledProcessError as e:
            return False, f"Failed to start PostgreSQL: {e.stderr}"

    def database_exists(self, db_name: str = None) -> bool:
        """Check if database exists."""
        db_name = db_name or self.db_name
        try:
            result = subprocess.run(
                ["sudo", "-u", "postgres", "psql", "-lqt"],
                capture_output=True,
                text=True,
                check=True
            )
            # Check if database name is in the list
            return db_name in result.stdout.split()
        except Exception:
            return False

    def user_exists(self, username: str = None) -> bool:
        """Check if database user exists."""
        username = username or self.db_user
        try:
            result = subprocess.run(
                ["sudo", "-u", "postgres", "psql", "-t", "-c",
                 f"SELECT 1 FROM pg_roles WHERE rolname='{username}'"],
                capture_output=True,
                text=True,
                check=True
            )
            return "1" in result.stdout
        except Exception:
            return False

    def create_user(self, username: str = None, password: str = None) -> Tuple[bool, str]:
        """Create database user."""
        username = username or self.db_user
        password = password or self.db_password

        if not password:
            return False, "Password is required"

        logger.info(f"Creating database user: {username}")
        try:
            # Check if user already exists
            if self.user_exists(username):
                logger.info(f"User {username} already exists, updating password")
                sql = f"ALTER USER {username} WITH PASSWORD '{password}';"
            else:
                sql = f"CREATE USER {username} WITH PASSWORD '{password}';"

            result = subprocess.run(
                ["sudo", "-u", "postgres", "psql", "-c", sql],
                capture_output=True,
                text=True,
                check=True
            )
            return True, f"User {username} created/updated"
        except subprocess.CalledProcessError as e:
            return False, f"Failed to create user: {e.stderr}"

    def create_database(self, db_name: str = None, owner: str = None) -> Tuple[bool, str]:
        """Create database."""
        db_name = db_name or self.db_name
        owner = owner or self.db_user

        logger.info(f"Creating database: {db_name}")
        try:
            # Check if database already exists
            if self.database_exists(db_name):
                logger.info(f"Database {db_name} already exists")
                return True, f"Database {db_name} already exists"

            result = subprocess.run(
                ["sudo", "-u", "postgres", "createdb", "-O", owner, db_name],
                capture_output=True,
                text=True,
                check=True
            )
            return True, f"Database {db_name} created"
        except subprocess.CalledProcessError as e:
            return False, f"Failed to create database: {e.stderr}"

    def grant_privileges(self, db_name: str = None, username: str = None) -> Tuple[bool, str]:
        """Grant all privileges on database to user."""
        db_name = db_name or self.db_name
        username = username or self.db_user

        logger.info(f"Granting privileges on {db_name} to {username}")
        try:
            sql = f"GRANT ALL PRIVILEGES ON DATABASE {db_name} TO {username};"
            result = subprocess.run(
                ["sudo", "-u", "postgres", "psql", "-c", sql],
                capture_output=True,
                text=True,
                check=True
            )
            return True, f"Privileges granted on {db_name}"
        except subprocess.CalledProcessError as e:
            return False, f"Failed to grant privileges: {e.stderr}"

    def test_connection(self, db_name: str = None, username: str = None, password: str = None) -> Tuple[bool, str]:
        """Test database connection."""
        db_name = db_name or self.db_name
        username = username or self.db_user
        password = password or self.db_password

        if not password:
            return False, "Password is required"

        logger.info(f"Testing connection to {db_name} as {username}")
        try:
            # Use PGPASSWORD environment variable for non-interactive auth
            import os
            env = os.environ.copy()
            env["PGPASSWORD"] = password

            result = subprocess.run(
                ["psql", "-h", "localhost", "-U", username, "-d", db_name, "-c", "SELECT 1;"],
                capture_output=True,
                text=True,
                env=env,
                check=True
            )
            return True, "Connection successful"
        except subprocess.CalledProcessError as e:
            return False, f"Connection failed: {e.stderr}"

    def drop_database(self, db_name: str = None) -> Tuple[bool, str]:
        """Drop database (for rollback)."""
        db_name = db_name or self.db_name
        logger.info(f"Dropping database: {db_name}")
        try:
            result = subprocess.run(
                ["sudo", "-u", "postgres", "dropdb", "--if-exists", db_name],
                capture_output=True,
                text=True,
                check=True
            )
            return True, f"Database {db_name} dropped"
        except subprocess.CalledProcessError as e:
            return False, f"Failed to drop database: {e.stderr}"

    def drop_user(self, username: str = None) -> Tuple[bool, str]:
        """Drop user (for rollback)."""
        username = username or self.db_user
        logger.info(f"Dropping user: {username}")
        try:
            result = subprocess.run(
                ["sudo", "-u", "postgres", "dropuser", "--if-exists", username],
                capture_output=True,
                text=True,
                check=True
            )
            return True, f"User {username} dropped"
        except subprocess.CalledProcessError as e:
            return False, f"Failed to drop user: {e.stderr}"

    def setup_complete(self, db_name: str = None, username: str = None, password: str = None) -> Tuple[bool, str]:
        """Complete database setup: start service, create user, create database, grant privileges."""
        results = []

        # Start PostgreSQL
        if not self.is_postgresql_running():
            ok, msg = self.start_postgresql()
            if not ok:
                return False, msg
            results.append(msg)

        # Create user
        ok, msg = self.create_user(username, password)
        if not ok:
            return False, msg
        results.append(msg)

        # Create database
        ok, msg = self.create_database(db_name, username)
        if not ok:
            return False, msg
        results.append(msg)

        # Grant privileges
        ok, msg = self.grant_privileges(db_name, username)
        if not ok:
            return False, msg
        results.append(msg)

        # Test connection
        ok, msg = self.test_connection(db_name, username, password)
        if not ok:
            return False, msg
        results.append(msg)

        return True, "\n".join(results)
