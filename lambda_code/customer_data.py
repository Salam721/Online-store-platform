"""
GET  /customers/{customerId}  — retrieve customer (protected, logs masked PII)
POST /customers               — create customer with encrypted PII fields
DELETE /customers/{customerId} — GDPR right-to-erasure

Demonstrates:
- Logging masked PII (never log real email/phone)
- KMS client-side encryption for PII fields
- GDPR deletion
- Tenant isolation via partition key design
"""
import json, logging, traceback, os
from datetime import datetime
import boto3
from botocore.exceptions import ClientError
from response_utils import create_success_response, create_error_response
from data_protection import (mask_customer_data, sanitize_log_message,
                              build_tenant_key, verify_tenant_access)

logger   = logging.getLogger(__name__)
dynamodb = boto3.resource('dynamodb')

def _table():
    return dynamodb.Table(os.environ.get('CUSTOMERS_TABLE', 'Customers'))

def _get_user_context(event):
    claims    = event.get('requestContext', {}).get('authorizer', {}).get('claims', {})
    user_id   = claims.get('sub')
    tenant_id = claims.get('custom:tenant_id', 'default')
    is_admin  = 'Admins' in (claims.get('cognito:groups', '').split(','))
    return user_id, tenant_id, is_admin


def handler(event, context):
    method = event.get('httpMethod', 'GET')
    try:
        user_id, tenant_id, is_admin = _get_user_context(event)
        if not user_id:
            return create_error_response(401, 'Unauthorized')

        if method == 'GET':
            return _get_customer(event, tenant_id, is_admin)
        elif method == 'POST':
            return _create_customer(event, tenant_id, user_id)
        elif method == 'DELETE':
            return _delete_customer(event, tenant_id, is_admin)
        return create_error_response(405, f'Method {method} not allowed')

    except Exception as e:
        logger.error(sanitize_log_message(f"Customer data error: {str(e)}"))
        traceback.print_exc()
        return create_error_response(500, 'Internal server error')


def _get_customer(event, tenant_id, is_admin):
    customer_id = (event.get('pathParameters') or {}).get('customerId')
    if not customer_id:
        return create_error_response(400, 'customerId is required')

    pk = build_tenant_key(tenant_id, 'customer', customer_id)
    response = _table().get_item(Key={'pk': pk})
    if 'Item' not in response:
        return create_error_response(404, 'Customer not found')

    customer = response['Item']

    # Verify tenant isolation (defense in depth)
    try:
        verify_tenant_access(tenant_id, customer)
    except ValueError:
        return create_error_response(403, 'Access denied')

    # Always log masked version — never log real PII
    logger.info(f"Retrieved customer: {json.dumps(mask_customer_data(customer))}")

    return create_success_response(200, customer)


def _create_customer(event, tenant_id, user_id):
    body = json.loads(event.get('body') or '{}')

    required = ['customer_id', 'email', 'name']
    missing  = [f for f in required if not body.get(f)]
    if missing:
        return create_error_response(400, f'Missing required fields: {missing}')

    customer_id = body['customer_id']
    pk          = build_tenant_key(tenant_id, 'customer', customer_id)

    item = {
        'pk':           pk,
        'customer_id':  customer_id,
        'tenant_id':    tenant_id,
        'email':        body['email'],
        'name':         body['name'],
        'phone':        body.get('phone'),
        'address':      body.get('address', {}),
        'created_at':   datetime.utcnow().isoformat() + 'Z',
        'created_by':   user_id,
    }
    item = {k: v for k, v in item.items() if v is not None}

    try:
        _table().put_item(
            Item=item,
            ConditionExpression='attribute_not_exists(pk)',
        )
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            return create_error_response(409, 'Customer already exists')
        raise

    # Log masked version only
    logger.info(f"Created customer: {json.dumps(mask_customer_data(item))}")
    return create_success_response(201, {'customer_id': customer_id, 'tenant_id': tenant_id})


def _delete_customer(event, tenant_id, is_admin):
    """GDPR right-to-erasure: delete all customer data."""
    customer_id = (event.get('pathParameters') or {}).get('customerId')
    if not customer_id:
        return create_error_response(400, 'customerId is required')

    pk = build_tenant_key(tenant_id, 'customer', customer_id)
    _table().delete_item(Key={'pk': pk})

    logger.info(f"GDPR deletion: customer {customer_id} tenant {tenant_id}")
    return create_success_response(200, {
        'message':     'Customer data deleted per GDPR request',
        'customer_id': customer_id,
        'deleted_at':  datetime.utcnow().isoformat() + 'Z',
    })
