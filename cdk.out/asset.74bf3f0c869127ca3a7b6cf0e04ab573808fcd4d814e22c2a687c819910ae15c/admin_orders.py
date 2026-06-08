"""
GET /admin/orders — admin-only endpoint: list all orders
GET /admin/orders?customerId=<id> — filter by customer

Role enforcement: only users in the 'Admins' Cognito group can access this.
Regular customers receive 403 Forbidden.
"""
import json, logging, traceback, os
from decimal import Decimal
import boto3
from response_utils import create_success_response, create_error_response

logger   = logging.getLogger(__name__)
dynamodb = boto3.resource('dynamodb')

def _is_admin(event):
    claims = event.get('requestContext', {}).get('authorizer', {}).get('claims', {})
    groups = claims.get('cognito:groups', '')
    return 'Admins' in (groups.split(',') if groups else [])

def handler(event, context):
    try:
        if not _is_admin(event):
            return create_error_response(403,
                'Forbidden — admin access required',
                suggestions=['Contact your administrator if you need access'])

        table     = dynamodb.Table(os.environ.get('ORDERS_TABLE', 'Orders'))
        params    = event.get('queryStringParameters') or {}
        customer_id = params.get('customerId')

        if customer_id:
            response = table.query(
                IndexName='customer-index',
                KeyConditionExpression=boto3.dynamodb.conditions.Key('customer_id').eq(customer_id),
            )
        else:
            response = table.scan()

        return create_success_response(200, {
            'orders': response.get('Items', []),
            'count':  response.get('Count', 0),
        })

    except Exception as e:
        logger.error(f"Admin orders error: {str(e)}")
        traceback.print_exc()
        return create_error_response(500, 'Internal server error')
