import json, uuid, logging, traceback
import products_db
from cache_client import cache_invalidate_product
from response_utils import create_success_response, create_error_response
from product_schema import ProductInput, VALID_CATEGORIES
from pydantic import ValidationError
from circuit_breaker import CircuitBreakerOpenError

logger = logging.getLogger(__name__)

def handler(event, context):
    try:
        raw_data = json.loads(event.get('body') or '{}')
        if 'id' in raw_data:
            return create_error_response(400, 'Product id is not allowed in request body')
        product_input  = ProductInput(**raw_data)
        validated_data = product_input.dict()
        validated_data['id'] = str(uuid.uuid4())
        user_arn = (event.get('requestContext') or {}).get('identity', {}).get('userArn', 'unknown')
        inserted = products_db.insert_product(validated_data, user_arn)
        cache_invalidate_product(validated_data['id'], validated_data['category'])
        return create_success_response(201, inserted)
    except json.JSONDecodeError as e:
        return create_error_response(400, f'Invalid JSON: {str(e)}')
    except ValidationError as e:
        msgs = [f"{err['loc'][0]}: {err['msg']}" for err in e.errors()]
        return create_error_response(400, 'Validation failed', details=msgs,
            suggestions=[f'category must be one of: {VALID_CATEGORIES}',
                         'price must be a positive number'])
    except ValueError as e:
        return create_error_response(409, str(e))
    except CircuitBreakerOpenError:
        return create_error_response(503, 'Service temporarily unavailable. Please try again later.')
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        traceback.print_exc()
        return create_error_response(500, 'Internal server error')
