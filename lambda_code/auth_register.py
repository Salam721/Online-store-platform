"""
POST /auth/register
Registers a new customer with Cognito user pool.
No authentication required — anyone can register.
"""
import json, logging, traceback, os
import boto3
from response_utils import create_success_response, create_error_response

logger  = logging.getLogger(__name__)
cognito = boto3.client('cognito-idp')

def handler(event, context):
    try:
        body = json.loads(event.get('body') or '{}')
        email    = (body.get('email') or '').strip().lower()
        password = body.get('password', '')
        name     = (body.get('name') or '').strip()

        if not email or not password or not name:
            return create_error_response(400, 'email, password, and name are required')

        response = cognito.sign_up(
            ClientId=os.environ['COGNITO_CLIENT_ID'],
            Username=email,
            Password=password,
            UserAttributes=[
                {'Name': 'email', 'Value': email},
                {'Name': 'name',  'Value': name},
            ],
        )

        return create_success_response(201, {
            'message': 'Check your email to verify your account',
            'userId':  response['UserSub'],
        })

    except cognito.exceptions.UsernameExistsException:
        return create_error_response(409, 'Email already registered')
    except cognito.exceptions.InvalidPasswordException as e:
        return create_error_response(400, f'Password does not meet requirements: {str(e)}')
    except cognito.exceptions.InvalidParameterException as e:
        return create_error_response(400, f'Invalid parameter: {str(e)}')
    except json.JSONDecodeError as e:
        return create_error_response(400, f'Invalid JSON: {str(e)}')
    except Exception as e:
        logger.error(f"Registration error: {str(e)}")
        traceback.print_exc()
        return create_error_response(500, 'Internal server error')
