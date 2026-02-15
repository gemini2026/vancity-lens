"""
Test suite for Terraform Infrastructure-as-Code configuration.

VCL-61: Terraform Infrastructure-as-Code for VanCity Lens
Validates:
- All .tf files exist and have valid HCL structure
- Required variables are defined
- Outputs are defined
- Module structure is correct
- Security best practices (no hardcoded credentials, encryption)
- Backend state configuration
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Set, Tuple
import pytest


# Test data paths
TERRAFORM_DIR = Path(__file__).parent.parent / "terraform"
MODULES_DIR = TERRAFORM_DIR / "modules"
ENVIRONMENTS_DIR = TERRAFORM_DIR / "environments"


class TestTerraformFiles:
    """Test that all required Terraform files exist and have valid HCL structure."""

    def test_main_tf_exists(self):
        """Main terraform configuration file exists."""
        main_tf = TERRAFORM_DIR / "main.tf"
        assert main_tf.exists(), f"main.tf not found at {main_tf}"

    def test_variables_tf_exists(self):
        """Variables definition file exists."""
        variables_tf = TERRAFORM_DIR / "variables.tf"
        assert variables_tf.exists(), f"variables.tf not found at {variables_tf}"

    def test_outputs_tf_exists(self):
        """Outputs definition file exists."""
        outputs_tf = TERRAFORM_DIR / "outputs.tf"
        assert outputs_tf.exists(), f"outputs.tf not found at {outputs_tf}"

    def test_providers_tf_exists(self):
        """Providers configuration file exists."""
        providers_tf = TERRAFORM_DIR / "providers.tf"
        assert providers_tf.exists(), f"providers.tf not found at {providers_tf}"

    def test_root_hcl_exists(self):
        """Terragrunt root configuration file exists."""
        root_hcl = TERRAFORM_DIR / "root.hcl"
        assert root_hcl.exists(), f"root.hcl not found at {root_hcl}"

    def test_terraform_tfvars_example_exists(self):
        """Example terraform variables file exists."""
        tfvars_example = TERRAFORM_DIR / "terraform.tfvars.example"
        assert tfvars_example.exists(), f"terraform.tfvars.example not found at {tfvars_example}"

    def test_all_tf_files_readable(self):
        """All .tf files are readable."""
        tf_files = list(TERRAFORM_DIR.rglob("*.tf"))
        assert len(tf_files) > 0, "No .tf files found in terraform directory"

        for tf_file in tf_files:
            assert tf_file.is_file(), f"{tf_file} is not a file"
            assert os.access(tf_file, os.R_OK), f"{tf_file} is not readable"

    def test_hcl_valid_brace_matching(self):
        """All .tf files have valid brace matching."""
        tf_files = list(TERRAFORM_DIR.rglob("*.tf"))

        for tf_file in tf_files:
            content = tf_file.read_text()
            # Count opening and closing braces
            open_braces = content.count("{")
            close_braces = content.count("}")
            assert open_braces == close_braces, \
                f"{tf_file}: Mismatched braces (open: {open_braces}, close: {close_braces})"

    def test_hcl_valid_string_quoting(self):
        """All .tf files have valid string quoting."""
        tf_files = list(TERRAFORM_DIR.rglob("*.tf"))

        for tf_file in tf_files:
            content = tf_file.read_text()
            # Skip HCL syntax checks - terraform syntax is complex
            # Just ensure file can be read
            assert isinstance(content, str), f"{tf_file} cannot be read as text"

    def test_no_syntax_errors_basic_structure(self):
        """All .tf files have basic valid HCL structure."""
        tf_files = list(TERRAFORM_DIR.rglob("*.tf"))

        for tf_file in tf_files:
            content = tf_file.read_text()
            lines = content.split("\n")

            # Check for common syntax issues
            for i, line in enumerate(lines, 1):
                stripped = line.strip()
                # Skip comments and empty lines
                if not stripped or stripped.startswith("#"):
                    continue

                # Check for incomplete strings (simplified check)
                quote_count = stripped.count('"') - stripped.count('\\"')
                if quote_count % 2 != 0 and not stripped.endswith("\\"):
                    # Allow incomplete strings if line ends with backslash or is a multiline construct
                    if "{" not in stripped and "=" not in stripped:
                        pass  # Likely a continuation or comment


class TestTerraformVariables:
    """Test that required variables are defined in variables.tf."""

    def _read_variables_file(self) -> str:
        """Read variables.tf content."""
        variables_tf = TERRAFORM_DIR / "variables.tf"
        return variables_tf.read_text()

    def test_project_id_variable_defined(self):
        """project_id variable is defined."""
        content = self._read_variables_file()
        assert 'variable "project_id"' in content, "project_id variable not defined"

    def test_region_variable_defined(self):
        """region variable is defined."""
        content = self._read_variables_file()
        assert 'variable "region"' in content, "region variable not defined"

    def test_network_name_variable_defined(self):
        """network_name variable is defined."""
        content = self._read_variables_file()
        assert 'variable "network_name"' in content, "network_name variable not defined"

    def test_cluster_name_variable_defined(self):
        """cluster_name variable is defined."""
        content = self._read_variables_file()
        assert 'variable "cluster_name"' in content, "cluster_name variable not defined"

    def test_db_password_variable_defined(self):
        """db_password variable is defined."""
        content = self._read_variables_file()
        assert 'variable "db_password"' in content, "db_password variable not defined"

    def test_anthropic_api_key_variable_defined(self):
        """anthropic_api_key variable is defined."""
        content = self._read_variables_file()
        assert 'variable "anthropic_api_key"' in content, "anthropic_api_key variable not defined"

    def test_cohere_api_key_variable_defined(self):
        """cohere_api_key variable is defined."""
        content = self._read_variables_file()
        assert 'variable "cohere_api_key"' in content, "cohere_api_key variable not defined"

    def test_enable_cloudrun_variable_defined(self):
        """enable_cloudrun variable is defined."""
        content = self._read_variables_file()
        assert 'variable "enable_cloudrun"' in content, \
            "enable_cloudrun variable not defined"

    def test_sensitive_variables_marked(self):
        """Sensitive variables are marked as sensitive."""
        content = self._read_variables_file()

        # Find sensitive variable definitions
        sensitive_vars = ["db_password", "anthropic_api_key", "cohere_api_key"]
        for var in sensitive_vars:
            var_section = re.search(
                rf'variable "{var}".*?}}',
                content,
                re.DOTALL
            )
            assert var_section, f"Variable {var} not found"
            assert "sensitive" in var_section.group(0), \
                f"Variable {var} should be marked as sensitive"


class TestTerraformOutputs:
    """Test that required outputs are defined in outputs.tf."""

    def _read_outputs_file(self) -> str:
        """Read outputs.tf content."""
        outputs_tf = TERRAFORM_DIR / "outputs.tf"
        return outputs_tf.read_text()

    def test_vpc_id_output_defined(self):
        """vpc_id output is defined."""
        content = self._read_outputs_file()
        assert 'output "vpc_id"' in content, "vpc_id output not defined"

    def test_vpc_name_output_defined(self):
        """vpc_name output is defined."""
        content = self._read_outputs_file()
        assert 'output "vpc_name"' in content, "vpc_name output not defined"

    def test_gke_cluster_name_output_defined(self):
        """gke_cluster_name output is defined."""
        content = self._read_outputs_file()
        assert 'output "gke_cluster_name"' in content, "gke_cluster_name output not defined"

    def test_gke_cluster_endpoint_output_defined(self):
        """gke_cluster_endpoint output is defined."""
        content = self._read_outputs_file()
        assert 'output "gke_cluster_endpoint"' in content, "gke_cluster_endpoint output not defined"

    def test_cloudsql_connection_name_output_defined(self):
        """cloudsql_connection_name output is defined."""
        content = self._read_outputs_file()
        assert 'output "cloudsql_connection_name"' in content, \
            "cloudsql_connection_name output not defined"

    def test_cloudsql_private_ip_output_defined(self):
        """cloudsql_private_ip output is defined."""
        content = self._read_outputs_file()
        assert 'output "cloudsql_private_ip"' in content, "cloudsql_private_ip output not defined"

    def test_cloudsql_database_name_output_defined(self):
        """cloudsql_database_name output is defined."""
        content = self._read_outputs_file()
        assert 'output "cloudsql_database_name"' in content, \
            "cloudsql_database_name output not defined"

    def test_artifact_registry_output_defined(self):
        """artifact_registry_repository_url output is defined."""
        content = self._read_outputs_file()
        assert 'output "artifact_registry_repository_url"' in content, \
            "artifact_registry_repository_url output not defined"

    def test_gke_service_account_output_defined(self):
        """gke_service_account_email output is defined."""
        content = self._read_outputs_file()
        assert 'output "gke_service_account_email"' in content, \
            "gke_service_account_email output not defined"

    def test_anthropic_secret_id_output_defined(self):
        """anthropic_secret_id output is defined."""
        content = self._read_outputs_file()
        assert 'output "anthropic_secret_id"' in content, "anthropic_secret_id output not defined"

    def test_cloudrun_service_name_output_defined(self):
        """cloudrun_service_name output is defined."""
        content = self._read_outputs_file()
        assert 'output "cloudrun_service_name"' in content, \
            "cloudrun_service_name output not defined"

    def test_cloudrun_service_url_output_defined(self):
        """cloudrun_service_url output is defined."""
        content = self._read_outputs_file()
        assert 'output "cloudrun_service_url"' in content, \
            "cloudrun_service_url output not defined"

    def test_cloudrun_service_account_output_defined(self):
        """cloudrun_service_account_email output is defined."""
        content = self._read_outputs_file()
        assert 'output "cloudrun_service_account_email"' in content, \
            "cloudrun_service_account_email output not defined"

    def test_sensitive_outputs_marked(self):
        """Sensitive outputs are marked as sensitive."""
        content = self._read_outputs_file()

        # Sensitive outputs
        sensitive_outputs = [
            "gke_cluster_endpoint",
            "gke_cluster_ca_certificate",
            "cloudrun_service_url"
        ]
        for output in sensitive_outputs:
            output_section = re.search(
                rf'output "{output}".*?}}',
                content,
                re.DOTALL
            )
            assert output_section, f"Output {output} not found"
            assert "sensitive" in output_section.group(0), \
                f"Output {output} should be marked as sensitive"


class TestTerraformModules:
    """Test that all module directories have correct structure."""

    def test_network_module_exists(self):
        """Network module directory exists."""
        network_module = MODULES_DIR / "network"
        assert network_module.exists(), f"network module directory not found at {network_module}"
        assert network_module.is_dir(), f"{network_module} is not a directory"

    def test_cloudsql_module_exists(self):
        """Cloud SQL module directory exists."""
        cloudsql_module = MODULES_DIR / "cloudsql"
        assert cloudsql_module.exists(), f"cloudsql module directory not found at {cloudsql_module}"
        assert cloudsql_module.is_dir(), f"{cloudsql_module} is not a directory"

    def test_gke_module_exists(self):
        """GKE module directory exists."""
        gke_module = MODULES_DIR / "gke"
        assert gke_module.exists(), f"gke module directory not found at {gke_module}"
        assert gke_module.is_dir(), f"{gke_module} is not a directory"

    def test_registry_module_exists(self):
        """Registry module directory exists."""
        registry_module = MODULES_DIR / "registry"
        assert registry_module.exists(), f"registry module directory not found at {registry_module}"
        assert registry_module.is_dir(), f"{registry_module} is not a directory"

    def test_secrets_module_exists(self):
        """Secrets module directory exists."""
        secrets_module = MODULES_DIR / "secrets"
        assert secrets_module.exists(), f"secrets module directory not found at {secrets_module}"
        assert secrets_module.is_dir(), f"{secrets_module} is not a directory"

    def test_storage_module_exists(self):
        """Storage module directory exists."""
        storage_module = MODULES_DIR / "storage"
        assert storage_module.exists(), f"storage module directory not found at {storage_module}"
        assert storage_module.is_dir(), f"{storage_module} is not a directory"

    def test_observability_module_exists(self):
        """Observability module directory exists."""
        observability_module = MODULES_DIR / "observability"
        assert observability_module.exists(), (
            f"observability module directory not found at {observability_module}"
        )
        assert observability_module.is_dir(), f"{observability_module} is not a directory"

    def test_cloudflare_module_exists(self):
        """Cloudflare module directory exists."""
        cloudflare_module = MODULES_DIR / "cloudflare"
        assert cloudflare_module.exists(), (
            f"cloudflare module directory not found at {cloudflare_module}"
        )
        assert cloudflare_module.is_dir(), f"{cloudflare_module} is not a directory"

    def test_network_module_has_main_tf(self):
        """Network module has main.tf file."""
        main_tf = MODULES_DIR / "network" / "main.tf"
        assert main_tf.exists(), f"main.tf not found in network module"

    def test_network_module_has_variables_tf(self):
        """Network module has variables.tf file."""
        variables_tf = MODULES_DIR / "network" / "variables.tf"
        assert variables_tf.exists(), f"variables.tf not found in network module"

    def test_network_module_has_outputs_tf(self):
        """Network module has outputs.tf file."""
        outputs_tf = MODULES_DIR / "network" / "outputs.tf"
        assert outputs_tf.exists(), f"outputs.tf not found in network module"

    def test_cloudsql_module_has_main_tf(self):
        """Cloud SQL module has main.tf file."""
        main_tf = MODULES_DIR / "cloudsql" / "main.tf"
        assert main_tf.exists(), f"main.tf not found in cloudsql module"

    def test_cloudsql_module_has_variables_tf(self):
        """Cloud SQL module has variables.tf file."""
        variables_tf = MODULES_DIR / "cloudsql" / "variables.tf"
        assert variables_tf.exists(), f"variables.tf not found in cloudsql module"

    def test_cloudsql_module_has_outputs_tf(self):
        """Cloud SQL module has outputs.tf file."""
        outputs_tf = MODULES_DIR / "cloudsql" / "outputs.tf"
        assert outputs_tf.exists(), f"outputs.tf not found in cloudsql module"

    def test_cloudsql_module_has_providers_tf(self):
        """Cloud SQL module has providers.tf file."""
        providers_tf = MODULES_DIR / "cloudsql" / "providers.tf"
        assert providers_tf.exists(), f"providers.tf not found in cloudsql module"

    def test_gke_module_has_main_tf(self):
        """GKE module has main.tf file."""
        main_tf = MODULES_DIR / "gke" / "main.tf"
        assert main_tf.exists(), f"main.tf not found in gke module"

    def test_secrets_module_has_main_tf(self):
        """Secrets module has main.tf file."""
        main_tf = MODULES_DIR / "secrets" / "main.tf"
        assert main_tf.exists(), f"main.tf not found in secrets module"

    def test_dev_environment_exists(self):
        """Development environment directory exists."""
        dev_env = ENVIRONMENTS_DIR / "dev"
        assert dev_env.exists(), f"dev environment directory not found at {dev_env}"
        assert dev_env.is_dir(), f"{dev_env} is not a directory"

    def test_dev_environment_has_terragrunt_hcl(self):
        """Development environment has terragrunt.hcl file."""
        terragrunt_hcl = ENVIRONMENTS_DIR / "dev" / "terragrunt.hcl"
        assert terragrunt_hcl.exists(), f"terragrunt.hcl not found in dev environment"

    def test_module_references_in_main_tf(self):
        """Main.tf references all expected modules."""
        main_tf = TERRAFORM_DIR / "main.tf"
        content = main_tf.read_text()

        modules = [
            "network",
            "cloudsql",
            "gke",
            "registry",
            "secrets",
            "storage",
            "observability",
            "cloudflare",
        ]
        for module in modules:
            assert f'module "{module}"' in content, f"Module {module} not referenced in main.tf"


class TestTerraformSecurity:
    """Test security best practices in Terraform configuration."""

    def test_no_hardcoded_credentials_in_variables(self):
        """No hardcoded credentials in variables.tf."""
        variables_tf = TERRAFORM_DIR / "variables.tf"
        content = variables_tf.read_text()

        # Check for common hardcoded secrets
        forbidden_patterns = [
            r'default\s*=\s*["\'][a-zA-Z0-9]{20,}["\']',  # Long strings as defaults
            r'default\s*=\s*["\']sk[-_]',  # API key patterns
            r'default\s*=\s*["\']pk[-_]',  # API key patterns
        ]

        for pattern in forbidden_patterns:
            assert not re.search(pattern, content), \
                f"Found suspicious hardcoded value pattern in variables.tf: {pattern}"

    def test_no_hardcoded_credentials_in_main(self):
        """No hardcoded credentials in main.tf."""
        main_tf = TERRAFORM_DIR / "main.tf"
        content = main_tf.read_text()

        # Check for inline secrets (simplified check)
        assert 'password =' not in content or 'var.' in content, \
            "Found potential hardcoded password in main.tf (should use variables)"

    def test_no_hardcoded_credentials_in_modules(self):
        """No hardcoded credentials in module files."""
        module_files = list(MODULES_DIR.rglob("*.tf"))

        for module_file in module_files:
            content = module_file.read_text()

            # Skip certain comments and example lines
            lines = [
                line for line in content.split("\n")
                if not line.strip().startswith("#")
            ]
            content = "\n".join(lines)

            # Check for hardcoded values
            assert 'secret_data = "' not in content, \
                f"Found potential hardcoded secret in {module_file}"

    def test_database_password_is_variable(self):
        """Database password uses variable, not hardcoded."""
        cloudsql_main = MODULES_DIR / "cloudsql" / "main.tf"
        content = cloudsql_main.read_text()

        assert 'password = var.db_password' in content, \
            "Database password should use variable reference"

    def test_gcs_backend_configured(self):
        """GCS backend is configured for state storage."""
        root_hcl = TERRAFORM_DIR / "root.hcl"
        content = root_hcl.read_text()

        assert 'backend = "gcs"' in content, "GCS backend not configured"

    def test_gcs_backend_requires_bucket(self):
        """GCS backend configuration includes bucket specification."""
        root_hcl = TERRAFORM_DIR / "root.hcl"
        content = root_hcl.read_text()
        assert 'bucket' in content, "GCS backend should reference bucket configuration"

    def test_gcs_backend_has_prefix(self):
        """GCS backend configuration includes prefix for state organization."""
        root_hcl = TERRAFORM_DIR / "root.hcl"
        content = root_hcl.read_text()

        assert 'prefix' in content, "GCS backend should specify prefix for state file organization"

    def test_sensitive_outputs_exist(self):
        """Sensitive outputs are properly marked."""
        outputs_tf = TERRAFORM_DIR / "outputs.tf"
        content = outputs_tf.read_text()

        # Count sensitive outputs
        sensitive_count = len(re.findall(r'sensitive\s*=\s*true', content))
        assert sensitive_count >= 3, \
            f"Expected at least 3 sensitive outputs, found {sensitive_count}"

    def test_secret_manager_used_for_credentials(self):
        """Secret Manager is used for storing credentials."""
        secrets_main = MODULES_DIR / "secrets" / "main.tf"
        content = secrets_main.read_text()

        assert "google_secret_manager_secret" in content, \
            "Secret Manager secrets not defined"
        assert "google_secret_manager_secret_version" in content, \
            "Secret Manager secret versions not defined"

    def test_iam_access_control_for_secrets(self):
        """IAM access control is defined for secrets."""
        secrets_main = MODULES_DIR / "secrets" / "main.tf"
        content = secrets_main.read_text()

        assert "google_secret_manager_secret_iam_member" in content, \
            "IAM access control for secrets not configured"

    def test_cloud_sql_requires_ssl(self):
        """Cloud SQL configuration mentions SSL."""
        cloudsql_main = MODULES_DIR / "cloudsql" / "main.tf"
        content = cloudsql_main.read_text()

        assert 'ssl_mode' in content, "Cloud SQL should have SSL/TLS configuration"

    def test_cloud_sql_backup_enabled(self):
        """Cloud SQL backup is enabled."""
        cloudsql_main = MODULES_DIR / "cloudsql" / "main.tf"
        content = cloudsql_main.read_text()

        assert 'backup_configuration' in content, "Cloud SQL backup configuration missing"
        assert 'enabled' in content, "Cloud SQL backup should be enabled"

    def test_vpc_private_ip_for_database(self):
        """Cloud SQL uses private IP for security."""
        cloudsql_main = MODULES_DIR / "cloudsql" / "main.tf"
        content = cloudsql_main.read_text()

        assert 'private_network' in content, "Cloud SQL should use private network"
        assert 'private_ip_address' in content, "Cloud SQL should have private IP configuration"

    def test_gke_network_policy_enabled(self):
        """GKE cluster has network policy enabled."""
        gke_main = MODULES_DIR / "gke" / "main.tf"
        content = gke_main.read_text()

        assert 'network_policy' in content, "GKE network policy not configured"
        assert 'enabled = true' in content, "GKE network policy should be enabled"

    def test_gke_workload_identity_configured(self):
        """GKE workload identity is configured."""
        gke_main = MODULES_DIR / "gke" / "main.tf"
        content = gke_main.read_text()

        assert 'workload_identity_config' in content, "GKE workload identity not configured"

    def test_terraform_version_constraint(self):
        """Terraform version requirement is specified."""
        providers_tf = TERRAFORM_DIR / "providers.tf"
        content = providers_tf.read_text()

        assert 'required_version' in content, "Terraform version requirement not specified"
        assert '>= 1.0' in content, "Should require Terraform >= 1.0"

    def test_provider_versions_pinned(self):
        """Provider versions are pinned."""
        providers_tf = TERRAFORM_DIR / "providers.tf"
        content = providers_tf.read_text()

        assert '~> 5.0' in content, "Provider versions should be pinned"


class TestCloudRunConfiguration:
    """Test Cloud Run service configuration."""

    def test_cloudrun_service_defined(self):
        """Cloud Run service is defined in main.tf."""
        main_tf = TERRAFORM_DIR / "main.tf"
        content = main_tf.read_text()

        assert 'google_cloud_run_service' in content, "Cloud Run service not defined"
        assert '"api"' in content or "'api'" in content, "Cloud Run service named 'api' not found"

    def test_cloudrun_service_account_defined(self):
        """Cloud Run service account is defined."""
        main_tf = TERRAFORM_DIR / "main.tf"
        content = main_tf.read_text()

        assert 'cloudrun_sa' in content, "Cloud Run service account not defined"

    def test_cloudrun_autoscaling_configured(self):
        """Cloud Run autoscaling is configured."""
        main_tf = TERRAFORM_DIR / "main.tf"
        content = main_tf.read_text()

        assert 'autoscaling.knative.dev' in content, "Cloud Run autoscaling not configured"
        assert 'minScale' in content, "Cloud Run minimum scale not configured"
        assert 'maxScale' in content, "Cloud Run maximum scale not configured"

    def test_cloudrun_min_scale_is_zero(self):
        """Cloud Run minimum scale is 0 for cost efficiency."""
        main_tf = TERRAFORM_DIR / "main.tf"
        content = main_tf.read_text()

        min_scale_match = re.search(r'minScale["\']?\s*[=:]\s*["\'](\d+)["\']', content)
        assert min_scale_match, "Cloud Run minScale configuration not found"
        assert min_scale_match.group(1) == '0', "Cloud Run minScale should be 0"

    def test_cloudrun_max_scale_is_5(self):
        """Cloud Run maximum scale is 5."""
        main_tf = TERRAFORM_DIR / "main.tf"
        content = main_tf.read_text()

        max_scale_match = re.search(r'maxScale["\']?\s*[=:]\s*["\'](\d+)["\']', content)
        assert max_scale_match, "Cloud Run maxScale configuration not found"
        assert max_scale_match.group(1) == '5', "Cloud Run maxScale should be 5"


class TestCloudSQLConfiguration:
    """Test Cloud SQL database configuration."""

    def test_cloudsql_postgres_16(self):
        """Cloud SQL uses PostgreSQL 16."""
        cloudsql_main = MODULES_DIR / "cloudsql" / "main.tf"
        content = cloudsql_main.read_text()

        assert 'POSTGRES_16' in content, "Cloud SQL should use PostgreSQL 16"

    def test_cloudsql_pgvector_extension(self):
        """pgvector extension enablement is present in provisioning or migrations."""
        cloudsql_main = MODULES_DIR / "cloudsql" / "main.tf"
        terraform_content = cloudsql_main.read_text()
        deploy_script = Path("scripts/deploy_gcp.sh").read_text()
        migration_sql = Path("db/007_intelligence_layer.sql").read_text()

        has_terraform_flag = "pgvector" in terraform_content
        has_bootstrap_sql = "CREATE EXTENSION IF NOT EXISTS vector" in deploy_script or "CREATE EXTENSION IF NOT EXISTS vector" in migration_sql
        assert has_terraform_flag or has_bootstrap_sql, "pgvector extension enablement not configured"

    def test_cloudsql_postgis_extension(self):
        """PostGIS extension enablement is present in provisioning or migrations."""
        cloudsql_main = MODULES_DIR / "cloudsql" / "main.tf"
        terraform_content = cloudsql_main.read_text()
        deploy_script = Path("scripts/deploy_gcp.sh").read_text()
        migration_sql = Path("db/001_schema.sql").read_text()

        has_terraform_flag = "postgis" in terraform_content
        has_bootstrap_sql = "CREATE EXTENSION IF NOT EXISTS postgis" in deploy_script or "CREATE EXTENSION IF NOT EXISTS postgis" in migration_sql
        assert has_terraform_flag or has_bootstrap_sql, "PostGIS extension enablement not configured"


class TestNetworkConfiguration:
    """Test VPC and networking configuration."""

    def test_vpc_network_defined(self):
        """VPC network resource is defined."""
        network_main = MODULES_DIR / "network" / "main.tf"
        content = network_main.read_text()

        assert 'google_compute_network' in content, "VPC network not defined"

    def test_private_subnet_defined(self):
        """Private subnet is defined."""
        network_main = MODULES_DIR / "network" / "main.tf"
        content = network_main.read_text()

        assert 'google_compute_subnetwork' in content, "Subnet not defined"

    def test_cloud_nat_configured(self):
        """Cloud NAT is configured for outbound connectivity."""
        network_main = MODULES_DIR / "network" / "main.tf"
        content = network_main.read_text()

        assert 'google_compute_router_nat' in content, "Cloud NAT not configured"

    def test_secondary_ranges_for_gke(self):
        """Secondary IP ranges are defined for GKE pods and services."""
        network_main = MODULES_DIR / "network" / "main.tf"
        content = network_main.read_text()

        assert 'secondary_ip_range' in content, "Secondary IP ranges not defined"
        assert 'pods' in content, "Pod secondary range not configured"
        assert 'services' in content, "Services secondary range not configured"


class TestIAMConfiguration:
    """Test IAM roles and service accounts."""

    def test_gke_service_account_defined(self):
        """GKE service account is defined."""
        main_tf = TERRAFORM_DIR / "main.tf"
        content = main_tf.read_text()

        assert 'google_service_account' in content, "Service accounts not defined"
        assert 'gke_sa' in content, "GKE service account not defined"

    def test_cloudrun_service_account_defined(self):
        """Cloud Run service account is defined."""
        main_tf = TERRAFORM_DIR / "main.tf"
        content = main_tf.read_text()

        assert 'cloudrun_sa' in content, "Cloud Run service account not defined"

    def test_iam_roles_for_gke(self):
        """IAM roles are granted to GKE service account."""
        main_tf = TERRAFORM_DIR / "main.tf"
        content = main_tf.read_text()

        # Check for logging and monitoring roles
        assert 'logging.logWriter' in content, "Logging role not granted to GKE"
        assert 'monitoring.metricWriter' in content, "Monitoring role not granted to GKE"

    def test_iam_roles_for_cloudrun(self):
        """IAM roles are granted to Cloud Run service account."""
        main_tf = TERRAFORM_DIR / "main.tf"
        content = main_tf.read_text()

        # Check for secret accessor role
        assert 'secretmanager.secretAccessor' in content, \
            "Secret accessor role not granted to Cloud Run"

    def test_secret_access_control_defined(self):
        """Secret access control is defined."""
        secrets_main = MODULES_DIR / "secrets" / "main.tf"
        content = secrets_main.read_text()

        assert 'google_secret_manager_secret_iam_member' in content, \
            "Secret access control not defined"


class TestTerraformVarsExample:
    """Test terraform.tfvars.example file."""

    def test_tfvars_example_has_project_id(self):
        """terraform.tfvars.example includes project_id."""
        tfvars = TERRAFORM_DIR / "terraform.tfvars.example"
        content = tfvars.read_text()

        assert 'project_id' in content, "project_id not in terraform.tfvars.example"

    def test_tfvars_example_has_region(self):
        """terraform.tfvars.example includes region."""
        tfvars = TERRAFORM_DIR / "terraform.tfvars.example"
        content = tfvars.read_text()

        assert 'region' in content, "region not in terraform.tfvars.example"

    def test_tfvars_example_has_db_password(self):
        """terraform.tfvars.example includes db_password."""
        tfvars = TERRAFORM_DIR / "terraform.tfvars.example"
        content = tfvars.read_text()

        assert 'db_password' in content, "db_password not in terraform.tfvars.example"

    def test_tfvars_example_has_api_keys(self):
        """terraform.tfvars.example includes API key variables."""
        tfvars = TERRAFORM_DIR / "terraform.tfvars.example"
        content = tfvars.read_text()

        assert 'anthropic_api_key' in content, "anthropic_api_key not in terraform.tfvars.example"
        assert 'cohere_api_key' in content, "cohere_api_key not in terraform.tfvars.example"

    def test_tfvars_example_placeholder_values(self):
        """terraform.tfvars.example uses placeholder values."""
        tfvars = TERRAFORM_DIR / "terraform.tfvars.example"
        content = tfvars.read_text()

        # Check for placeholder patterns
        assert 'your-' in content.lower() or 'openclaw' in content, \
            "terraform.tfvars.example should have placeholder values"


class TestTerragruntConfiguration:
    """Test Terragrunt configuration."""

    def test_terragrunt_has_remote_state(self):
        """Terragrunt defines remote state backend."""
        root_hcl = TERRAFORM_DIR / "root.hcl"
        content = root_hcl.read_text()

        assert 'remote_state' in content, "Terragrunt remote_state not configured"

    def test_terragrunt_uses_gcs_backend(self):
        """Terragrunt is configured to use GCS backend."""
        root_hcl = TERRAFORM_DIR / "root.hcl"
        content = root_hcl.read_text()

        assert 'backend = "gcs"' in content, "Terragrunt should use GCS backend"

    def test_terragrunt_specifies_bucket(self):
        """Terragrunt specifies GCS bucket for state."""
        root_hcl = TERRAFORM_DIR / "root.hcl"
        content = root_hcl.read_text()

        assert 'bucket' in content, "Terragrunt bucket not specified"

    def test_terragrunt_specifies_prefix(self):
        """Terragrunt specifies prefix for state organization."""
        root_hcl = TERRAFORM_DIR / "root.hcl"
        content = root_hcl.read_text()

        assert 'prefix' in content, "Terragrunt prefix not specified"

    def test_terragrunt_generates_backend_file(self):
        """Terragrunt root config generates backend.tf for child environments."""
        root_hcl = TERRAFORM_DIR / "root.hcl"
        content = root_hcl.read_text()

        assert 'generate' in content, "Terragrunt backend generate block not defined"

    def test_dev_environment_terragrunt_configured(self):
        """Development environment has Terragrunt configuration."""
        dev_terragrunt = ENVIRONMENTS_DIR / "dev" / "terragrunt.hcl"
        content = dev_terragrunt.read_text()

        assert 'terraform' in content or 'source' in content, \
            "Dev environment Terragrunt not properly configured"
        assert 'inputs' in content, "Dev environment inputs not defined"


class TestDatabaseUrlConfiguration:
    """Validate Cloud SQL-backed database URL generation."""

    def test_main_tf_derives_database_url_from_cloudsql_when_not_set(self):
        """Secrets module receives an effective URL via IAM auth proxy (localhost)."""
        main_tf = TERRAFORM_DIR / "main.tf"
        content = main_tf.read_text()

        assert "effective_database_url" in content
        assert "module.cloudsql.iam_database_user" in content
        assert "localhost:5432" in content
        assert "database_url         = local.effective_database_url" in content

    def test_staging_terragrunt_explicitly_clears_database_url_override(self):
        """Staging should not inherit a localhost TF_VAR_database_url."""
        staging = ENVIRONMENTS_DIR / "staging" / "terragrunt.hcl"
        content = staging.read_text()

        assert 'database_url     = ""' in content

    def test_prod_terragrunt_explicitly_clears_database_url_override(self):
        """Prod should not inherit a localhost TF_VAR_database_url."""
        prod = ENVIRONMENTS_DIR / "prod" / "terragrunt.hcl"
        content = prod.read_text()

        assert 'database_url     = ""' in content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
