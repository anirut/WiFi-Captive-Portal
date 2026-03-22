"""Redis installation and configuration."""

import subprocess
import logging
from typing import Tuple


logger = logging.getLogger(__name__)


class RedisInstaller:
    """Handles Redis installation and configuration."""

    def is_redis_installed(self) -> bool:
        """Check if Redis is installed."""
        try:
            result = subprocess.run(
                ["which", "redis-server"],
                capture_output=True,
                text=True
            )
            return result.returncode == 0
        except Exception:
            return False

    def is_redis_running(self) -> bool:
        """Check if Redis service is running."""
        try:
            result = subprocess.run(
                ["systemctl", "is-active", "redis-server"],
                capture_output=True,
                text=True
            )
            return result.returncode == 0
        except Exception:
            return False

    def start_redis(self) -> Tuple[bool, str]:
        """Start Redis service."""
        logger.info("Starting Redis service...")
        try:
            subprocess.run(
                ["systemctl", "start", "redis-server"],
                capture_output=True,
                text=True,
                check=True
            )
            subprocess.run(
                ["systemctl", "enable", "redis-server"],
                capture_output=True,
                text=True,
                check=True
            )
            return True, "Redis started"
        except subprocess.CalledProcessError as e:
            return False, f"Failed to start Redis: {e.stderr}"

    def stop_redis(self) -> Tuple[bool, str]:
        """Stop Redis service."""
        logger.info("Stopping Redis service...")
        try:
            subprocess.run(
                ["systemctl", "stop", "redis-server"],
                capture_output=True,
                text=True
            )
            return True, "Redis stopped"
        except subprocess.CalledProcessError as e:
            return False, f"Failed to stop Redis: {e.stderr}"

    def test_connection(self, host: str = "localhost", port: int = 6379) -> Tuple[bool, str]:
        """Test Redis connection using redis-cli."""
        logger.info(f"Testing Redis connection at {host}:{port}")
        try:
            result = subprocess.run(
                ["redis-cli", "-h", host, "-p", str(port), "ping"],
                capture_output=True,
                text=True,
                check=True
            )
            if "PONG" in result.stdout:
                return True, "Redis connection successful"
            return False, f"Unexpected response: {result.stdout}"
        except subprocess.CalledProcessError as e:
            return False, f"Redis connection failed: {e.stderr}"

    def configure_redis(self, maxmemory: str = "256mb", maxmemory_policy: str = "allkeys-lru") -> Tuple[bool, str]:
        """Configure Redis settings."""
        logger.info(f"Configuring Redis: maxmemory={maxmemory}, policy={maxmemory_policy}")
        try:
            redis_conf = "/etc/redis/redis.conf"

            # Read current config
            with open(redis_conf, "r") as f:
                lines = f.readlines()

            # Update settings
            updated_lines = []
            settings = {
                "maxmemory": f"{maxmemory}",
                "maxmemory-policy": maxmemory_policy,
                "bind": "127.0.0.1 ::1",  # Keep localhost binding for security
            }

            settings_updated = {k: False for k in settings}

            for line in lines:
                stripped = line.strip()
                updated = False
                for setting, value in settings.items():
                    if stripped.startswith(f"{setting} ") or stripped.startswith(f"# {setting} "):
                        updated_lines.append(f"{setting} {value}\n")
                        settings_updated[setting] = True
                        updated = True
                        break
                if not updated:
                    updated_lines.append(line)

            # Add any missing settings
            for setting, value in settings.items():
                if not settings_updated[setting]:
                    updated_lines.append(f"{setting} {value}\n")

            # Write back
            with open(redis_conf, "w") as f:
                f.writelines(updated_lines)

            # Restart Redis to apply changes
            subprocess.run(
                ["systemctl", "restart", "redis-server"],
                capture_output=True,
                text=True,
                check=True
            )

            return True, "Redis configured and restarted"
        except Exception as e:
            return False, f"Failed to configure Redis: {str(e)}"

    def flush_all(self) -> Tuple[bool, str]:
        """Flush all data from Redis (for rollback/cleanup)."""
        logger.info("Flushing all data from Redis...")
        try:
            result = subprocess.run(
                ["redis-cli", "FLUSHALL"],
                capture_output=True,
                text=True,
                check=True
            )
            return True, "Redis data flushed"
        except subprocess.CalledProcessError as e:
            return False, f"Failed to flush Redis: {e.stderr}"

    def setup_complete(self) -> Tuple[bool, str]:
        """Complete Redis setup: start service, test connection."""
        results = []

        # Start Redis
        if not self.is_redis_running():
            ok, msg = self.start_redis()
            if not ok:
                return False, msg
            results.append(msg)
        else:
            results.append("Redis already running")

        # Test connection
        ok, msg = self.test_connection()
        if not ok:
            return False, msg
        results.append(msg)

        return True, "\n".join(results)
