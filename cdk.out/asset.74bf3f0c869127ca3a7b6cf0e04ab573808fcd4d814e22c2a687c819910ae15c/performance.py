"""
Performance utilities for Lambda functions.

Provides:
  - timeout_guard: check remaining execution time early, log a warning
  - timed: decorator that logs execution duration and memory usage
  - ETag generation for HTTP conditional requests
  - CloudFront cache invalidation helper
  - In-memory L1 cache (persists across warm invocations in same container)

CloudWatch Logs Insights queries for profiling (run in the CW console):

  # Average/peak duration + memory usage per 5-min bucket
  fields @timestamp, @duration, @memorySize, @maxMemoryUsed
  | filter @type = "REPORT"
  | stats avg(@duration), max(@duration), avg(@maxMemoryUsed) by bin(5m)

  # Cold start frequency
  fields @timestamp, @initDuration
  | filter @type = "REPORT" AND @initDuration > 0
  | stats count() as cold_starts by bin(1h)

  # Slow invocations (> 3 seconds)
  fields @timestamp, @duration, @requestId
  | filter @type = "REPORT" AND @duration > 3000
  | sort @duration desc
  | limit 50
"""
import time, json, hashlib, logging, os
from functools import wraps

logger = logging.getLogger(__name__)

# ── Timeout guard ─────────────────────────────────────────────────────────────
def timeout_guard(context, buffer_ms: int = 5000) -> None:
    """
    Raise TimeoutError if remaining execution time < buffer_ms.
    Call this early in the handler to fail fast rather than hit the hard limit.
    """
    remaining = context.get_remaining_time_in_millis()
    if remaining < buffer_ms:
        raise TimeoutError(
            f"Only {remaining}ms remaining — insufficient for safe processing")


# ── Execution timer decorator ─────────────────────────────────────────────────
def timed(fn):
    """Log execution duration and memory stats after each invocation."""
    @wraps(fn)
    def wrapper(event, context, *args, **kwargs):
        start = time.time()
        try:
            result = fn(event, context, *args, **kwargs)
            elapsed = (time.time() - start) * 1000
            logger.info(json.dumps({
                'event':       'lambda_timing',
                'function':    context.function_name,
                'duration_ms': round(elapsed, 2),
                'memory_mb':   context.memory_limit_in_mb,
            }))
            return result
        except Exception as e:
            elapsed = (time.time() - start) * 1000
            logger.error(json.dumps({
                'event':       'lambda_error',
                'function':    context.function_name,
                'duration_ms': round(elapsed, 2),
                'error':       str(e),
            }))
            raise
    return wrapper


# ── ETag helpers ──────────────────────────────────────────────────────────────
def generate_etag(content: str, last_modified: str = '') -> str:
    """Generate a weak ETag by hashing content + last_modified timestamp."""
    digest = hashlib.md5(f"{content}{last_modified}".encode()).hexdigest()
    return f'"{digest}"'


def check_etag(event: dict, current_etag: str) -> bool:
    """Return True if client's If-None-Match matches current_etag (304 candidate)."""
    client_etag = (event.get('headers') or {}).get('If-None-Match', '')
    return client_etag == current_etag


# ── Cache-Control header builders ─────────────────────────────────────────────
def cache_headers(data_type: str) -> dict:
    """
    Return appropriate Cache-Control headers per content type.
    data_type: 'static' | 'api' | 'user' | 'no_cache'
    """
    directives = {
        'static':   'public, max-age=31536000, immutable',   # 1 year
        'api':      'public, max-age=600',                   # 10 min
        'user':     'private, max-age=300',                  # 5 min browser-only
        'no_cache': 'no-cache',
    }
    return {'Cache-Control': directives.get(data_type, 'no-cache')}


# ── In-memory L1 cache (lives inside Lambda container) ───────────────────────
_L1: dict = {}

_TTL_MAP = {
    'product_details':  3600,
    'product_inventory': 300,
    'user_preferences': 1800,
    'search_results':    600,
    'config':           7200,
}


def l1_get(cache_type: str, key: str):
    """Return cached value or None if missing / expired."""
    full_key = f"{cache_type}:{key}"
    entry = _L1.get(full_key)
    if entry and time.time() < entry['expires_at']:
        return entry['data']
    if entry:
        del _L1[full_key]
    return None


def l1_set(cache_type: str, key: str, data) -> None:
    """Store value in L1 with TTL appropriate for cache_type."""
    ttl = _TTL_MAP.get(cache_type, 300)
    _L1[f"{cache_type}:{key}"] = {'data': data, 'expires_at': time.time() + ttl}


def l1_delete(cache_type: str, key: str) -> None:
    _L1.pop(f"{cache_type}:{key}", None)


def l1_clear_type(cache_type: str) -> None:
    prefix = f"{cache_type}:"
    for k in list(_L1.keys()):
        if k.startswith(prefix):
            del _L1[k]


# ── CloudFront invalidation ───────────────────────────────────────────────────
def invalidate_cloudfront(distribution_id: str, paths: list[str]) -> str | None:
    """
    Invalidate specific CloudFront paths after a product update.
    Returns invalidation ID or None if distribution_id not configured.
    """
    if not distribution_id:
        return None
    try:
        import boto3
        cf = boto3.client('cloudfront')
        resp = cf.create_invalidation(
            DistributionId=distribution_id,
            InvalidationBatch={
                'Paths': {'Quantity': len(paths), 'Items': paths},
                'CallerReference': str(int(time.time())),
            })
        inv_id = resp['Invalidation']['Id']
        logger.info(json.dumps({'event': 'cf_invalidation', 'id': inv_id, 'paths': paths}))
        return inv_id
    except Exception as e:
        logger.warning(f"CloudFront invalidation failed: {e}")
        return None
