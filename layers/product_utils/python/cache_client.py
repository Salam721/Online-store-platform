import os, json, logging
import redis

logger = logging.getLogger(__name__)

CACHE_TTL = {
    'product_details':  3600,
    'search_results':   1800,
    'category_lists':   7200,
    'inventory_counts':  300,
    'user_sessions':   86400,
    'popular_products': 3600,
}

_client = None

def get_client():
    global _client
    if _client is None:
        host = os.environ.get('CACHE_ENDPOINT', 'localhost')
        port = int(os.environ.get('CACHE_PORT', 6379))
        _client = redis.Redis(host=host, port=port, decode_responses=True,
                              socket_connect_timeout=5, socket_timeout=5)
    return _client

def cache_get(key):
    try:
        val = get_client().get(key)
        return json.loads(val) if val else None
    except Exception as e:
        logger.warning(f"Cache get failed for {key}: {e}")
        return None

def cache_set(key, data, data_type='product_details'):
    ttl = CACHE_TTL.get(data_type, 3600)
    try:
        get_client().setex(key, ttl, json.dumps(data, default=str))
    except Exception as e:
        logger.warning(f"Cache set failed for {key}: {e}")

def cache_delete(key):
    try:
        get_client().delete(key)
    except Exception as e:
        logger.warning(f"Cache delete failed for {key}: {e}")

def cache_invalidate_product(product_id, category=None):
    cache_delete(f"product:{product_id}")
    try:
        client = get_client()
        for key in client.scan_iter(match="search:*"):
            client.delete(key)
        if category:
            for key in client.scan_iter(match=f"category:{category}:*"):
                client.delete(key)
    except Exception as e:
        logger.warning(f"Cache invalidation failed: {e}")
