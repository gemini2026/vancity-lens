"""
VanCity Lens — Secrets Management (SEC-010)

Centralized secret loading with support for:
- Environment variables
- .env files
- Docker secrets (/run/secrets/*)

Priority order: Docker secrets > env vars > .env file > defaults (dev only)

Features:
- Read-once pattern: secrets cached in memory after initial load
- Production validation: fails fast if required secrets missing
- Secret masking: logging shows only first/last 4 chars
- Rotation support: reload_secrets() method for credential updates
- Type-safe accessors: get_database_url(), get_anthropic_key(), etc.
"""

import logging
import os
from pathlib import Path
from typing import Optional, Dict

from .secrets_config import SECRET_DEFINITIONS, SecretDefinition

logger = logging.getLogger(__name__)


class SecretsManager:
    """Centralized secrets loading and management."""

    def __init__(self, env_file: Optional[str] = None):
        """
        Initialize secrets manager.

        Args:
            env_file: Path to .env file (defaults to .env in project root).
                     Only loaded if file exists and not in production.
        """
        self._cache: Dict[str, Optional[str]] = {}
        self._loaded = False
        self._env_file = env_file or ".env"
        self._is_production = os.getenv("VANCITY_ENV", "development") == "production"

    def _load_env_file(self) -> Dict[str, str]:
        """
        Parse a simple .env file without external dependencies.

        Returns:
            Dict of key=value pairs parsed from .env file.
        """
        env_vars = {}
        env_path = Path(self._env_file)

        if not env_path.exists():
            return env_vars

        try:
            with open(env_path, "r") as f:
                for line in f:
                    line = line.strip()
                    # Skip empty lines and comments
                    if not line or line.startswith("#"):
                        continue

                    # Parse KEY=VALUE
                    if "=" in line:
                        key, value = line.split("=", 1)
                        key = key.strip()
                        value = value.strip()

                        # Remove quotes if present
                        if value.startswith('"') and value.endswith('"'):
                            value = value[1:-1]
                        elif value.startswith("'") and value.endswith("'"):
                            value = value[1:-1]

                        env_vars[key] = value
        except Exception as e:
            logger.warning(f"Failed to load .env file: {e}")

        return env_vars

    def _read_docker_secret(self, path: str) -> Optional[str]:
        """
        Read a Docker secret file.

        Args:
            path: Path to secret file (e.g., /run/secrets/anthropic_key)

        Returns:
            Secret value with whitespace trimmed, or None if file doesn't exist.
        """
        try:
            secret_path = Path(path)
            if secret_path.exists():
                value = secret_path.read_text().strip()
                return value if value else None
        except Exception as e:
            logger.warning(f"Failed to read Docker secret {path}: {e}")

        return None

    def _load_secret(self, definition: SecretDefinition) -> Optional[str]:
        """
        Load a single secret using priority order:
        1. Docker secret (/run/secrets/*)
        2. Environment variable
        3. .env file
        4. None (no default)

        Args:
            definition: Secret definition with metadata

        Returns:
            Secret value or None if not found
        """
        # 1. Try Docker secret first
        if definition.docker_secret_path:
            value = self._read_docker_secret(definition.docker_secret_path)
            if value:
                logger.debug(
                    f"Loaded secret '{definition.name}' from Docker secrets"
                )
                return value

        # 2. Try environment variable
        value = os.environ.get(definition.env_var)
        if value:
            logger.debug(
                f"Loaded secret '{definition.name}' from environment variable"
            )
            return value

        # 3. Try .env file (only if not production)
        if not self._is_production:
            env_vars = self._load_env_file()
            value = env_vars.get(definition.env_var)
            if value:
                logger.debug(f"Loaded secret '{definition.name}' from .env file")
                return value

        return None

    def _mask_secret(self, value: Optional[str]) -> str:
        """
        Mask a secret for logging (show first/last 4 chars only).

        Args:
            value: Secret value

        Returns:
            Masked string (e.g., 'sk-a...kY5X') or '<not-set>'
        """
        if not value:
            return "<not-set>"

        if len(value) <= 8:
            return "****"

        first_4 = value[:4]
        last_4 = value[-4:]
        return f"{first_4}...{last_4}"

    def load_secrets(self) -> None:
        """
        Load all secrets and cache in memory.

        In production, raises RuntimeError if any required secret is missing.
        In development, missing optional secrets are allowed.

        Raises:
            RuntimeError: In production, if required secrets are missing
        """
        if self._loaded:
            return

        missing_required = []

        for definition in SECRET_DEFINITIONS:
            value = self._load_secret(definition)
            self._cache[definition.name] = value

            if value:
                logger.debug(
                    f"Secret '{definition.name}': {self._mask_secret(value)}"
                )
            else:
                logger.debug(f"Secret '{definition.name}': <not-set>")

                if definition.required_in_production and self._is_production:
                    missing_required.append(definition.name)

        self._loaded = True

        # Fail fast in production if required secrets are missing
        if missing_required:
            msg = (
                f"Missing required secrets in production: {', '.join(missing_required)}. "
                f"Set via environment variables, .env file, or Docker secrets."
            )
            logger.error(msg)
            raise RuntimeError(msg)

        logger.info("All required secrets loaded successfully")

    def reload_secrets(self) -> None:
        """
        Reload secrets from sources (for credential rotation).

        Useful for picking up new values after Docker secret updates.
        """
        self._cache.clear()
        self._loaded = False
        self.load_secrets()

    def get_secret(self, name: str) -> Optional[str]:
        """
        Get a secret value by name.

        Args:
            name: Secret name (e.g., 'anthropic_key')

        Returns:
            Secret value or None if not set
        """
        if not self._loaded:
            self.load_secrets()

        return self._cache.get(name)

    # ── Type-safe accessors ────────────────────────────────────────

    def get_database_url(self) -> str:
        """
        Get DATABASE_URL.

        Returns:
            Connection string

        Raises:
            RuntimeError: In production if not set
        """
        if not self._loaded:
            self.load_secrets()

        value = self._cache.get("database_url")
        if not value and self._is_production:
            raise RuntimeError(
                "DATABASE_URL is required in production but not set. "
                "Set via environment variable, .env file, or Docker secret."
            )

        return value or ""

    def get_anthropic_key(self) -> str:
        """
        Get ANTHROPIC_API_KEY.

        Returns:
            API key

        Raises:
            RuntimeError: In production if not set
        """
        if not self._loaded:
            self.load_secrets()

        value = self._cache.get("anthropic_key")
        if not value and self._is_production:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is required in production but not set. "
                "Set via environment variable, .env file, or Docker secret."
            )

        return value or ""

    def get_cohere_key(self) -> str:
        """
        Get COHERE_API_KEY.

        Returns:
            API key

        Raises:
            RuntimeError: In production if not set
        """
        if not self._loaded:
            self.load_secrets()

        value = self._cache.get("cohere_key")
        if not value and self._is_production:
            raise RuntimeError(
                "COHERE_API_KEY is required in production but not set. "
                "Set via environment variable, .env file, or Docker secret."
            )

        return value or ""

    def get_admin_key(self) -> Optional[str]:
        """
        Get ADMIN_API_KEY (optional).

        Returns:
            API key or None if not set
        """
        if not self._loaded:
            self.load_secrets()

        return self._cache.get("admin_key")

    def get_mapbox_token(self) -> Optional[str]:
        """
        Get MAPBOX_TOKEN (optional).

        Returns:
            Token or None if not set
        """
        if not self._loaded:
            self.load_secrets()

        return self._cache.get("mapbox_token")

    def validate_production_secrets(self) -> None:
        """
        Explicit validation method for production secrets.

        This is called automatically by load_secrets() in production.
        Can be called manually to validate before any secret-dependent operations.

        Raises:
            RuntimeError: If any required secret is missing in production
        """
        if not self._is_production:
            return

        if not self._loaded:
            self.load_secrets()

        # Validation already happened in load_secrets()


# Global singleton instance
_secrets_manager: Optional[SecretsManager] = None


def get_secrets_manager(env_file: Optional[str] = None) -> SecretsManager:
    """
    Get or create global secrets manager singleton.

    Args:
        env_file: Path to .env file (only used on first call)

    Returns:
        SecretsManager instance
    """
    global _secrets_manager
    if _secrets_manager is None:
        _secrets_manager = SecretsManager(env_file=env_file)
    return _secrets_manager


def load_secrets(env_file: Optional[str] = None) -> None:
    """
    Load all secrets (initialization function).

    Typically called once at application startup.

    Args:
        env_file: Path to .env file (optional)

    Raises:
        RuntimeError: In production, if required secrets are missing
    """
    manager = get_secrets_manager(env_file=env_file)
    manager.load_secrets()
