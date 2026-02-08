"""
VanCity Lens — Secrets Configuration Metadata

Defines all known secrets with their environment variable names, Docker secret paths,
production requirements, and descriptions.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class SecretDefinition:
    """Metadata for a single secret."""

    name: str
    """Friendly name (e.g., 'anthropic_key', 'database_url')."""

    env_var: str
    """Environment variable name (e.g., 'ANTHROPIC_API_KEY')."""

    docker_secret_path: Optional[str]
    """Path to Docker secret file if using swarm/k8s (e.g., '/run/secrets/anthropic_key')."""

    required_in_production: bool
    """If True, missing secret in production causes startup failure."""

    description: str
    """Human-readable description of what this secret is for."""


# All known secrets across VanCity Lens
SECRET_DEFINITIONS = [
    SecretDefinition(
        name="database_url",
        env_var="DATABASE_URL",
        docker_secret_path="/run/secrets/database_url",
        required_in_production=True,
        description="PostgreSQL connection string (with credentials)",
    ),
    SecretDefinition(
        name="anthropic_key",
        env_var="ANTHROPIC_API_KEY",
        docker_secret_path="/run/secrets/anthropic_key",
        required_in_production=True,
        description="Claude API key for signal extraction and chat",
    ),
    SecretDefinition(
        name="cohere_key",
        env_var="COHERE_API_KEY",
        docker_secret_path="/run/secrets/cohere_key",
        required_in_production=True,
        description="Cohere API key for embeddings and reranking",
    ),
    SecretDefinition(
        name="admin_key",
        env_var="ADMIN_API_KEY",
        docker_secret_path="/run/secrets/admin_key",
        required_in_production=True,
        description="Admin API key for protected endpoints",
    ),
    SecretDefinition(
        name="mapbox_token",
        env_var="MAPBOX_TOKEN",
        docker_secret_path="/run/secrets/mapbox_token",
        required_in_production=False,
        description="Mapbox GL token for frontend maps (optional)",
    ),
]
