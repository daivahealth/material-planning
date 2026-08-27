import logging
import secrets as _secrets

from pydantic_settings import BaseSettings

log = logging.getLogger("config")

# Values that shipped as defaults in earlier builds. If one of these is still in
# use the deployment is insecure — every token is forgeable / every stored
# source-DB password is decryptable by anyone with the source tree.
_KNOWN_INSECURE = {
    "medplan-jwt-secret-change-in-production-please",
    "pIGqOca8iKkeGdeI8VTlJJvqcriKkECZv_cZs6IoVvo=",
}


class Settings(BaseSettings):
    database_url: str = "postgresql://matplan:matplan@localhost:5432/matplan"

    # Fernet key protecting external-DB passwords (data mining + outbound).
    # MUST be supplied per environment: it decrypts data already at rest, so it
    # cannot be auto-generated or rotated without re-entering those passwords.
    mining_secret_key: str = ""

    # JWT / Auth. Blank → a random key is generated at startup (see _harden),
    # so no build ever ships with a known signing key.
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440  # 24 hours

    # Comma-separated list of allowed browser origins, e.g.
    # "https://matplan.example.org". "*" is rejected because credentials are
    # allowed (browsers reject that combination too).
    cors_allow_origins: str = "http://localhost:14030,http://127.0.0.1:14030"

    # Password for the auto-seeded `admin` account on a fresh database. Blank →
    # a random one is generated and printed once at startup, so no build ships
    # with a publicly-known admin password.
    admin_initial_password: str = ""

    # Root log level for the app's own loggers. DEBUG emits per-row mining and
    # per-item indent detail — keep at INFO or higher in production.
    log_level: str = "INFO"

    # SQLAlchemy connection pool. Raise these if scheduled jobs (outbound
    # dispatch, data mining) run while the API is under load — a long job holds
    # one connection for its whole run.
    db_pool_size: int = 10
    db_max_overflow: int = 20

    # Brute-force protection on login. Failures are counted per username and
    # per source IP over a sliding window; exceeding the limit locks that key
    # for `login_lockout_minutes`. Set login_max_attempts to 0 to disable.
    login_max_attempts: int = 5
    login_window_minutes: int = 15
    login_lockout_minutes: int = 15

    # Account lockout: after this many CONSECUTIVE wrong passwords the account
    # is locked in the database and stays locked until an administrator (or a
    # DBA, via SQL) releases it. The counter resets on any successful login.
    # Set to 0 to disable account locking (the IP/username throttle above still
    # applies). This is separate from the throttle: the throttle is a temporary
    # rate limit, this is a durable account state.
    account_lockout_threshold: int = 5

    # Password rotation. After this many days a password is expired: the user
    # can still authenticate, but every endpoint except "change my password"
    # is refused until they set a new one. 0 disables rotation.
    password_max_age_days: int = 90
    # Start warning the user this many days before expiry.
    password_expiry_warning_days: int = 7

    # Whether to take the client IP from the X-Forwarded-For header.
    # Leave FALSE unless the app sits behind a proxy you control that
    # overwrites this header: when true, any caller can spoof their source
    # address and bypass the IP allowlist by sending X-Forwarded-For.
    # When the app IS behind a proxy this must be true, otherwise every request
    # appears to come from the proxy's own address.
    trust_proxy_headers: bool = False

    # Timezone for cron schedules — cron expressions entered in the UI are
    # interpreted in this timezone rather than UTC.
    timezone: str = "Asia/Kolkata"

    # Kafka bootstrap servers (comma-separated host:port) for the outbound
    # request-number publisher. Provided at deploy; the Outbound Settings row
    # may override it. Blank disables publishing (outbox rows just wait).
    kafka_brokers: str = ""

    class Config:
        env_file = ".env"

    @property
    def cors_origin_list(self) -> list:
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]


settings = Settings()


def _harden() -> None:
    """Fail closed on known-insecure secrets; generate what can be generated."""
    if settings.jwt_secret_key in _KNOWN_INSECURE:
        raise RuntimeError(
            "JWT_SECRET_KEY is set to a value that shipped in the source tree — "
            "every issued token would be forgeable. Set a fresh secret "
            "(e.g. `openssl rand -hex 32`) via the JWT_SECRET_KEY env var."
        )
    if not settings.jwt_secret_key:
        settings.jwt_secret_key = _secrets.token_urlsafe(48)
        log.critical(
            "JWT_SECRET_KEY not set — generated a random key for this process. "
            "Sessions are invalidated on restart and replicas reject each "
            "other's tokens. Set JWT_SECRET_KEY in production."
        )
    if settings.mining_secret_key in _KNOWN_INSECURE:
        log.critical(
            "MINING_SECRET_KEY is the value that shipped in the source tree — "
            "all stored external-DB passwords are decryptable by anyone with "
            "the repo. Rotate it and re-enter the data-mining/outbound passwords."
        )
    if not settings.mining_secret_key:
        log.warning(
            "MINING_SECRET_KEY not set — data-mining/outbound credentials cannot "
            "be encrypted or decrypted until it is provided."
        )
    if "*" in settings.cors_origin_list:
        raise RuntimeError(
            "CORS_ALLOW_ORIGINS must not be '*': credentials are allowed, and a "
            "wildcard with credentials is insecure and rejected by browsers. "
            "List the exact origins instead."
        )


_harden()
