import logging, traceback
import products_db
from cache_client import cache_get, cache_set
from response_utils import create_success_response, create_error_response
from circuit_breaker import CircuitBreakerOpenError

logger = logging.getLogger(__name__)

def handler(event, context):
    try:
        params   = event.get('queryStringParameters') or {}
        category = params.get('category')
        cache_key = f"search:all:{category or 'all'}"
        cached    = cache_get(cache_key)
        if cached:
            return create_success_response(200, cached)
        products = (products_db.get_products_by_category(category)
                    if category else products_db.get_all_products())
        cache_set(cache_key, products, 'search_results')
        return create_success_response(200, products)
    except CircuitBreakerOpenError:
        return create_error_response(503, 'Service temporarily unavailable. Please try again later.')
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        traceback.print_exc()
        return create_error_response(500, 'Internal server error')
