import logging, traceback
import products_db
from cache_client import cache_get, cache_set
from response_utils import create_success_response, create_error_response
from circuit_breaker import CircuitBreakerOpenError

logger = logging.getLogger(__name__)

def handler(event, context):
    try:
        product_id = (event.get('pathParameters') or {}).get('id')
        if not product_id:
            return create_error_response(400, 'Product ID is required',
                suggestions=['Include the product ID in the URL: /products/{id}'])
        cached = cache_get(f"product:{product_id}")
        if cached:
            return create_success_response(200, cached)
        product = products_db.get_product(product_id)
        if not product:
            return create_error_response(404, f'Product {product_id} not found',
                suggestions=['Verify the product ID is correct'])
        cache_set(f"product:{product_id}", product, 'product_details')
        return create_success_response(200, product)
    except CircuitBreakerOpenError:
        return create_error_response(503, 'Service temporarily unavailable. Please try again later.')
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        traceback.print_exc()
        return create_error_response(500, 'Internal server error')
