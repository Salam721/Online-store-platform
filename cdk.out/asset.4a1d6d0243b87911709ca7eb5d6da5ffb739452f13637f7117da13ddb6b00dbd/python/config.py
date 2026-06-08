"""
Centralised configuration — reads from Parameter Store with lru_cache fallback to env vars.
Naming convention: /store/{env}/{key}
"""
import os, logging, boto3
from functools import lru_cache

logger = logging.getLogger(__name__)
_ssm   = None

def _get_ssm():
    global _ssm
    if _ssm is None:
        _ssm = boto3.client('ssm')
    return _ssm

def get_env():
    return os.environ.get('APP_ENV', 'dev')

@lru_cache(maxsize=128)
def get_parameter(key):
    """Fetch from Parameter Store; fall back to env var if unavailable."""
    env  = get_env()
    name = f"/store/{env}/{key}"
    try:
        return _get_ssm().get_parameter(Name=name)['Parameter']['Value']
    except Exception as e:
        logger.warning(f"Parameter Store unavailable for {name}, using env var: {e}")
        return os.environ.get(key.upper().replace('/', '_'), '')

def get_products_table():
    return get_parameter('products_table') or os.environ.get('PRODUCTS_TABLE', 'Products')

def get_image_bucket():
    return get_parameter('image_bucket') or os.environ.get('PRODUCT_IMAGE_BUCKET', '')

def get_cache_endpoint():
    return get_parameter('cache_endpoint') or os.environ.get('CACHE_ENDPOINT', 'localhost')

def get_timeout_setting(key, default=30, min_val=1, max_val=300):
    raw = os.environ.get(key.upper(), str(default))
    try:
        return max(min_val, min(int(raw), max_val))
    except ValueError:
        return default
