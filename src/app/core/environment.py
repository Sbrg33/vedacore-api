"""
Environment configuration with local/remote toggle.

Implements PM guidance for zero-cost local development with single toggle
between local and Supabase environments.
"""

import os

from dataclasses import dataclass
from typing import Literal

EnvironmentType = Literal["local", "remote"]


@dataclass
class DatabaseConfig:
    """Database configuration for environment."""

    url: str
    require_tenant: bool
    auth_secret: str
    jwks_url: str | None = None


@dataclass
class StreamingConfig:
    """Streaming configuration for environment."""

    dev_publish_enabled: bool
    dev_publish_token: str
    rate_limit_enabled: bool
    metrics_enabled: bool


@dataclass
class EnvironmentConfig:
    """Complete environment configuration."""

    env_type: EnvironmentType
    database: DatabaseConfig
    streaming: StreamingConfig
    debug: bool
    feature_v1_routing: bool


def get_environment() -> EnvironmentType:
    """Get current environment from VC_ENV variable."""
    env = os.getenv("VC_ENV", "local").lower()
    if env in ("local", "remote"):
        return env  # type: ignore[return-value]
    return "local"  # Default fallback


def get_database_config() -> DatabaseConfig:
    """Get database configuration based on environment."""
    env = get_environment()

    if env == "local":
        return DatabaseConfig(
            url=os.getenv(
                "DATABASE_URL", "postgresql://postgres:devpass@localhost:5432/postgres"
            ),
            require_tenant=os.getenv("AUTH_REQUIRE_TENANT", "0") == "1",
            auth_secret=os.getenv("AUTH_JWT_SECRET", "dev-secret-for-local-streaming"),
            jwks_url=None,  # Use HS256 for local
        )
    else:  # remote (Supabase)
        url = os.getenv("SUPABASE_DATABASE_URL") or os.getenv("DATABASE_URL")
        if not url:
            raise ValueError(
                "Database URL required for remote environment. Set SUPABASE_DATABASE_URL or DATABASE_URL"
            )

        auth_secret = os.getenv("SUPABASE_JWT_SECRET") or os.getenv("AUTH_JWT_SECRET")
        if not auth_secret:
            raise ValueError(
                "Auth secret required for remote environment. Set SUPABASE_JWT_SECRET or AUTH_JWT_SECRET"
            )

        return DatabaseConfig(
            url=url,
            require_tenant=True,  # Always require tenant in remote
            auth_secret=auth_secret,
            jwks_url=os.getenv(
                "SUPABASE_JWKS_URL"
            ),  # Use JWKS for Supabase if available
        )


def get_streaming_config() -> StreamingConfig:
    """Get streaming configuration based on environment."""
    env = get_environment()

    if env == "local":
        return StreamingConfig(
            dev_publish_enabled=True,  # Always enabled in local
            dev_publish_token=os.getenv("STREAM_DEV_PUBLISH_TOKEN", "dev-pub-123"),
            rate_limit_enabled=os.getenv("RATE_LIMIT_ENABLED", "1") == "1",
            metrics_enabled=True,
        )
    else:  # remote
        return StreamingConfig(
            dev_publish_enabled=os.getenv("STREAM_DEV_PUBLISH_ENABLED", "false").lower()
            == "true",
            dev_publish_token=os.getenv("STREAM_DEV_PUBLISH_TOKEN", ""),
            rate_limit_enabled=True,  # Always enabled in remote
            metrics_enabled=True,
        )


def get_complete_config() -> EnvironmentConfig:
    """Get complete environment configuration."""
    env = get_environment()

    return EnvironmentConfig(
        env_type=env,
        database=get_database_config(),
        streaming=get_streaming_config(),
        debug=env == "local",
        feature_v1_routing=os.getenv("FEATURE_V1_ROUTING", "true").lower() == "true",
    )


def create_environment_files() -> None:
    """Create environment file templates."""

    local_env = """# VedaCore Local Development Environment
# Zero-cost development with Docker Postgres + pgvector

VC_ENV=local
AUTH_JWT_SECRET=dev-secret-for-local-streaming
AUTH_REQUIRE_TENANT=0
WEB_CONCURRENCY=1
STREAM_DEV_PUBLISH_TOKEN=dev-pub-123
DATABASE_URL=postgresql://postgres:devpass@localhost:5432/postgres

# Optional: Metrics
PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus
RATE_LIMIT_ENABLED=1

# Optional: Debug (keep app-local imports only)
# PYTHONPATH can be set per-shell if needed; recommended default is repo-local
PYTHONPATH=./src:.
RUST_LOG=debug
"""

    supabase_local_env = """# VedaCore Supabase Local Environment  
# Professional setup with RLS testing

VC_ENV=local
DATABASE_URL=postgresql://postgres:postgres@localhost:54322/postgres
SUPABASE_URL=http://localhost:54321
SUPABASE_ANON_KEY=<from_supabase_start_output>
AUTH_JWT_SECRET=<supabase_jwt_secret>
AUTH_REQUIRE_TENANT=1
STREAM_DEV_PUBLISH_TOKEN=dev-pub-123
WEB_CONCURRENCY=1

# RLS Testing
SUPABASE_SERVICE_ROLE_KEY=<from_supabase_start_output>
"""

    remote_env = """# VedaCore Remote Environment (Supabase Cloud)
# Use sparingly to stay within $10 credit

VC_ENV=remote
DATABASE_URL=<supabase_pooled_connection_string>
SUPABASE_DATABASE_URL=<supabase_direct_connection_string>
SUPABASE_URL=<your_supabase_url>
SUPABASE_ANON_KEY=<your_anon_key>
SUPABASE_JWT_SECRET=<your_jwt_secret>
AUTH_REQUIRE_TENANT=1
STREAM_DEV_PUBLISH_ENABLED=false
STREAM_DEV_PUBLISH_TOKEN=""
WEB_CONCURRENCY=4

# Production settings
RATE_LIMIT_ENABLED=1
PROMETHEUS_MULTIPROC_DIR=/var/lib/prometheus
"""

    # Write environment templates
    with open(".env.local.template", "w") as f:
        f.write(local_env)

    with open(".env.supabase-local.template", "w") as f:
        f.write(supabase_local_env)

    with open(".env.remote.template", "w") as f:
        f.write(remote_env)


# Environment validation
def validate_environment() -> list[str]:
    """Validate current environment configuration."""
    config = get_complete_config()
    issues = []

    # Check database URL
    if not config.database.url:
        issues.append("DATABASE_URL not configured")

    # Check auth secret
    if not config.database.auth_secret:
        issues.append("AUTH_JWT_SECRET not configured")

    # Check remote-specific requirements
    if config.env_type == "remote":
        if (
            config.streaming.dev_publish_enabled
            and not config.streaming.dev_publish_token
        ):
            issues.append("Dev publish enabled but no token in remote environment")

    # Check local-specific requirements
    if config.env_type == "local":
        if (
            "localhost" not in config.database.url
            and "127.0.0.1" not in config.database.url
        ):
            issues.append("Local environment should use localhost database")

    return issues


def print_environment_status() -> None:
    """Print current environment configuration status."""
    config = get_complete_config()
    issues = validate_environment()

    print(f"🔧 VedaCore Environment: {config.env_type.upper()}")
    print(
        f"📊 Database: {'✅' if config.database.url else '❌'} {config.database.url[:50]}..."
    )
    print(
        f"🔐 Auth: {'✅' if config.database.auth_secret else '❌'} {'JWKS' if config.database.jwks_url else 'HS256'}"
    )
    print(f"🏢 Tenant Required: {'✅' if config.database.require_tenant else '❌'}")
    print(f"🚀 Dev Publish: {'✅' if config.streaming.dev_publish_enabled else '❌'}")
    print(f"⚡ Rate Limiting: {'✅' if config.streaming.rate_limit_enabled else '❌'}")
    print(f"📈 Metrics: {'✅' if config.streaming.metrics_enabled else '❌'}")

    if issues:
        print("\n⚠️  Configuration Issues:")
        for issue in issues:
            print(f"   - {issue}")
    else:
        print("\n✅ Environment configuration valid!")


# CLI helper
if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "create-templates":
        create_environment_files()
        print("✅ Environment templates created:")
        print("   - .env.local.template")
        print("   - .env.supabase-local.template")
        print("   - .env.remote.template")
    else:
        print_environment_status()
