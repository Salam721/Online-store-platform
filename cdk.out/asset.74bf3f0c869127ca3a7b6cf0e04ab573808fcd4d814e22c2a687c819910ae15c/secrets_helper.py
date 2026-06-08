"""
Thin wrapper around AWS Secrets Manager with in-memory caching.

Secrets are fetched once per Lambda container lifetime and cached.
Cache is invalidated when get_secret is called with force_refresh=True,
which should happen after rotation events.

Usage:
    from secrets_helper import get_secret, get_payment_api_key
    api_key = get_payment_api_key()
"""
import json, logging, os
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

_client = None
_cache: dict = {}


def _secrets_client():
    global _client
    if _client is None:
        _client = boto3.client('secretsmanager')
    return _client


def get_secret(secret_name: str, force_refresh: bool = False) -> dict:
    """
    Retrieve and cache a JSON secret from Secrets Manager.
    Returns the parsed dict. Raises on failure.
    """
    if not force_refresh and secret_name in _cache:
        return _cache[secret_name]
    try:
        resp   = _secrets_client().get_secret_value(SecretId=secret_name)
        secret = json.loads(resp['SecretString'])
        _cache[secret_name] = secret
        logger.info(f"Retrieved secret: {secret_name}")
        return secret
    except ClientError as e:
        logger.error(f"Failed to retrieve secret {secret_name}: {e}")
        raise


def get_payment_api_key() -> str:
    """Return the payment processor API key from Secrets Manager."""
    secret_name = os.environ.get('PAYMENT_SECRET_NAME', 'prod/payment/api-key')
    return get_secret(secret_name)['api_key']


def get_db_credentials() -> dict:
    """Return database username and password."""
    secret_name = os.environ.get('DB_SECRET_NAME', 'prod/database/credentials')
    return get_secret(secret_name)
