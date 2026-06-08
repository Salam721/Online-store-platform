"""
AppConfig feature flag client with in-memory caching.

Fetches feature flags once per Lambda container lifetime.
Use force_refresh=True after a suspected config change.

Usage:
    from appconfig_flags import is_enabled, get_flag

    if is_enabled('ai-recommendations'):
        return serve_ai_recommendations(user_id)

    rollout = get_flag('new-checkout-flow', {})
    if rollout.get('enabled') and _in_rollout(user_id, rollout.get('rollout-percentage', 0)):
        return new_checkout(event)
"""
import os, json, logging, hashlib
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

_appconfig  = None
_flag_cache: dict | None = None

APP_NAME    = os.environ.get('APPCONFIG_APP',     'online-store')
ENV_NAME    = os.environ.get('APPCONFIG_ENV',     'dev')
CONFIG_NAME = os.environ.get('APPCONFIG_PROFILE', 'feature-flags')
CLIENT_ID   = os.environ.get('APPCONFIG_CLIENT',  'lambda')


def _client():
    global _appconfig
    if _appconfig is None:
        _appconfig = boto3.client('appconfig')
    return _appconfig


def get_flags(force_refresh: bool = False) -> dict:
    """Return the 'values' section of the feature flag config."""
    global _flag_cache
    if not force_refresh and _flag_cache is not None:
        return _flag_cache
    try:
        resp = _client().get_configuration(
            Application=APP_NAME,
            Environment=ENV_NAME,
            Configuration=CONFIG_NAME,
            ClientId=CLIENT_ID,
        )
        content = resp['Content'].read()
        if content:
            data        = json.loads(content)
            _flag_cache = data.get('values', {})
            logger.info(f"Loaded feature flags: {list(_flag_cache.keys())}")
        # If content is empty, AppConfig returned unchanged config — reuse cache
        return _flag_cache or {}
    except ClientError as e:
        logger.warning(f"AppConfig unavailable: {e}. Using defaults.")
        return _flag_cache or {}


def get_flag(flag_name: str, default=None):
    """Return the value dict for a single flag, or default if not found."""
    return get_flags().get(flag_name, default if default is not None else {})


def is_enabled(flag_name: str) -> bool:
    """Return True if the flag exists and has enabled=True."""
    return bool(get_flag(flag_name).get('enabled', False))


def in_rollout(flag_name: str, user_id: str) -> bool:
    """
    Return True if user_id falls within the rollout percentage for flag_name.
    Uses consistent hashing so the same user always gets the same experience.
    """
    flag = get_flag(flag_name)
    if not flag.get('enabled', False):
        return False
    pct  = flag.get('rollout-percentage', 0)
    # Consistent hash: user always gets same bucket 0-99
    bucket = int(hashlib.md5(f"{flag_name}:{user_id}".encode()).hexdigest(), 16) % 100
    return bucket < pct
