"""
GET  /users/profile  — get current user's profile (protected)
PUT  /users/profile  — update current user's profile (protected)

User ID always extracted from validated JWT claims — never from request body.
Admin users (cognito:groups contains 'Admins') can view any profile.
"""
import json, logging, traceback, os
from decimal import Decimal
import boto3
from response_utils import create_success_response, create_error_response

logger   = logging.getLogger(__name__)
dynamodb = boto3.resource('dynamodb')

def _get_table():
    return dynamodb.Table(os.environ.get('USER_PROFILES_TABLE', 'UserProfiles'))

def _get_user_context(event):
    """Extract user ID and role from API Gateway Cognito authorizer claims."""
    claims  = event.get('requestContext', {}).get('authorizer', {}).get('claims', {})
    user_id = claims.get('sub')
    groups  = claims.get('cognito:groups', '')
    is_admin = 'Admins' in (groups.split(',') if groups else [])
    return user_id, is_admin, claims

def handler(event, context):
    method = event.get('httpMethod', 'GET')
    try:
        user_id, is_admin, claims = _get_user_context(event)
        if not user_id:
            return create_error_response(401, 'Unauthorized — missing user context')

        if method == 'GET':
            return _get_profile(user_id, is_admin, claims, event)
        elif method == 'PUT':
            return _update_profile(user_id, event)
        else:
            return create_error_response(405, f'Method {method} not allowed')

    except Exception as e:
        logger.error(f"Profile error: {str(e)}")
        traceback.print_exc()
        return create_error_response(500, 'Internal server error')


def _get_profile(user_id, is_admin, claims, event):
    table = _get_table()

    # Admins can query any user via ?userId=<id>
    target_id = user_id
    if is_admin:
        params = event.get('queryStringParameters') or {}
        target_id = params.get('userId', user_id)

    response = table.get_item(Key={'userId': target_id})
    if 'Item' not in response:
        # Auto-create profile on first access
        profile = {
            'userId': user_id,
            'email':  claims.get('email', ''),
            'name':   claims.get('name', ''),
        }
        table.put_item(Item=profile)
    else:
        profile = response['Item']

    return create_success_response(200, profile)


def _update_profile(user_id, event):
    body = json.loads(event.get('body') or '{}')
    # User ID from JWT only — never trust request body
    allowed = {'name', 'address', 'phone', 'preferences'}
    updates = {k: v for k, v in body.items() if k in allowed}
    if not updates:
        return create_error_response(400, f'No valid fields to update. Allowed: {allowed}')

    expr   = 'SET ' + ', '.join(f'#{k} = :{k}' for k in updates)
    names  = {f'#{k}': k for k in updates}
    values = {f':{k}': v for k, v in updates.items()}

    _get_table().update_item(
        Key={'userId': user_id},
        UpdateExpression=expr,
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )
    return create_success_response(200, {'message': 'Profile updated', 'userId': user_id})
