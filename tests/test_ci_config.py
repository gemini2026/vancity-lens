"""Tests for CI/CD configuration files."""

import yaml
from pathlib import Path


class TestCIConfig:
    """Tests for .github/workflows/ci.yml"""

    @classmethod
    def setup_class(cls):
        """Load CI configuration file."""
        ci_path = Path(__file__).parent.parent / '.github' / 'workflows' / 'ci.yml'
        assert ci_path.exists(), f"CI configuration not found at {ci_path}"

        with open(ci_path, 'r') as f:
            cls.ci_config = yaml.safe_load(f)

    def test_ci_config_valid_yaml(self):
        """Verify ci.yml is valid YAML."""
        assert isinstance(self.ci_config, dict), "CI config should be a dictionary"

    def test_ci_config_has_name(self):
        """Verify CI workflow has a name."""
        assert 'name' in self.ci_config
        assert self.ci_config['name'] == 'CI'

    def test_ci_triggers_on_push_all_branches(self):
        """Verify CI triggers on push to any branch."""
        # YAML parses 'on:' as boolean True key
        on_config = self.ci_config.get('on') or self.ci_config.get(True)
        assert on_config is not None, "Config should have 'on' trigger"
        assert 'push' in on_config
        assert on_config['push']['branches'] == ['*']

    def test_ci_triggers_on_pull_request_to_main(self):
        """Verify CI triggers on pull requests to main."""
        on_config = self.ci_config.get('on') or self.ci_config.get(True)
        assert on_config is not None
        assert 'pull_request' in on_config
        assert on_config['pull_request']['branches'] == ['main']

    def test_ci_concurrency_configured(self):
        """Verify concurrency configuration for branch cancellation."""
        assert 'concurrency' in self.ci_config
        concurrency = self.ci_config['concurrency']
        assert 'group' in concurrency
        assert 'cancel-in-progress' in concurrency
        assert concurrency['cancel-in-progress'] is True

    def test_ci_has_all_four_jobs(self):
        """Verify all four required jobs are defined."""
        assert 'jobs' in self.ci_config
        jobs = self.ci_config['jobs']

        required_jobs = {'lint', 'test', 'typecheck', 'security'}
        assert set(jobs.keys()) >= required_jobs, \
            f"Missing jobs. Found: {set(jobs.keys())}, Expected at least: {required_jobs}"

    def test_lint_job_exists_and_runs_ruff(self):
        """Verify lint job runs ruff check and format check."""
        jobs = self.ci_config['jobs']
        assert 'lint' in jobs
        lint_job = jobs['lint']

        assert 'steps' in lint_job
        steps = lint_job['steps']
        step_names = [s.get('name', '') for s in steps]

        assert any('ruff check' in name for name in step_names), \
            "Lint job should include ruff check step"
        assert any('ruff format' in name for name in step_names), \
            "Lint job should include ruff format check step"

    def test_test_job_has_python_matrix(self):
        """Verify test job has Python 3.10 and 3.12 matrix."""
        jobs = self.ci_config['jobs']
        assert 'test' in jobs
        test_job = jobs['test']

        assert 'strategy' in test_job
        strategy = test_job['strategy']
        assert 'matrix' in strategy

        matrix = strategy['matrix']
        assert 'python-version' in matrix
        python_versions = matrix['python-version']

        assert '3.10' in python_versions
        assert '3.12' in python_versions

    def test_test_job_has_fail_fast_false(self):
        """Verify test matrix has fail-fast set to false."""
        jobs = self.ci_config['jobs']
        test_job = jobs['test']
        strategy = test_job['strategy']

        assert strategy.get('fail-fast') is False, \
            "Test job should have fail-fast: false to run all versions"

    def test_test_job_has_postgres_service(self):
        """Verify test job has PostgreSQL service."""
        jobs = self.ci_config['jobs']
        test_job = jobs['test']

        assert 'services' in test_job
        services = test_job['services']
        assert 'postgres' in services

        postgres_service = services['postgres']
        assert 'image' in postgres_service
        # Should be postgres or postgis for PostGIS support
        image = postgres_service['image']
        assert 'postgis' in image or 'postgres' in image, \
            f"Image should be postgres or postgis, got {image}"

    def test_test_job_has_junit_xml_output(self):
        """Verify test job generates JUnit XML output."""
        jobs = self.ci_config['jobs']
        test_job = jobs['test']
        steps = test_job['steps']

        pytest_steps = [s for s in steps if 'pytest' in s.get('name', '').lower()]
        assert len(pytest_steps) > 0, "Test job should have a pytest step"

        pytest_step = pytest_steps[0]
        assert 'run' in pytest_step
        run_command = pytest_step['run']

        assert '--junitxml' in run_command, \
            "pytest should output JUnit XML"

    def test_test_job_has_coverage_report(self):
        """Verify test job generates coverage report."""
        jobs = self.ci_config['jobs']
        test_job = jobs['test']
        steps = test_job['steps']

        pytest_steps = [s for s in steps if 'pytest' in s.get('name', '').lower()]
        pytest_step = pytest_steps[0]
        run_command = pytest_step['run']

        assert '--cov' in run_command, \
            "pytest should include coverage"
        assert '--cov-report' in run_command, \
            "pytest should generate coverage reports"

    def test_test_job_uploads_artifacts(self):
        """Verify test job uploads test results and coverage."""
        jobs = self.ci_config['jobs']
        test_job = jobs['test']
        steps = test_job['steps']

        upload_steps = [s for s in steps if 'upload' in s.get('name', '').lower()]
        assert len(upload_steps) > 0, "Test job should upload artifacts"

        # Check for JUnit XML artifact upload
        junit_uploads = [s for s in upload_steps
                        if 'junit' in str(s.get('with', {}).get('path', '')).lower()]
        assert len(junit_uploads) > 0, "Test job should upload JUnit XML"

    def test_test_job_uses_test_reporter(self):
        """Verify test job uses dorny/test-reporter for PR results."""
        jobs = self.ci_config['jobs']
        test_job = jobs['test']
        steps = test_job['steps']

        test_reporter_steps = [s for s in steps
                              if 'test-reporter' in s.get('uses', '')]
        assert len(test_reporter_steps) > 0, \
            "Test job should use dorny/test-reporter"

    def test_typecheck_job_exists_and_runs_mypy(self):
        """Verify typecheck job runs mypy with continue-on-error."""
        jobs = self.ci_config['jobs']
        assert 'typecheck' in jobs
        typecheck_job = jobs['typecheck']

        assert 'steps' in typecheck_job
        steps = typecheck_job['steps']
        step_names = [s.get('name', '') for s in steps]

        mypy_steps = [s for s in steps if 'mypy' in s.get('name', '').lower()]
        assert len(mypy_steps) > 0, "Typecheck job should include mypy step"

        mypy_step = mypy_steps[0]
        assert mypy_step.get('continue-on-error') is True, \
            "mypy step should have continue-on-error: true"

    def test_security_job_exists_and_runs_pip_audit(self):
        """Verify security job runs pip-audit with continue-on-error."""
        jobs = self.ci_config['jobs']
        assert 'security' in jobs
        security_job = jobs['security']

        assert 'steps' in security_job
        steps = security_job['steps']

        # Find the step that runs pip-audit scan (not the install step)
        audit_steps = [s for s in steps
                      if s.get('run') and 'pip-audit' in s.get('run', '')
                      and '--desc' in s.get('run', '')]
        assert len(audit_steps) > 0, "Security job should include pip-audit scan step"

        audit_step = audit_steps[0]
        assert audit_step.get('continue-on-error') is True, \
            "pip-audit step should have continue-on-error: true"

    def test_ci_has_environment_variables(self):
        """Verify CI config defines necessary environment variables."""
        assert 'env' in self.ci_config
        env = self.ci_config['env']

        assert 'DATABASE_URL' in env
        assert 'ANTHROPIC_API_KEY' in env
        assert 'COHERE_API_KEY' in env

    def test_jobs_have_caching(self):
        """Verify critical jobs have pip cache configured."""
        jobs = self.ci_config['jobs']

        for job_name in ['lint', 'test', 'typecheck', 'security']:
            assert job_name in jobs
            job = jobs[job_name]
            steps = job.get('steps', [])

            cache_steps = [s for s in steps if 'cache' in s.get('uses', '')]
            assert len(cache_steps) > 0, \
                f"{job_name} job should have pip cache configured"


class TestReleaseConfig:
    """Tests for .github/workflows/release.yml"""

    @classmethod
    def setup_class(cls):
        """Load release configuration file."""
        release_path = Path(__file__).parent.parent / '.github' / 'workflows' / 'release.yml'
        assert release_path.exists(), f"Release configuration not found at {release_path}"

        with open(release_path, 'r') as f:
            cls.release_config = yaml.safe_load(f)

    def test_release_config_valid_yaml(self):
        """Verify release.yml is valid YAML."""
        assert isinstance(self.release_config, dict), "Release config should be a dictionary"

    def test_release_config_has_name(self):
        """Verify release workflow has a name."""
        assert 'name' in self.release_config
        assert self.release_config['name'] == 'Release'

    def test_release_triggers_on_tag_push(self):
        """Verify release triggers on version tag push."""
        # YAML parses 'on:' as boolean True key
        on_config = self.release_config.get('on') or self.release_config.get(True)
        assert on_config is not None, "Config should have 'on' trigger"
        assert 'push' in on_config

        push_config = on_config['push']
        assert 'tags' in push_config
        tags = push_config['tags']

        assert 'v*' in tags, "Should trigger on v* tags"

    def test_release_has_release_job(self):
        """Verify release workflow has a release job."""
        assert 'jobs' in self.release_config
        jobs = self.release_config['jobs']
        assert 'release' in jobs

    def test_release_job_has_docker_build_step(self):
        """Verify release job builds Docker image."""
        jobs = self.release_config['jobs']
        release_job = jobs['release']
        steps = release_job.get('steps', [])

        docker_build_steps = [s for s in steps
                             if 'build' in s.get('uses', '').lower() and 'docker' in s.get('uses', '').lower()]
        assert len(docker_build_steps) > 0, \
            "Release job should have docker build step"

    def test_release_job_pushes_to_ghcr(self):
        """Verify release job pushes to GitHub Container Registry."""
        jobs = self.release_config['jobs']
        release_job = jobs['release']
        steps = release_job.get('steps', [])

        docker_build_steps = [s for s in steps
                             if 'build-push' in s.get('uses', '')]
        assert len(docker_build_steps) > 0, "Should have docker/build-push-action"

        docker_step = docker_build_steps[0]
        build_config = docker_step.get('with', {})

        tags = str(build_config.get('tags', ''))
        assert len(tags) > 0, "Tags should be configured"
        assert 'image' in tags or 'ghcr' in tags, \
            "Should push to GitHub Container Registry"

    def test_release_job_logs_in_to_registry(self):
        """Verify release job logs into container registry."""
        jobs = self.release_config['jobs']
        release_job = jobs['release']
        steps = release_job.get('steps', [])

        login_steps = [s for s in steps if 'login' in s.get('uses', '').lower()]
        assert len(login_steps) > 0, "Release job should log in to registry"

    def test_release_job_creates_github_release(self):
        """Verify release job creates GitHub release."""
        jobs = self.release_config['jobs']
        release_job = jobs['release']
        steps = release_job.get('steps', [])

        release_steps = [s for s in steps if 'release' in s.get('uses', '').lower()]
        assert len(release_steps) > 0, "Release job should create GitHub release"

    def test_release_job_has_permissions(self):
        """Verify release job has necessary permissions."""
        jobs = self.release_config['jobs']
        release_job = jobs['release']

        assert 'permissions' in release_job, "Release job should define permissions"
        permissions = release_job['permissions']

        assert 'contents' in permissions or 'write' in str(permissions)
        assert 'packages' in permissions or 'write' in str(permissions)

    def test_release_extracts_version_from_tag(self):
        """Verify release job extracts version from tag."""
        jobs = self.release_config['jobs']
        release_job = jobs['release']
        steps = release_job.get('steps', [])

        meta_steps = [s for s in steps if 'version' in s.get('name', '').lower()]
        assert len(meta_steps) > 0, "Release job should extract version from tag"

    def test_release_tags_with_version_and_latest(self):
        """Verify Docker image is tagged with both version and latest."""
        jobs = self.release_config['jobs']
        release_job = jobs['release']
        steps = release_job.get('steps', [])

        docker_build_steps = [s for s in steps
                             if 'build-push' in s.get('uses', '')]
        assert len(docker_build_steps) > 0

        docker_step = docker_build_steps[0]
        build_config = docker_step.get('with', {})
        tags = str(build_config.get('tags', ''))

        assert len(tags) > 0, "Tags should be defined"
        assert 'image' in tags, "Should reference image variables"
        assert 'latest' in tags.lower(), "Should include latest tag"
