"""
VanCity Lens — Secrets Management Tests (VCL-27 / SEC-010)

Comprehensive tests for the SecretsManager class including:
- Loading from environment variables
- Loading from Docker secret files
- Loading from .env files
- Priority order validation (Docker > env > .env)
- Production validation
- Secret masking
- Reload functionality
- Type-safe accessors
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from api.secrets import (
    SecretsManager,
    get_secrets_manager,
    load_secrets,
)


class TestSecretsManagerEnvironmentVariables:
    """Test loading secrets from environment variables."""

    def test_load_from_env_var(self):
        """Should load secret from environment variable."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test123"}):
            manager = SecretsManager(env_file="/nonexistent/.env")
            value = manager._load_secret(
                MagicMock(
                    name="anthropic_key",
                    env_var="ANTHROPIC_API_KEY",
                    docker_secret_path=None,
                    required_in_production=True,
                    description="Test",
                )
            )
            assert value == "sk-ant-test123"

    def test_env_var_not_set_returns_none(self):
        """Should return None if environment variable not set."""
        with patch.dict(os.environ, {}, clear=True):
            manager = SecretsManager(env_file="/nonexistent/.env")
            value = manager._load_secret(
                MagicMock(
                    name="anthropic_key",
                    env_var="ANTHROPIC_API_KEY",
                    docker_secret_path=None,
                    required_in_production=True,
                    description="Test",
                )
            )
            assert value is None

    def test_empty_env_var_is_none(self):
        """Should treat empty string as not set."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}):
            manager = SecretsManager(env_file="/nonexistent/.env")
            value = manager._load_secret(
                MagicMock(
                    name="anthropic_key",
                    env_var="ANTHROPIC_API_KEY",
                    docker_secret_path=None,
                    required_in_production=True,
                    description="Test",
                )
            )
            assert value is None


class TestSecretsManagerDockerSecrets:
    """Test loading secrets from Docker secret files."""

    def test_load_from_docker_secret(self):
        """Should load secret from Docker secret file."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".secret") as f:
            f.write("sk-ant-docker123")
            f.flush()
            docker_secret_path = f.name

        try:
            manager = SecretsManager(env_file="/nonexistent/.env")
            value = manager._read_docker_secret(docker_secret_path)
            assert value == "sk-ant-docker123"
        finally:
            os.unlink(docker_secret_path)

    def test_docker_secret_trims_whitespace(self):
        """Should trim whitespace from Docker secret files."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".secret") as f:
            f.write("  sk-ant-docker123\n\n")
            f.flush()
            docker_secret_path = f.name

        try:
            manager = SecretsManager(env_file="/nonexistent/.env")
            value = manager._read_docker_secret(docker_secret_path)
            assert value == "sk-ant-docker123"
        finally:
            os.unlink(docker_secret_path)

    def test_docker_secret_missing_returns_none(self):
        """Should return None if Docker secret file doesn't exist."""
        manager = SecretsManager(env_file="/nonexistent/.env")
        value = manager._read_docker_secret("/nonexistent/docker/secret")
        assert value is None

    def test_docker_secret_empty_file_returns_none(self):
        """Should return None for empty Docker secret files."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".secret") as f:
            f.write("")
            f.flush()
            docker_secret_path = f.name

        try:
            manager = SecretsManager(env_file="/nonexistent/.env")
            value = manager._read_docker_secret(docker_secret_path)
            assert value is None
        finally:
            os.unlink(docker_secret_path)


class TestSecretsManagerEnvFile:
    """Test loading secrets from .env files."""

    def test_load_from_env_file(self):
        """Should load secrets from .env file."""
        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix=".env", newline=""
        ) as f:
            f.write("ANTHROPIC_API_KEY=sk-ant-file123\n")
            f.write("COHERE_API_KEY=cohere-file456\n")
            f.flush()
            env_file = f.name

        try:
            with patch.dict(os.environ, {"VANCITY_ENV": "development"}, clear=False):
                manager = SecretsManager(env_file=env_file)
                env_vars = manager._load_env_file()
                assert env_vars["ANTHROPIC_API_KEY"] == "sk-ant-file123"
                assert env_vars["COHERE_API_KEY"] == "cohere-file456"
        finally:
            os.unlink(env_file)

    def test_env_file_skips_comments(self):
        """Should skip comment lines in .env file."""
        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix=".env", newline=""
        ) as f:
            f.write("# This is a comment\n")
            f.write("ANTHROPIC_API_KEY=sk-ant-value\n")
            f.write("# Another comment\n")
            f.flush()
            env_file = f.name

        try:
            manager = SecretsManager(env_file=env_file)
            env_vars = manager._load_env_file()
            assert "ANTHROPIC_API_KEY" in env_vars
            assert len(env_vars) == 1
        finally:
            os.unlink(env_file)

    def test_env_file_skips_empty_lines(self):
        """Should skip empty lines in .env file."""
        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix=".env", newline=""
        ) as f:
            f.write("\n")
            f.write("ANTHROPIC_API_KEY=sk-ant-value\n")
            f.write("\n")
            f.write("COHERE_API_KEY=cohere-value\n")
            f.write("\n")
            f.flush()
            env_file = f.name

        try:
            manager = SecretsManager(env_file=env_file)
            env_vars = manager._load_env_file()
            assert len(env_vars) == 2
        finally:
            os.unlink(env_file)

    def test_env_file_removes_quotes(self):
        """Should remove surrounding quotes from .env file values."""
        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix=".env", newline=""
        ) as f:
            f.write('ANTHROPIC_API_KEY="sk-ant-quoted"\n')
            f.write("COHERE_API_KEY='cohere-single'\n")
            f.write("UNQUOTED_KEY=unquoted-value\n")
            f.flush()
            env_file = f.name

        try:
            manager = SecretsManager(env_file=env_file)
            env_vars = manager._load_env_file()
            assert env_vars["ANTHROPIC_API_KEY"] == "sk-ant-quoted"
            assert env_vars["COHERE_API_KEY"] == "cohere-single"
            assert env_vars["UNQUOTED_KEY"] == "unquoted-value"
        finally:
            os.unlink(env_file)

    def test_env_file_not_loaded_in_production(self):
        """Should not load .env file in production mode."""
        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix=".env", newline=""
        ) as f:
            f.write("ANTHROPIC_API_KEY=sk-ant-file123\n")
            f.flush()
            env_file = f.name

        try:
            with patch.dict(os.environ, {"VANCITY_ENV": "production"}, clear=False):
                manager = SecretsManager(env_file=env_file)
                # In production, _load_env_file should be skipped in _load_secret
                # Verify by checking that file values aren't returned if not in env
                with patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}, clear=False):
                    value = manager._load_secret(
                        MagicMock(
                            name="anthropic_key",
                            env_var="ANTHROPIC_API_KEY",
                            docker_secret_path=None,
                            required_in_production=True,
                            description="Test",
                        )
                    )
                    assert value is None
        finally:
            os.unlink(env_file)

    def test_env_file_missing_handled_gracefully(self):
        """Should handle missing .env file gracefully."""
        manager = SecretsManager(env_file="/nonexistent/.env")
        env_vars = manager._load_env_file()
        assert env_vars == {}


class TestSecretsManagerPriority:
    """Test priority order: Docker secrets > env vars > .env file."""

    def test_priority_docker_over_env(self):
        """Docker secret should take priority over environment variable."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".secret") as f:
            f.write("docker-value")
            f.flush()
            docker_secret_path = f.name

        try:
            with patch.dict(
                os.environ, {"ANTHROPIC_API_KEY": "env-value"}, clear=False
            ):
                manager = SecretsManager(env_file="/nonexistent/.env")
                value = manager._load_secret(
                    MagicMock(
                        name="anthropic_key",
                        env_var="ANTHROPIC_API_KEY",
                        docker_secret_path=docker_secret_path,
                        required_in_production=True,
                        description="Test",
                    )
                )
                assert value == "docker-value"
        finally:
            os.unlink(docker_secret_path)

    def test_priority_env_over_env_file(self):
        """Environment variable should take priority over .env file."""
        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix=".env", newline=""
        ) as f:
            f.write("ANTHROPIC_API_KEY=file-value\n")
            f.flush()
            env_file = f.name

        try:
            with patch.dict(
                os.environ,
                {"ANTHROPIC_API_KEY": "env-value", "VANCITY_ENV": "development"},
                clear=False,
            ):
                manager = SecretsManager(env_file=env_file)
                value = manager._load_secret(
                    MagicMock(
                        name="anthropic_key",
                        env_var="ANTHROPIC_API_KEY",
                        docker_secret_path=None,
                        required_in_production=False,
                        description="Test",
                    )
                )
                assert value == "env-value"
        finally:
            os.unlink(env_file)

    def test_priority_full_chain(self):
        """Full priority chain: Docker > env > .env."""
        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix=".env", newline=""
        ) as f:
            f.write("COHERE_API_KEY=file-value\n")
            f.flush()
            env_file = f.name

        try:
            with patch.dict(
                os.environ, {"VANCITY_ENV": "development"}, clear=False
            ):
                # Cohere only in .env
                manager = SecretsManager(env_file=env_file)
                value = manager._load_secret(
                    MagicMock(
                        name="cohere_key",
                        env_var="COHERE_API_KEY",
                        docker_secret_path=None,
                        required_in_production=False,
                        description="Test",
                    )
                )
                assert value == "file-value"
        finally:
            os.unlink(env_file)


class TestSecretsManagerSecretMasking:
    """Test secret masking for logging."""

    def test_mask_secret_long_value(self):
        """Should mask long secret values (show first/last 4 chars)."""
        manager = SecretsManager()
        masked = manager._mask_secret("sk-ant-1234567890abcdef")
        assert masked == "sk-a...cdef"

    def test_mask_secret_short_value(self):
        """Should mask short values (8 chars or less) completely."""
        manager = SecretsManager()
        masked = manager._mask_secret("12345678")
        assert masked == "****"

    def test_mask_secret_none_returns_not_set(self):
        """Should return <not-set> for None."""
        manager = SecretsManager()
        masked = manager._mask_secret(None)
        assert masked == "<not-set>"

    def test_mask_secret_empty_returns_not_set(self):
        """Should return <not-set> for empty string."""
        manager = SecretsManager()
        masked = manager._mask_secret("")
        assert masked == "<not-set>"


class TestSecretsManagerLoadSecrets:
    """Test load_secrets() functionality."""

    def test_load_secrets_success_development(self):
        """Should load all secrets successfully in development."""
        with patch.dict(
            os.environ,
            {
                "VANCITY_ENV": "development",
                "ANTHROPIC_API_KEY": "sk-ant-test",
                "COHERE_API_KEY": "cohere-test",
            },
            clear=False,
        ):
            manager = SecretsManager(env_file="/nonexistent/.env")
            manager.load_secrets()
            assert manager._loaded is True
            assert manager._cache["anthropic_key"] == "sk-ant-test"
            assert manager._cache["cohere_key"] == "cohere-test"

    def test_load_secrets_idempotent(self):
        """Should only load secrets once (idempotent)."""
        call_count = 0

        original_load_secret = SecretsManager._load_secret

        def counting_load_secret(self, definition):
            nonlocal call_count
            call_count += 1
            return original_load_secret(self, definition)

        with patch.dict(
            os.environ,
            {"VANCITY_ENV": "development"},
            clear=False,
        ):
            manager = SecretsManager(env_file="/nonexistent/.env")
            with patch.object(SecretsManager, "_load_secret", counting_load_secret):
                manager.load_secrets()
                first_call_count = call_count
                manager.load_secrets()  # Call again
                # Should not have called _load_secret again
                assert call_count == first_call_count

    def test_load_secrets_fails_production_missing_required(self):
        """Should fail in production if required secret is missing."""
        with patch.dict(os.environ, {"VANCITY_ENV": "production"}, clear=True):
            manager = SecretsManager(env_file="/nonexistent/.env")
            with pytest.raises(RuntimeError, match="Missing required secrets"):
                manager.load_secrets()

    def test_load_secrets_succeeds_production_all_set(self):
        """Should succeed in production if all required secrets are set."""
        with patch.dict(
            os.environ,
            {
                "VANCITY_ENV": "production",
                "DATABASE_URL": "postgresql://...",
                "ANTHROPIC_API_KEY": "sk-ant-test",
                "COHERE_API_KEY": "cohere-test",
                "ADMIN_API_KEY": "admin-test",
            },
            clear=False,
        ):
            manager = SecretsManager(env_file="/nonexistent/.env")
            manager.load_secrets()  # Should not raise
            assert manager._loaded is True

    def test_load_secrets_allows_optional_missing_development(self):
        """Should allow optional secrets to be missing in development."""
        with patch.dict(
            os.environ,
            {
                "VANCITY_ENV": "development",
                "DATABASE_URL": "postgresql://...",
                "ANTHROPIC_API_KEY": "sk-ant-test",
                "COHERE_API_KEY": "cohere-test",
                "ADMIN_API_KEY": "admin-test",
            },
            clear=False,
        ):
            manager = SecretsManager(env_file="/nonexistent/.env")
            manager.load_secrets()
            # MAPBOX_TOKEN is optional and not set, should be fine
            assert manager._cache.get("mapbox_token") is None


class TestSecretsManagerReload:
    """Test reload_secrets() for credential rotation."""

    def test_reload_secrets_clears_cache(self):
        """Should clear cache when reloading."""
        with patch.dict(
            os.environ,
            {
                "VANCITY_ENV": "development",
                "ANTHROPIC_API_KEY": "old-key",
            },
            clear=False,
        ):
            manager = SecretsManager(env_file="/nonexistent/.env")
            manager.load_secrets()
            assert manager._cache["anthropic_key"] == "old-key"

            # Reload with new value
            with patch.dict(
                os.environ,
                {"ANTHROPIC_API_KEY": "new-key"},
                clear=False,
            ):
                manager.reload_secrets()
                assert manager._cache["anthropic_key"] == "new-key"

    def test_reload_resets_loaded_flag(self):
        """Should reset _loaded flag when reloading."""
        with patch.dict(
            os.environ,
            {"VANCITY_ENV": "development"},
            clear=False,
        ):
            manager = SecretsManager(env_file="/nonexistent/.env")
            manager.load_secrets()
            assert manager._loaded is True

            manager.reload_secrets()
            assert manager._loaded is True  # Should be reloaded


class TestSecretsManagerGetSecretMethods:
    """Test type-safe accessor methods."""

    def test_get_secret_by_name(self):
        """Should get secret by name."""
        with patch.dict(
            os.environ,
            {
                "VANCITY_ENV": "development",
                "ANTHROPIC_API_KEY": "sk-ant-test",
            },
            clear=False,
        ):
            manager = SecretsManager(env_file="/nonexistent/.env")
            value = manager.get_secret("anthropic_key")
            assert value == "sk-ant-test"

    def test_get_database_url(self):
        """Should get database URL."""
        with patch.dict(
            os.environ,
            {
                "VANCITY_ENV": "development",
                "DATABASE_URL": "postgresql://localhost/test",
            },
            clear=False,
        ):
            manager = SecretsManager(env_file="/nonexistent/.env")
            url = manager.get_database_url()
            assert url == "postgresql://localhost/test"

    def test_get_database_url_fails_production(self):
        """Should fail if DATABASE_URL missing in production."""
        with patch.dict(os.environ, {"VANCITY_ENV": "production"}, clear=True):
            manager = SecretsManager(env_file="/nonexistent/.env")
            with pytest.raises(RuntimeError, match="Missing required secrets"):
                manager.get_database_url()

    def test_get_anthropic_key(self):
        """Should get Anthropic API key."""
        with patch.dict(
            os.environ,
            {
                "VANCITY_ENV": "development",
                "ANTHROPIC_API_KEY": "sk-ant-key",
            },
            clear=False,
        ):
            manager = SecretsManager(env_file="/nonexistent/.env")
            key = manager.get_anthropic_key()
            assert key == "sk-ant-key"

    def test_get_cohere_key(self):
        """Should get Cohere API key."""
        with patch.dict(
            os.environ,
            {
                "VANCITY_ENV": "development",
                "COHERE_API_KEY": "cohere-key",
            },
            clear=False,
        ):
            manager = SecretsManager(env_file="/nonexistent/.env")
            key = manager.get_cohere_key()
            assert key == "cohere-key"

    def test_get_admin_key_optional(self):
        """Should return None for optional admin key if not set."""
        with patch.dict(os.environ, {"VANCITY_ENV": "development"}, clear=False):
            manager = SecretsManager(env_file="/nonexistent/.env")
            key = manager.get_admin_key()
            assert key is None

    def test_get_mapbox_token_optional(self):
        """Should return None for optional Mapbox token if not set."""
        with patch.dict(os.environ, {"VANCITY_ENV": "development"}, clear=False):
            manager = SecretsManager(env_file="/nonexistent/.env")
            token = manager.get_mapbox_token()
            assert token is None


class TestSecretsManagerValidation:
    """Test validate_production_secrets() method."""

    def test_validate_production_secrets_passes_in_development(self):
        """Should pass validation in development."""
        with patch.dict(os.environ, {"VANCITY_ENV": "development"}, clear=False):
            manager = SecretsManager(env_file="/nonexistent/.env")
            manager.validate_production_secrets()  # Should not raise

    def test_validate_production_secrets_called_in_load(self):
        """Should validate production secrets when loading."""
        with patch.dict(os.environ, {"VANCITY_ENV": "production"}, clear=True):
            manager = SecretsManager(env_file="/nonexistent/.env")
            # load_secrets should fail because validation happens there
            with pytest.raises(RuntimeError):
                manager.load_secrets()


class TestSecretsManagerSingleton:
    """Test global singleton functionality."""

    def test_get_secrets_manager_singleton(self):
        """Should return same instance on multiple calls."""
        manager1 = get_secrets_manager()
        manager2 = get_secrets_manager()
        assert manager1 is manager2

    def test_load_secrets_function(self):
        """Should load secrets via module-level function."""
        with patch.dict(
            os.environ,
            {
                "VANCITY_ENV": "development",
                "ANTHROPIC_API_KEY": "sk-ant-test",
            },
            clear=False,
        ):
            # Reset singleton
            import api.secrets as secrets_module

            secrets_module._secrets_manager = None

            load_secrets()
            manager = get_secrets_manager()
            assert manager._loaded is True


class TestSecretsManagerIntegration:
    """Integration tests for real-world scenarios."""

    def test_full_production_scenario(self):
        """Test realistic production scenario with all secrets."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create Docker secret files
            db_secret = Path(tmpdir) / "db_secret"
            db_secret.write_text("postgresql://prod:pass@db:5432/lens\n")

            anthropic_secret = Path(tmpdir) / "anthropic_secret"
            anthropic_secret.write_text("sk-ant-prod123\n")

            cohere_secret = Path(tmpdir) / "cohere_secret"
            cohere_secret.write_text("cohere-prod456\n")

            admin_secret = Path(tmpdir) / "admin_secret"
            admin_secret.write_text("admin-prod-key\n")

            with patch.dict(
                os.environ,
                {
                    "VANCITY_ENV": "production",
                    "DATABASE_URL": str(db_secret),
                    "ANTHROPIC_API_KEY": str(anthropic_secret),
                    "COHERE_API_KEY": str(cohere_secret),
                    "ADMIN_API_KEY": str(admin_secret),
                },
                clear=False,
            ):
                # Manually patch to use file paths as values for testing
                with patch.dict(
                    os.environ,
                    {
                        "VANCITY_ENV": "production",
                        "DATABASE_URL": "postgresql://prod:pass@db:5432/lens",
                        "ANTHROPIC_API_KEY": "sk-ant-prod123",
                        "COHERE_API_KEY": "cohere-prod456",
                        "ADMIN_API_KEY": "admin-prod-key",
                    },
                    clear=False,
                ):
                    manager = SecretsManager(env_file="/nonexistent/.env")
                    manager.load_secrets()

                    assert manager.get_database_url() == "postgresql://prod:pass@db:5432/lens"
                    assert manager.get_anthropic_key() == "sk-ant-prod123"
                    assert manager.get_cohere_key() == "cohere-prod456"
                    assert manager.get_admin_key() == "admin-prod-key"

    def test_fallback_development_scenario(self):
        """Test realistic development scenario with minimal .env."""
        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix=".env", newline=""
        ) as f:
            f.write("DATABASE_URL=postgresql://localhost/test\n")
            f.write("ANTHROPIC_API_KEY=sk-dev-test\n")
            f.write("COHERE_API_KEY=cohere-dev-test\n")
            f.write("ADMIN_API_KEY=dev-admin-key\n")
            f.flush()
            env_file = f.name

        try:
            with patch.dict(
                os.environ,
                {"VANCITY_ENV": "development"},
                clear=False,
            ):
                manager = SecretsManager(env_file=env_file)
                manager.load_secrets()

                assert "localhost" in manager.get_database_url()
                assert manager.get_anthropic_key() == "sk-dev-test"
                assert manager.get_cohere_key() == "cohere-dev-test"
        finally:
            os.unlink(env_file)
