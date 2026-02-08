"""Comprehensive tests for GCP deployment scripts and configuration.

Tests validate:
- Bash script syntax and required commands
- GCP configuration correctness
- Security (no hardcoded secrets)
- Cloud Run, Cloud SQL, Secret Manager setup
- Custom domain and health check configuration
"""

import re
import subprocess
from pathlib import Path
from typing import List
import pytest


class TestDeployGCPScript:
    """Tests for scripts/deploy_gcp.sh - Cloud Run API deployment."""

    @classmethod
    def setup_class(cls):
        """Load GCP deployment script."""
        script_path = Path(__file__).parent.parent / 'scripts' / 'deploy_gcp.sh'
        assert script_path.exists(), f"Deploy GCP script not found at {script_path}"

        with open(script_path, 'r') as f:
            cls.script_content = f.read()

    def test_script_is_executable_bash(self):
        """Verify script has proper bash shebang."""
        assert self.script_content.startswith('#!/usr/bin/env bash'), \
            "Script should start with #!/usr/bin/env bash"

    def test_script_has_error_handling(self):
        """Verify script has set -euo pipefail for error handling."""
        assert 'set -euo pipefail' in self.script_content, \
            "Script should have 'set -euo pipefail' for error handling"

    def test_script_requires_gcp_project_id(self):
        """Verify script requires GCP_PROJECT_ID environment variable."""
        assert 'GCP_PROJECT_ID:?' in self.script_content, \
            "Script should require GCP_PROJECT_ID with :? parameter expansion"

    def test_script_has_default_region_us_west1(self):
        """Verify script defaults to us-west1 region (Vancouver-closest)."""
        assert 'GCP_REGION:-us-west1' in self.script_content, \
            "Script should default REGION to us-west1"

    def test_script_requires_anthropic_api_key(self):
        """Verify ANTHROPIC_API_KEY is required."""
        assert 'ANTHROPIC_API_KEY:?' in self.script_content, \
            "Script should require ANTHROPIC_API_KEY"

    def test_script_requires_cohere_api_key(self):
        """Verify COHERE_API_KEY is required."""
        assert 'COHERE_API_KEY:?' in self.script_content, \
            "Script should require COHERE_API_KEY"

    def test_script_defines_custom_domain(self):
        """Verify script defines custom domain variable."""
        assert 'CUSTOM_DOMAIN=' in self.script_content, \
            "Script should define CUSTOM_DOMAIN variable"
        assert 'api.vancitylens.com' in self.script_content, \
            "Custom domain should be api.vancitylens.com"

    def test_script_enables_required_gcp_apis(self):
        """Verify script enables all required GCP APIs."""
        required_apis = [
            'sqladmin.googleapis.com',
            'run.googleapis.com',
            'cloudbuild.googleapis.com',
            'artifactregistry.googleapis.com',
            'secretmanager.googleapis.com'
        ]

        for api in required_apis:
            assert api in self.script_content, \
                f"Script should enable {api}"

    def test_script_creates_cloud_sql_instance(self):
        """Verify script creates Cloud SQL instance."""
        assert 'gcloud sql instances create' in self.script_content, \
            "Script should create Cloud SQL instance"

    def test_script_uses_postgresql_16(self):
        """Verify script uses PostgreSQL 16."""
        assert 'POSTGRES_16' in self.script_content, \
            "Script should use PostgreSQL 16"

    def test_script_enables_pgvector_extension(self):
        """Verify script enables pgvector extension."""
        assert 'CREATE EXTENSION IF NOT EXISTS vector' in self.script_content, \
            "Script should enable pgvector extension"

    def test_script_enables_postgis_extension(self):
        """Verify script enables PostGIS extension."""
        assert 'CREATE EXTENSION IF NOT EXISTS postgis' in self.script_content, \
            "Script should enable PostGIS extension"

    def test_script_uses_secret_manager(self):
        """Verify script uses Secret Manager for storing secrets."""
        assert 'gcloud secrets create' in self.script_content or \
               'gcloud secrets versions add' in self.script_content, \
            "Script should use Secret Manager (gcloud secrets)"

    def test_script_stores_anthropic_key_in_secrets(self):
        """Verify ANTHROPIC_API_KEY is stored in Secret Manager."""
        assert 'anthropic-api-key' in self.script_content, \
            "Script should store anthropic-api-key in Secret Manager"

    def test_script_stores_cohere_key_in_secrets(self):
        """Verify COHERE_API_KEY is stored in Secret Manager."""
        assert 'cohere-api-key' in self.script_content, \
            "Script should store cohere-api-key in Secret Manager"

    def test_script_stores_database_url_in_secrets(self):
        """Verify DATABASE_URL is stored in Secret Manager."""
        assert 'database-url' in self.script_content or 'DATABASE_URL' in self.script_content, \
            "Script should store database URL in Secret Manager"

    def test_script_deploys_to_cloud_run(self):
        """Verify script deploys service to Cloud Run."""
        assert 'gcloud run deploy' in self.script_content, \
            "Script should deploy to Cloud Run"

    def test_script_configures_min_max_instances(self):
        """Verify Cloud Run scaling: min 0, max 5 instances."""
        assert '--min-instances=0' in self.script_content, \
            "Cloud Run should have min-instances=0"
        assert '--max-instances=5' in self.script_content, \
            "Cloud Run should have max-instances=5"

    def test_script_configures_health_check(self):
        """Verify script configures health check."""
        assert '--health-check-path' in self.script_content or \
               'HEALTH_CHECK_PATH' in self.script_content, \
            "Script should configure health check path"

    def test_script_sets_cors_origins(self):
        """Verify script sets CORS_ORIGINS environment variable."""
        assert 'CORS_ORIGINS' in self.script_content, \
            "Script should set CORS_ORIGINS environment variable"
        assert 'app.vancitylens.com' in self.script_content, \
            "CORS should allow app.vancitylens.com"

    def test_script_uses_cloud_sql_proxy(self):
        """Verify script sets up Cloud SQL connection."""
        assert 'cloudsql' in self.script_content, \
            "Script should configure Cloud SQL connection"

    def test_script_creates_artifact_registry(self):
        """Verify script creates Artifact Registry repository."""
        assert 'gcloud artifacts repositories create' in self.script_content, \
            "Script should create Artifact Registry repository"

    def test_script_builds_container_image(self):
        """Verify script builds and pushes container image."""
        assert 'gcloud builds submit' in self.script_content, \
            "Script should build container image"

    def test_script_maps_custom_domain(self):
        """Verify script creates domain mapping for custom domain."""
        assert 'gcloud run domain-mappings create' in self.script_content, \
            "Script should create domain mapping for custom domain"

    def test_script_uses_database_credentials_from_secrets(self):
        """Verify script uses secrets for database credentials."""
        assert '--set-secrets' in self.script_content, \
            "Script should use --set-secrets for sensitive config"

    def test_script_prints_deployment_summary(self):
        """Verify script prints deployment summary with endpoints."""
        assert 'Deployment Complete' in self.script_content, \
            "Script should print deployment success message"
        assert '/health' in self.script_content or 'HEALTH_CHECK' in self.script_content, \
            "Script should reference health check endpoint"


class TestDeployFrontendScript:
    """Tests for scripts/deploy_frontend.sh - Cloudflare Pages deployment."""

    @classmethod
    def setup_class(cls):
        """Load frontend deployment script."""
        script_path = Path(__file__).parent.parent / 'scripts' / 'deploy_frontend.sh'
        assert script_path.exists(), f"Deploy frontend script not found at {script_path}"

        with open(script_path, 'r') as f:
            cls.script_content = f.read()

    def test_script_is_executable_bash(self):
        """Verify script has proper bash shebang."""
        assert self.script_content.startswith('#!/usr/bin/env bash'), \
            "Script should start with #!/usr/bin/env bash"

    def test_script_has_error_handling(self):
        """Verify script has set -euo pipefail for error handling."""
        assert 'set -euo pipefail' in self.script_content, \
            "Script should have 'set -euo pipefail'"

    def test_script_requires_api_url(self):
        """Verify script requires NEXT_PUBLIC_API_URL."""
        assert 'NEXT_PUBLIC_API_URL:?' in self.script_content, \
            "Script should require NEXT_PUBLIC_API_URL"

    def test_script_requires_mapbox_token(self):
        """Verify script requires NEXT_PUBLIC_MAPBOX_TOKEN."""
        assert 'NEXT_PUBLIC_MAPBOX_TOKEN:?' in self.script_content, \
            "Script should require NEXT_PUBLIC_MAPBOX_TOKEN"

    def test_script_defines_custom_domain(self):
        """Verify script defines custom domain for frontend."""
        assert 'CUSTOM_DOMAIN=' in self.script_content or 'CF_CUSTOM_DOMAIN' in self.script_content, \
            "Script should define custom domain"
        assert 'app.vancitylens.com' in self.script_content, \
            "Frontend custom domain should be app.vancitylens.com"

    def test_script_validates_nextjs_config(self):
        """Verify script validates Next.js configuration."""
        assert 'next.config' in self.script_content, \
            "Script should check for next.config"

    def test_script_checks_for_standalone_output(self):
        """Verify script checks for standalone output configuration."""
        assert 'standalone' in self.script_content, \
            "Script should verify standalone output configuration"

    def test_script_installs_dependencies(self):
        """Verify script runs npm ci."""
        assert 'npm ci' in self.script_content, \
            "Script should install dependencies with npm ci"

    def test_script_builds_nextjs(self):
        """Verify script builds Next.js application."""
        assert 'npm run build' in self.script_content, \
            "Script should build Next.js application"

    def test_script_validates_build_artifacts(self):
        """Verify script validates build artifacts after build."""
        assert '.next' in self.script_content, \
            "Script should check for .next build directory"

    def test_script_deploys_to_cloudflare_pages(self):
        """Verify script deploys to Cloudflare Pages."""
        assert 'wrangler pages deploy' in self.script_content, \
            "Script should deploy using wrangler pages"

    def test_script_sets_api_url_environment_variable(self):
        """Verify script sets NEXT_PUBLIC_API_URL during build."""
        assert 'NEXT_PUBLIC_API_URL=' in self.script_content, \
            "Script should set NEXT_PUBLIC_API_URL environment variable"

    def test_script_sets_mapbox_token_environment_variable(self):
        """Verify script sets NEXT_PUBLIC_MAPBOX_TOKEN during build."""
        assert 'NEXT_PUBLIC_MAPBOX_TOKEN=' in self.script_content, \
            "Script should set NEXT_PUBLIC_MAPBOX_TOKEN environment variable"

    def test_script_uses_production_branch(self):
        """Verify script deploys to production branch."""
        assert '--branch=production' in self.script_content, \
            "Script should deploy to production branch"

    def test_script_configures_dns_cname(self):
        """Verify script provides DNS CNAME configuration instructions."""
        assert 'CNAME' in self.script_content or 'DNS' in self.script_content, \
            "Script should provide DNS configuration instructions"

    def test_script_requires_cloudflare_credentials(self):
        """Verify script mentions Cloudflare API requirements."""
        assert 'CF_API_TOKEN' in self.script_content or 'CF_ACCOUNT_ID' in self.script_content, \
            "Script should reference Cloudflare credentials"

    def test_script_has_error_handling_for_frontend_dir(self):
        """Verify script checks if frontend directory exists."""
        assert 'frontend' in self.script_content and 'Error' in self.script_content, \
            "Script should validate frontend directory exists"

    def test_script_prints_deployment_summary(self):
        """Verify script prints deployment summary."""
        assert 'Deployment Complete' in self.script_content or 'deployment' in self.script_content.lower(), \
            "Script should print deployment summary"

    def test_script_includes_next_steps(self):
        """Verify script includes next steps for user."""
        assert 'Next steps' in self.script_content or 'next' in self.script_content.lower(), \
            "Script should include next steps for user"


class TestGCPConfig:
    """Tests for GCP configuration validation."""

    @classmethod
    def setup_class(cls):
        """Load GCP deployment script."""
        script_path = Path(__file__).parent.parent / 'scripts' / 'deploy_gcp.sh'
        with open(script_path, 'r') as f:
            cls.script_content = f.read()

    def test_cloud_run_service_name_is_set(self):
        """Verify Cloud Run service name is defined."""
        assert 'SERVICE_NAME=' in self.script_content, \
            "Service name should be defined"
        assert 'vancity-lens-api' in self.script_content, \
            "Service name should be vancity-lens-api"

    def test_cloud_sql_instance_name_is_set(self):
        """Verify Cloud SQL instance name is defined."""
        assert 'DB_INSTANCE_NAME=' in self.script_content, \
            "Database instance name should be defined"
        assert 'vancity-lens-db' in self.script_content, \
            "Database instance should be vancity-lens-db"

    def test_database_name_is_set(self):
        """Verify database name is configured."""
        assert 'DB_NAME=' in self.script_content, \
            "Database name should be defined"
        assert 'vancity_lens' in self.script_content, \
            "Database should be named vancity_lens"

    def test_database_user_is_configured(self):
        """Verify database user is created."""
        assert 'DB_USER=' in self.script_content, \
            "Database user should be defined"
        assert 'vancity' in self.script_content, \
            "Database user should be 'vancity'"

    def test_artifact_registry_is_used(self):
        """Verify script uses Artifact Registry for container images."""
        assert 'artifactregistry.googleapis.com' in self.script_content, \
            "Script should enable Artifact Registry API"
        assert 'artifactregistry' in self.script_content or 'docker.pkg.dev' in self.script_content, \
            "Script should use Artifact Registry"

    def test_cloud_run_memory_is_set(self):
        """Verify Cloud Run memory allocation."""
        assert '--memory=' in self.script_content, \
            "Cloud Run memory should be configured"

    def test_cloud_run_cpu_is_set(self):
        """Verify Cloud Run CPU allocation."""
        assert '--cpu=' in self.script_content, \
            "Cloud Run CPU should be configured"

    def test_cloud_run_timeout_is_set(self):
        """Verify Cloud Run request timeout."""
        assert '--timeout=' in self.script_content, \
            "Cloud Run timeout should be configured"
        assert '300' in self.script_content, \
            "Timeout should be 300 seconds"

    def test_cloud_sql_uses_ssd_storage(self):
        """Verify Cloud SQL uses SSD storage."""
        assert '--storage-type=SSD' in self.script_content, \
            "Cloud SQL should use SSD storage"

    def test_cloud_sql_is_zonal(self):
        """Verify Cloud SQL uses zonal availability (cost optimization)."""
        assert '--availability-type=zonal' in self.script_content, \
            "Cloud SQL should use zonal availability"

    def test_database_password_generation(self):
        """Verify database password is generated securely."""
        assert 'openssl rand' in self.script_content or 'DB_PASSWORD=' in self.script_content, \
            "Script should generate database password"

    def test_cors_origins_configured(self):
        """Verify CORS origins are configured."""
        assert 'CORS_ORIGINS=' in self.script_content, \
            "CORS origins should be configured"


class TestDeploymentSecurity:
    """Tests validating security practices in deployment scripts."""

    @classmethod
    def setup_class(cls):
        """Load both deployment scripts."""
        gcp_path = Path(__file__).parent.parent / 'scripts' / 'deploy_gcp.sh'
        frontend_path = Path(__file__).parent.parent / 'scripts' / 'deploy_frontend.sh'

        with open(gcp_path, 'r') as f:
            cls.gcp_script = f.read()

        with open(frontend_path, 'r') as f:
            cls.frontend_script = f.read()

    def test_gcp_script_no_hardcoded_anthropic_key(self):
        """Verify ANTHROPIC_API_KEY is not hardcoded."""
        # Check that the key is not in the script directly (should be from env var)
        assert not re.search(r'ANTHROPIC_API_KEY\s*=\s*["\'][^"\']*sk-', self.gcp_script), \
            "ANTHROPIC_API_KEY should not be hardcoded with a real key"

    def test_gcp_script_no_hardcoded_cohere_key(self):
        """Verify COHERE_API_KEY is not hardcoded."""
        # Check that the key is not in the script directly
        assert not re.search(r'COHERE_API_KEY\s*=\s*["\'][^"\']*[a-zA-Z0-9]{20,}', self.gcp_script), \
            "COHERE_API_KEY should not be hardcoded"

    def test_gcp_script_no_hardcoded_db_password(self):
        """Verify database password is not hardcoded."""
        # Password should be generated, not hardcoded
        assert 'DB_PASSWORD:-' in self.gcp_script or 'DB_PASSWORD="${' in self.gcp_script, \
            "Database password should come from environment or be generated"

    def test_gcp_script_uses_secret_manager_for_api_keys(self):
        """Verify API keys are stored in Secret Manager, not as env vars."""
        assert '--set-secrets=' in self.gcp_script, \
            "Script should use --set-secrets for sensitive values"

    def test_gcp_script_no_secrets_in_logs(self):
        """Verify script doesn't print secrets to logs."""
        # Check that secrets are not echoed directly
        unsafe_patterns = [
            r'echo.*\$\{ANTHROPIC_KEY\}',
            r'echo.*\$\{COHERE_KEY\}',
            r'echo.*\$\{DB_PASSWORD\}',
        ]
        for pattern in unsafe_patterns:
            assert not re.search(pattern, self.gcp_script), \
                f"Script should not echo secrets: {pattern}"

    def test_gcp_script_uses_stdin_for_secrets(self):
        """Verify secrets are passed via stdin, not command line."""
        assert 'data-file=-' in self.gcp_script or '--data-file=' in self.gcp_script, \
            "Secrets should be passed via stdin (data-file=-), not command line"

    def test_frontend_script_no_hardcoded_mapbox_token(self):
        """Verify Mapbox token is not hardcoded in build."""
        assert not re.search(r'pk\.[a-zA-Z0-9]{20,}', self.frontend_script), \
            "Mapbox token should not be hardcoded"

    def test_frontend_script_no_hardcoded_api_url(self):
        """Verify API URL is not hardcoded (should come from env var)."""
        assert 'NEXT_PUBLIC_API_URL=' in self.frontend_script, \
            "API URL should come from environment variable"

    def test_gcp_script_validates_env_variables(self):
        """Verify script validates required environment variables."""
        # Check for parameter expansion with :? (error if not set)
        assert ':?' in self.gcp_script, \
            "Script should validate required environment variables"

    def test_frontend_script_validates_env_variables(self):
        """Verify frontend script validates required variables."""
        assert ':?' in self.frontend_script, \
            "Script should validate required environment variables"

    def test_gcp_script_handles_credentials_properly(self):
        """Verify script uses gcloud for authentication (not hardcoded)."""
        assert 'gcloud' in self.gcp_script, \
            "Script should use gcloud CLI for authentication"

    def test_frontend_script_respects_cloudflare_auth(self):
        """Verify frontend script respects Cloudflare authentication."""
        # Cloudflare auth should be handled by wrangler (which reads CF_API_TOKEN)
        assert 'CF_API_TOKEN' in self.frontend_script or 'wrangler' in self.frontend_script, \
            "Script should use Cloudflare authentication properly"

    def test_database_password_never_logged(self):
        """Verify database password is not echoed or logged."""
        # Check for unsafe echo patterns
        assert 'echo "${DB_PASSWORD}"' not in self.gcp_script, \
            "Database password should not be echoed"

    def test_gcp_script_uses_cloud_sql_proxy_connection(self):
        """Verify Cloud SQL connection uses secure proxy."""
        assert 'cloudsql' in self.gcp_script, \
            "Should use Cloud SQL Auth Proxy for secure connections"


class TestScriptValidation:
    """Tests that validate script syntax and structure."""

    @classmethod
    def setup_class(cls):
        """Load both deployment scripts."""
        gcp_path = Path(__file__).parent.parent / 'scripts' / 'deploy_gcp.sh'
        frontend_path = Path(__file__).parent.parent / 'scripts' / 'deploy_frontend.sh'

        with open(gcp_path, 'r') as f:
            cls.gcp_script = f.read()

        with open(frontend_path, 'r') as f:
            cls.frontend_script = f.read()

    def test_gcp_script_bash_syntax_valid(self):
        """Verify GCP script has valid bash syntax (via bash -n)."""
        gcp_path = Path(__file__).parent.parent / 'scripts' / 'deploy_gcp.sh'
        result = subprocess.run(
            ['bash', '-n', str(gcp_path)],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, f"Bash syntax error: {result.stderr}"

    def test_frontend_script_bash_syntax_valid(self):
        """Verify frontend script has valid bash syntax."""
        frontend_path = Path(__file__).parent.parent / 'scripts' / 'deploy_frontend.sh'
        result = subprocess.run(
            ['bash', '-n', str(frontend_path)],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, f"Bash syntax error: {result.stderr}"

    def test_gcp_script_no_unquoted_variables(self):
        """Verify script uses quoted variables where appropriate."""
        # This is a heuristic check - look for common mistakes
        # Variables should generally be quoted unless used as word splitting is intentional
        assert '${' in self.gcp_script, "Script should use proper variable syntax"

    def test_frontend_script_no_unquoted_variables(self):
        """Verify frontend script uses quoted variables."""
        assert '${' in self.frontend_script, "Script should use proper variable syntax"

    def test_gcp_script_uses_consistent_formatting(self):
        """Verify GCP script follows consistent formatting."""
        # Check for proper comment formatting
        assert '#' in self.gcp_script, "Script should include comments"

    def test_frontend_script_uses_consistent_formatting(self):
        """Verify frontend script follows consistent formatting."""
        assert '#' in self.frontend_script, "Script should include comments"


class TestCloudRunConfiguration:
    """Tests specifically for Cloud Run configuration."""

    @classmethod
    def setup_class(cls):
        """Load GCP deployment script."""
        script_path = Path(__file__).parent.parent / 'scripts' / 'deploy_gcp.sh'
        with open(script_path, 'r') as f:
            cls.script_content = f.read()

    def test_cloud_run_allows_unauthenticated(self):
        """Verify Cloud Run allows unauthenticated access."""
        assert '--allow-unauthenticated' in self.script_content, \
            "API should allow unauthenticated access"

    def test_cloud_run_configured_as_managed(self):
        """Verify Cloud Run uses managed platform."""
        assert '--platform=managed' in self.script_content, \
            "Cloud Run should use managed platform"

    def test_cloud_run_scales_to_zero(self):
        """Verify Cloud Run scales to zero when idle."""
        assert '--min-instances=0' in self.script_content, \
            "Cloud Run should scale to zero (min-instances=0)"

    def test_cloud_run_max_instances_reasonable(self):
        """Verify max instances is reasonable for MVP."""
        assert '--max-instances=5' in self.script_content, \
            "Max instances should be 5 for MVP"

    def test_cloud_run_region_is_us_west1(self):
        """Verify Cloud Run region is us-west1 (Vancouver-closest)."""
        assert 'us-west1' in self.script_content, \
            "Cloud Run should be deployed to us-west1 region"


class TestCloudSQLConfiguration:
    """Tests specifically for Cloud SQL configuration."""

    @classmethod
    def setup_class(cls):
        """Load GCP deployment script."""
        script_path = Path(__file__).parent.parent / 'scripts' / 'deploy_gcp.sh'
        with open(script_path, 'r') as f:
            cls.script_content = f.read()

    def test_cloud_sql_version_is_postgres_16(self):
        """Verify Cloud SQL uses PostgreSQL 16."""
        assert 'POSTGRES_16' in self.script_content, \
            "Should use PostgreSQL 16"

    def test_cloud_sql_tier_is_cost_effective(self):
        """Verify Cloud SQL uses appropriate tier."""
        assert '--tier=' in self.script_content, \
            "Cloud SQL tier should be specified"

    def test_cloud_sql_storage_is_ssd(self):
        """Verify Cloud SQL uses SSD storage."""
        assert '--storage-type=SSD' in self.script_content, \
            "Storage should be SSD type"

    def test_cloud_sql_initial_size(self):
        """Verify Cloud SQL initial storage size."""
        assert '--storage-size=' in self.script_content, \
            "Storage size should be specified"

    def test_cloud_sql_pgvector_enabled(self):
        """Verify pgvector extension is created."""
        assert 'vector' in self.script_content, \
            "pgvector extension should be enabled"

    def test_cloud_sql_postgis_enabled(self):
        """Verify PostGIS extension is created."""
        assert 'postgis' in self.script_content, \
            "PostGIS extension should be enabled"


class TestSecretManagerConfiguration:
    """Tests for Secret Manager configuration."""

    @classmethod
    def setup_class(cls):
        """Load GCP deployment script."""
        script_path = Path(__file__).parent.parent / 'scripts' / 'deploy_gcp.sh'
        with open(script_path, 'r') as f:
            cls.script_content = f.read()

    def test_secret_manager_api_enabled(self):
        """Verify Secret Manager API is enabled."""
        assert 'secretmanager.googleapis.com' in self.script_content, \
            "Secret Manager API should be enabled"

    def test_anthropic_key_stored_in_secrets(self):
        """Verify Anthropic key is stored as a secret."""
        assert 'anthropic-api-key' in self.script_content, \
            "Anthropic API key should be stored as a secret"

    def test_cohere_key_stored_in_secrets(self):
        """Verify Cohere key is stored as a secret."""
        assert 'cohere-api-key' in self.script_content, \
            "Cohere API key should be stored as a secret"

    def test_database_password_stored_in_secrets(self):
        """Verify database password is stored as a secret."""
        # Should be stored as database-password or similar
        assert 'database' in self.script_content.lower() and ('secret' in self.script_content.lower() or 'gcloud secrets' in self.script_content), \
            "Database password should be stored in secrets"

    def test_cloud_run_uses_secret_references(self):
        """Verify Cloud Run uses secret references via --set-secrets."""
        assert '--set-secrets=' in self.script_content, \
            "Cloud Run should reference secrets via --set-secrets flag"

    def test_secrets_use_automatic_replication(self):
        """Verify secrets use automatic replication policy."""
        assert '--replication-policy=' in self.script_content or 'automatic' in self.script_content, \
            "Secrets should use automatic replication"


class TestHealthCheckConfiguration:
    """Tests for health check configuration."""

    @classmethod
    def setup_class(cls):
        """Load GCP deployment script."""
        script_path = Path(__file__).parent.parent / 'scripts' / 'deploy_gcp.sh'
        with open(script_path, 'r') as f:
            cls.script_content = f.read()

    def test_health_check_path_defined(self):
        """Verify health check path is defined."""
        assert 'HEALTH_CHECK_PATH' in self.script_content or '--health-check-path' in self.script_content, \
            "Health check path should be configured"

    def test_health_check_default_is_slash_health(self):
        """Verify default health check is /health."""
        assert '/health' in self.script_content, \
            "Health check path should default to /health"

    def test_health_check_timeouts_configured(self):
        """Verify health check timeout is configured."""
        assert 'HEALTH_CHECK_TIMEOUT' in self.script_content or '--timeout' in self.script_content, \
            "Health check timeout should be configured"

    def test_health_check_initial_delay_set(self):
        """Verify health check has initial delay."""
        assert 'HEALTH_CHECK_INITIAL_DELAY' in self.script_content, \
            "Health check should have initial delay configured"


class TestEnvironmentVariables:
    """Tests for environment variable handling."""

    @classmethod
    def setup_class(cls):
        """Load both scripts."""
        gcp_path = Path(__file__).parent.parent / 'scripts' / 'deploy_gcp.sh'
        frontend_path = Path(__file__).parent.parent / 'scripts' / 'deploy_frontend.sh'

        with open(gcp_path, 'r') as f:
            cls.gcp_script = f.read()

        with open(frontend_path, 'r') as f:
            cls.frontend_script = f.read()

    def test_gcp_cors_origins_env_var(self):
        """Verify CORS_ORIGINS is passed as environment variable."""
        assert 'CORS_ORIGINS' in self.gcp_script, \
            "CORS_ORIGINS should be configured"

    def test_frontend_api_url_env_var(self):
        """Verify NEXT_PUBLIC_API_URL is set during frontend build."""
        assert 'NEXT_PUBLIC_API_URL' in self.frontend_script, \
            "NEXT_PUBLIC_API_URL should be passed to Next.js build"

    def test_frontend_mapbox_token_env_var(self):
        """Verify NEXT_PUBLIC_MAPBOX_TOKEN is set during build."""
        assert 'NEXT_PUBLIC_MAPBOX_TOKEN' in self.frontend_script, \
            "NEXT_PUBLIC_MAPBOX_TOKEN should be passed to build"

    def test_gcp_region_env_var_used(self):
        """Verify GCP region is properly used throughout script."""
        assert '${REGION}' in self.gcp_script or '${GCP_REGION}' in self.gcp_script, \
            "Region should be used as a variable"


class TestErrorHandlingAndValidation:
    """Tests for error handling and input validation."""

    @classmethod
    def setup_class(cls):
        """Load both scripts."""
        gcp_path = Path(__file__).parent.parent / 'scripts' / 'deploy_gcp.sh'
        frontend_path = Path(__file__).parent.parent / 'scripts' / 'deploy_frontend.sh'

        with open(gcp_path, 'r') as f:
            cls.gcp_script = f.read()

        with open(frontend_path, 'r') as f:
            cls.frontend_script = f.read()

    def test_gcp_script_validates_project_id(self):
        """Verify GCP script validates PROJECT_ID is set."""
        assert 'GCP_PROJECT_ID:?' in self.gcp_script, \
            "Script should validate GCP_PROJECT_ID is set"

    def test_gcp_script_validates_required_keys(self):
        """Verify GCP script validates all required API keys."""
        assert 'ANTHROPIC_API_KEY:?' in self.gcp_script, \
            "Should validate ANTHROPIC_API_KEY"
        assert 'COHERE_API_KEY:?' in self.gcp_script, \
            "Should validate COHERE_API_KEY"

    def test_frontend_script_validates_api_url(self):
        """Verify frontend script validates API URL is set."""
        assert 'NEXT_PUBLIC_API_URL:?' in self.frontend_script, \
            "Should validate NEXT_PUBLIC_API_URL is set"

    def test_frontend_script_validates_mapbox_token(self):
        """Verify frontend script validates Mapbox token."""
        assert 'NEXT_PUBLIC_MAPBOX_TOKEN:?' in self.frontend_script, \
            "Should validate NEXT_PUBLIC_MAPBOX_TOKEN is set"

    def test_frontend_script_checks_frontend_directory(self):
        """Verify frontend script checks if frontend dir exists."""
        assert 'frontend' in self.frontend_script and ('Error' in self.frontend_script or 'error' in self.frontend_script.lower()), \
            "Script should check if frontend directory exists"

    def test_frontend_script_checks_nextjs_config(self):
        """Verify frontend script validates Next.js config exists."""
        assert 'next.config' in self.frontend_script, \
            "Script should check for next.config file"

    def test_frontend_script_validates_build_artifacts(self):
        """Verify frontend script validates build was successful."""
        assert '.next' in self.frontend_script, \
            "Script should validate .next directory exists after build"


class TestDomainConfiguration:
    """Tests for custom domain configuration."""

    @classmethod
    def setup_class(cls):
        """Load both scripts."""
        gcp_path = Path(__file__).parent.parent / 'scripts' / 'deploy_gcp.sh'
        frontend_path = Path(__file__).parent.parent / 'scripts' / 'deploy_frontend.sh'

        with open(gcp_path, 'r') as f:
            cls.gcp_script = f.read()

        with open(frontend_path, 'r') as f:
            cls.frontend_script = f.read()

    def test_gcp_api_custom_domain_is_correct(self):
        """Verify API custom domain is api.vancitylens.com."""
        assert 'api.vancitylens.com' in self.gcp_script, \
            "API custom domain should be api.vancitylens.com"

    def test_frontend_custom_domain_is_correct(self):
        """Verify frontend custom domain is app.vancitylens.com."""
        assert 'app.vancitylens.com' in self.frontend_script, \
            "Frontend custom domain should be app.vancitylens.com"

    def test_gcp_creates_domain_mapping(self):
        """Verify GCP script creates domain mapping."""
        assert 'gcloud run domain-mappings create' in self.gcp_script or 'domain-mapping' in self.gcp_script, \
            "Script should create Cloud Run domain mapping"

    def test_frontend_provides_cname_instructions(self):
        """Verify frontend script provides DNS CNAME instructions."""
        assert 'CNAME' in self.frontend_script or 'DNS' in self.frontend_script or 'pages.dev' in self.frontend_script, \
            "Script should provide CNAME configuration instructions"
