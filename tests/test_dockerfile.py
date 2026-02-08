"""
Tests for multi-stage Docker builds (VCL-68: INFRA-012)

Validates that Dockerfile and Dockerfile.prod follow best practices:
- Multi-stage builds for smaller final images
- Non-root user execution
- Virtual environment usage
- Health checks
- Production hardening
"""

import re
from pathlib import Path


class TestDockerfile:
    """Tests for the standard development Dockerfile"""

    @classmethod
    def setup_class(cls):
        """Load the Dockerfile content"""
        dockerfile_path = Path(__file__).parent.parent / "Dockerfile"
        assert dockerfile_path.exists(), f"Dockerfile not found at {dockerfile_path}"
        cls.content = dockerfile_path.read_text()

    def test_multi_stage_build(self):
        """Verify multi-stage build with at least 2 FROM statements"""
        from_statements = re.findall(r'^FROM\s+', self.content, re.MULTILINE)
        assert len(from_statements) >= 2, \
            f"Expected at least 2 FROM statements (multi-stage), found {len(from_statements)}"

    def test_builder_stage_exists(self):
        """Verify builder stage with AS builder"""
        assert re.search(r'FROM\s+.*\s+AS\s+builder', self.content, re.IGNORECASE), \
            "Builder stage not found (missing 'FROM ... AS builder')"

    def test_runtime_stage_exists(self):
        """Verify runtime stage with AS runtime"""
        assert re.search(r'FROM\s+.*\s+AS\s+runtime', self.content, re.IGNORECASE), \
            "Runtime stage not found (missing 'FROM ... AS runtime')"

    def test_builder_has_build_essential(self):
        """Verify builder stage installs build-essential"""
        builder_match = re.search(
            r'(FROM\s+.*\s+AS\s+builder.*?)(FROM\s+.*\s+AS|$)',
            self.content,
            re.IGNORECASE | re.DOTALL
        )
        assert builder_match, "Builder stage not found"
        builder_section = builder_match.group(1)
        assert 'build-essential' in builder_section, \
            "Builder stage must install build-essential"

    def test_builder_has_libpq_dev(self):
        """Verify builder stage installs libpq-dev"""
        builder_match = re.search(
            r'(FROM\s+.*\s+AS\s+builder.*?)(FROM\s+.*\s+AS|$)',
            self.content,
            re.IGNORECASE | re.DOTALL
        )
        assert builder_match, "Builder stage not found"
        builder_section = builder_match.group(1)
        assert 'libpq-dev' in builder_section, \
            "Builder stage must install libpq-dev"

    def test_builder_creates_venv(self):
        """Verify builder creates virtual environment at /opt/venv"""
        builder_match = re.search(
            r'(FROM\s+.*\s+AS\s+builder.*?)(FROM\s+.*\s+AS|$)',
            self.content,
            re.IGNORECASE | re.DOTALL
        )
        assert builder_match, "Builder stage not found"
        builder_section = builder_match.group(1)
        assert '/opt/venv' in builder_section, \
            "Builder must create virtual environment at /opt/venv"

    def test_runtime_no_build_essential(self):
        """Verify runtime stage does NOT have build-essential in RUN apt-get"""
        # Split content into stages at FROM directives
        stages = re.split(r'^FROM\s+.*\s+AS\s+', self.content, flags=re.MULTILINE)
        # Find the runtime stage (should be after builder)
        runtime_stage = None
        for stage in stages:
            if stage.lower().startswith('runtime'):
                runtime_stage = stage
                break
        assert runtime_stage, "Runtime stage not found"
        # Check that build-essential is not in apt-get installs in this stage
        apt_install_match = re.search(
            r'apt-get install.*?(?=apt-get clean|\n\n)',
            runtime_stage,
            re.DOTALL
        )
        if apt_install_match:
            install_section = apt_install_match.group(0)
            assert 'build-essential' not in install_section, \
                "Runtime stage must not install build-essential (bloat)"

    def test_runtime_has_libpq5(self):
        """Verify runtime stage installs libpq5 (runtime dep)"""
        runtime_match = re.search(
            r'(FROM\s+.*\s+AS\s+runtime.*?)(USER\s+|$)',
            self.content,
            re.IGNORECASE | re.DOTALL
        )
        assert runtime_match, "Runtime stage not found"
        runtime_section = runtime_match.group(1)
        assert 'libpq5' in runtime_section, \
            "Runtime stage must install libpq5"

    def test_runtime_has_poppler(self):
        """Verify runtime stage installs poppler-utils"""
        runtime_match = re.search(
            r'(FROM\s+.*\s+AS\s+runtime.*?)(USER\s+|$)',
            self.content,
            re.IGNORECASE | re.DOTALL
        )
        assert runtime_match, "Runtime stage not found"
        runtime_section = runtime_match.group(1)
        assert 'poppler-utils' in runtime_section, \
            "Runtime stage must install poppler-utils"

    def test_runtime_has_tesseract(self):
        """Verify runtime stage installs tesseract-ocr"""
        runtime_match = re.search(
            r'(FROM\s+.*\s+AS\s+runtime.*?)(USER\s+|$)',
            self.content,
            re.IGNORECASE | re.DOTALL
        )
        assert runtime_match, "Runtime stage not found"
        runtime_section = runtime_match.group(1)
        assert 'tesseract-ocr' in runtime_section, \
            "Runtime stage must install tesseract-ocr"

    def test_copy_from_builder(self):
        """Verify COPY --from=builder /opt/venv /opt/venv"""
        assert re.search(
            r'COPY\s+--from=builder\s+/opt/venv\s+/opt/venv',
            self.content,
            re.IGNORECASE
        ), "Must copy venv from builder: COPY --from=builder /opt/venv /opt/venv"

    def test_non_root_user_created(self):
        """Verify non-root user 'vancity' is created"""
        assert 'vancity' in self.content, \
            "Non-root user 'vancity' must be created"
        assert re.search(
            r'useradd.*vancity',
            self.content,
            re.IGNORECASE
        ), "useradd command must create 'vancity' user"

    def test_user_uid_1000(self):
        """Verify vancity user has uid 1000"""
        assert re.search(
            r'useradd.*-u\s+1000.*vancity',
            self.content,
            re.IGNORECASE
        ), "User 'vancity' must have uid 1000"

    def test_user_no_shell(self):
        """Verify vancity user has nologin shell"""
        assert re.search(
            r'useradd.*nologin.*vancity',
            self.content,
            re.IGNORECASE
        ), "User 'vancity' must use /sbin/nologin shell"

    def test_healthcheck_present(self):
        """Verify HEALTHCHECK instruction is present"""
        assert re.search(
            r'HEALTHCHECK',
            self.content,
            re.IGNORECASE
        ), "HEALTHCHECK instruction must be present"

    def test_healthcheck_uses_python(self):
        """Verify HEALTHCHECK uses python (no curl/wget)"""
        assert re.search(
            r'HEALTHCHECK.*python',
            self.content,
            re.IGNORECASE | re.DOTALL
        ), "HEALTHCHECK must use python (not curl/wget) for slim images"

    def test_expose_8000(self):
        """Verify EXPOSE 8000 is present"""
        assert re.search(
            r'EXPOSE\s+8000',
            self.content,
            re.IGNORECASE
        ), "Must EXPOSE port 8000"

    def test_cmd_exec_form(self):
        """Verify CMD uses exec form (JSON array)"""
        assert re.search(
            r'CMD\s+\[',
            self.content
        ), "CMD must use exec form (JSON array), not shell form"

    def test_file_ownership(self):
        """Verify COPY uses --chown for non-root user"""
        assert re.search(
            r'COPY\s+--chown=vancity:vancity',
            self.content,
            re.IGNORECASE
        ), "Application files must be owned by vancity user (use --chown)"

    def test_user_switch(self):
        """Verify USER command switches to non-root"""
        assert re.search(
            r'USER\s+vancity',
            self.content,
            re.IGNORECASE
        ), "Must switch to non-root user with USER command"


class TestDockerfileProd:
    """Tests for the production-hardened Dockerfile.prod"""

    @classmethod
    def setup_class(cls):
        """Load the Dockerfile.prod content"""
        dockerfile_prod_path = Path(__file__).parent.parent / "Dockerfile.prod"
        assert dockerfile_prod_path.exists(), \
            f"Dockerfile.prod not found at {dockerfile_prod_path}"
        cls.content = dockerfile_prod_path.read_text()

    def test_multi_stage_build(self):
        """Verify multi-stage build with at least 2 FROM statements"""
        from_statements = re.findall(r'^FROM\s+', self.content, re.MULTILINE)
        assert len(from_statements) >= 2, \
            f"Expected at least 2 FROM statements (multi-stage), found {len(from_statements)}"

    def test_non_root_user_created(self):
        """Verify non-root user 'vancity' is created"""
        assert 'vancity' in self.content, \
            "Non-root user 'vancity' must be created"
        assert re.search(
            r'useradd.*vancity',
            self.content,
            re.IGNORECASE
        ), "useradd command must create 'vancity' user"

    def test_no_reload_flag(self):
        """Verify production CMD does NOT have --reload flag"""
        cmd_match = re.search(
            r'CMD\s+\[(.*?)\]',
            self.content,
            re.DOTALL
        )
        assert cmd_match, "CMD instruction not found"
        cmd_content = cmd_match.group(1)
        assert '--reload' not in cmd_content, \
            "Production image must not have --reload flag (development only)"

    def test_workers_configured(self):
        """Verify production CMD specifies worker count"""
        cmd_match = re.search(
            r'CMD\s+\[(.*?)\]',
            self.content,
            re.DOTALL
        )
        assert cmd_match, "CMD instruction not found"
        cmd_content = cmd_match.group(1)
        assert '--workers' in cmd_content, \
            "Production CMD should specify --workers for multi-processing"

    def test_cmd_exec_form(self):
        """Verify CMD uses exec form (JSON array)"""
        assert re.search(
            r'CMD\s+\[',
            self.content
        ), "CMD must use exec form (JSON array), not shell form"

    def test_healthcheck_present(self):
        """Verify HEALTHCHECK instruction is present"""
        assert re.search(
            r'HEALTHCHECK',
            self.content,
            re.IGNORECASE
        ), "HEALTHCHECK instruction must be present"

    def test_readonly_filesystem_friendly(self):
        """Verify chmod for read-only filesystem compatibility"""
        assert re.search(
            r'chmod',
            self.content,
            re.IGNORECASE
        ), "Must configure permissions for read-only filesystem"

    def test_expose_8000(self):
        """Verify EXPOSE 8000 is present"""
        assert re.search(
            r'EXPOSE\s+8000',
            self.content,
            re.IGNORECASE
        ), "Must EXPOSE port 8000"

    def test_copy_from_builder(self):
        """Verify COPY --from=builder /opt/venv /opt/venv"""
        assert re.search(
            r'COPY\s+--from=builder\s+/opt/venv\s+/opt/venv',
            self.content,
            re.IGNORECASE
        ), "Must copy venv from builder: COPY --from=builder /opt/venv /opt/venv"

    def test_user_switch(self):
        """Verify USER command switches to non-root"""
        assert re.search(
            r'USER\s+vancity',
            self.content,
            re.IGNORECASE
        ), "Must switch to non-root user with USER command"


class TestDockerComposibility:
    """Tests to ensure docker-compose.yml compatibility"""

    def test_dockerfile_exists(self):
        """Verify Dockerfile exists at project root"""
        dockerfile = Path(__file__).parent.parent / "Dockerfile"
        assert dockerfile.exists(), "Dockerfile must exist at project root"

    def test_docker_compose_references_dockerfile(self):
        """Verify docker-compose.yml references Dockerfile correctly"""
        compose_path = Path(__file__).parent.parent / "docker-compose.yml"
        assert compose_path.exists(), "docker-compose.yml not found"
        compose_content = compose_path.read_text()
        # The api service should build from Dockerfile
        assert 'dockerfile: Dockerfile' in compose_content, \
            "docker-compose.yml must reference 'dockerfile: Dockerfile' for api service"

    def test_api_service_build_context(self):
        """Verify api service uses correct build context"""
        compose_path = Path(__file__).parent.parent / "docker-compose.yml"
        compose_content = compose_path.read_text()
        # Find the api service section and verify context
        api_section = re.search(
            r'api:\s*\n.*?build:.*?\n.*?context:\s*\.',
            compose_content,
            re.DOTALL
        )
        assert api_section, \
            "api service must use 'context: .'"
