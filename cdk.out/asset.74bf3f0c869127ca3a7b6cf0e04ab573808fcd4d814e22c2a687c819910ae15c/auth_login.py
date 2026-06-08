"""
POST /auth/login
Authenticates a customer and returns JWTs.
Returns: accessToken, idToken, refreshToken
"""
import json, logging, traceback, os
import boto3
from response_utils import create_success_response, create_error_response

logger  = logging.getLogger(__name__)
cognito = boto3.client('cognito-idp')

def handler(event, context):
    try:
        body     = json.loads(event.get('body') or '{}')
        email    = (body.get('email') or '').strip().lower()
        password = body.get('password', '')

        if not email or not password:
            return create_error_response(400, 'email and password are required')

        response = cognito.initiate_auth(
            ClientId=os.environ['COGNITO_CLIENT_ID'],
            AuthFlow='USER_PASSWORD_AUTH',
            AuthParameters={
                'USERNAME': email,
                'PASSWORD': password,
            },
        )

        tokens = response['AuthenticationResult']
        return create_success_response(200, {
            'accessToken':  tokens['AccessToken'],
            'idToken':      tokens['IdToken'],
            'refreshToken': tokens['RefreshToken'],
            'expiresIn':    tokens['ExpiresIn'],
        })

    except cognito.exceptions.NotAuthorizedException:
        return create_error_response(401, 'Invalid email or password')
    except cognito.exceptions.UserNotConfirmedException:
        return create_error_response(403, 'Please verify your email before signing in')
    except cognito.exceptions.UserNotFoundException:
        # Return same message as NotAuthorized to prevent user enumeration
        return create_error_response(401, 'Invalid email or password')
    except json.JSONDecodeError as e:
        return create_error_response(400, f'Invalid JSON: {str(e)}')
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        traceback.print_exc()
        return create_error_response(500, 'Internal server error')
