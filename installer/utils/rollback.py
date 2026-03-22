"""Rollback management for installation steps."""

import subprocess
import logging
from typing import Callable, List, Optional, Tuple
from dataclasses import dataclass, field


logger = logging.getLogger(__name__)


@dataclass
class RollbackStep:
    """Represents a single rollback step."""
    name: str
    rollback_fn: Callable[[], Tuple[bool, str]]
    description: str = ""


class RollbackManager:
    """Manages rollback of installation steps in reverse order."""

    def __init__(self):
        self.completed_steps: List[RollbackStep] = []
        self.rolled_back: List[str] = []

    def register_step(
        self,
        name: str,
        rollback_fn: Callable[[], Tuple[bool, str]],
        description: str = ""
    ) -> None:
        """Register a completed step with its rollback function."""
        step = RollbackStep(
            name=name,
            rollback_fn=rollback_fn,
            description=description or name
        )
        self.completed_steps.append(step)
        logger.info(f"Registered rollback step: {name}")

    def rollback_all(self) -> Tuple[bool, List[str], List[str]]:
        """
        Execute all rollback steps in reverse order.

        Returns:
            Tuple of (success, successful_rollbacks, failed_rollbacks)
        """
        success = True
        failed = []
        successful = []

        # Reverse order - undo most recent changes first
        for step in reversed(self.completed_steps):
            logger.info(f"Rolling back: {step.name}")
            try:
                ok, msg = step.rollback_fn()
                if ok:
                    successful.append(step.name)
                    self.rolled_back.append(step.name)
                    logger.info(f"Rollback successful: {step.name}")
                else:
                    success = False
                    failed.append(f"{step.name}: {msg}")
                    logger.error(f"Rollback failed: {step.name} - {msg}")
            except Exception as e:
                success = False
                failed.append(f"{step.name}: {str(e)}")
                logger.exception(f"Rollback exception: {step.name}")

        return success, successful, failed

    def rollback_step(self, name: str) -> Tuple[bool, str]:
        """Rollback a specific step by name."""
        for step in self.completed_steps:
            if step.name == name and name not in self.rolled_back:
                try:
                    ok, msg = step.rollback_fn()
                    if ok:
                        self.rolled_back.append(name)
                    return ok, msg
                except Exception as e:
                    return False, str(e)
        return False, f"Step '{name}' not found or already rolled back"

    def clear(self) -> None:
        """Clear all registered steps (after successful installation)."""
        self.completed_steps.clear()
        self.rolled_back.clear()

    def get_pending_rollbacks(self) -> List[str]:
        """Get list of steps that haven't been rolled back."""
        return [
            step.name for step in self.completed_steps
            if step.name not in self.rolled_back
        ]


# Pre-defined rollback functions for common operations

def rollback_apt_packages(packages: List[str]) -> Tuple[bool, str]:
    """Rollback: Remove installed apt packages."""
    try:
        cmd = ["apt-get", "remove", "--purge", "-y"] + packages
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            return True, ""
        return False, result.stderr
    except Exception as e:
        return False, str(e)


def rollback_postgresql_database(db_name: str) -> Tuple[bool, str]:
    """Rollback: Drop PostgreSQL database."""
    try:
        result = subprocess.run(
            ["sudo", "-u", "postgres", "dropdb", "--if-exists", db_name],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            return True, ""
        return False, result.stderr
    except Exception as e:
        return False, str(e)


def rollback_postgresql_user(db_user: str) -> Tuple[bool, str]:
    """Rollback: Drop PostgreSQL user."""
    try:
        result = subprocess.run(
            ["sudo", "-u", "postgres", "dropuser", "--if-exists", db_user],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            return True, ""
        return False, result.stderr
    except Exception as e:
        return False, str(e)


def rollback_file(path: str) -> Tuple[bool, str]:
    """Rollback: Remove a file."""
    import os
    try:
        if os.path.exists(path):
            os.remove(path)
        return True, ""
    except Exception as e:
        return False, str(e)


def rollback_directory(path: str) -> Tuple[bool, str]:
    """Rollback: Remove a directory and its contents."""
    import shutil
    try:
        if os.path.exists(path):
            shutil.rmtree(path)
        return True, ""
    except Exception as e:
        return False, str(e)


def rollback_systemd_service(service_name: str) -> Tuple[bool, str]:
    """Rollback: Stop and disable systemd service."""
    try:
        subprocess.run(["systemctl", "stop", service_name], capture_output=True)
        subprocess.run(["systemctl", "disable", service_name], capture_output=True)
        return True, ""
    except Exception as e:
        return False, str(e)


def rollback_nftables_table(table_name: str = "captive_portal") -> Tuple[bool, str]:
    """Rollback: Flush and delete nftables table."""
    try:
        subprocess.run(
            ["nft", "flush", "table", "inet", table_name],
            capture_output=True
        )
        subprocess.run(
            ["nft", "delete", "table", "inet", table_name],
            capture_output=True
        )
        return True, ""
    except Exception as e:
        return False, str(e)


def rollback_dnsmasq_config(config_name: str = "captive-portal") -> Tuple[bool, str]:
    """Rollback: Remove dnsmasq configuration."""
    import os
    config_path = f"/etc/dnsmasq.d/{config_name}"
    try:
        if os.path.exists(config_path):
            os.remove(config_path)
            subprocess.run(["systemctl", "restart", "dnsmasq"], capture_output=True)
        return True, ""
    except Exception as e:
        return False, str(e)


# Need to import os for rollback functions
import os
