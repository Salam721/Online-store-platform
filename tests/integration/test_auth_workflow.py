"""
Integration tests: Cognito auth workflow.
Uses unittest.mock to simulate Cognito responses — no real user pool needed.
"""
import sys, os, json, unittest
from unittest.mock import patch, MagicMock
from moto import mock_dynamodb
import boto3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../layers/product_utils/python'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../lambda_code'))

os.environ.setdefault('COGNITO_CLIENT_ID',   'test_client_id')
os.environ.setdefault('COGNITO_USER_POOL_ID','us-east-1_TestPool')
os.environ.setdefault('USER_PROFILES_TABLE', 'UserProfiles')


def _make_cognito_mock(sign_up_result=None, auth_result=None):
    mock = MagicMock()
    if sign_up_result:
        mock.sign_up.return_value = sign_up_result
    if auth_result:
        mock.initiate_auth.return_value = {'AuthenticationResult': auth_result}
    mock.exceptions.UsernameExistsException    = type('UsernameExistsException',    (Exception,), {})
    mock.exceptions.NotAuthorizedException     = type('NotAuthorizedException',     (Exception,), {})
    mock.exceptions.UserNotConfirmedException  = type('UserNotConfirmedException',  (Exception,), {})
    mock.exceptions.UserNotFoundException      = type('UserNotFoundException',      (Exception,), {})
    mock.exceptions.InvalidPasswordException   = type('InvalidPasswordException',   (Exception,), {})
    mock.exceptions.InvalidParameterException  = type('InvalidParameterException',  (Exception,), {})
    return mock


class TestRegistrationLoginFlow(unittest.TestCase):

    @patch('boto3.client')
    def test_register_then_login_workflow(self, mock_boto):
        """Full register → login workflow returns all three tokens."""
        mock_cognito = _make_cognito_mock(
            sign_up_result={'UserSub': 'user-uuid-abc'},
            auth_result={
                'AccessToken':  'access_tok_xyz',
                'IdToken':      'id_tok_xyz',
                'RefreshToken': 'refresh_tok_xyz',
                'ExpiresIn':    3600,
            })
        mock_boto.return_value = mock_cognito

        import importlib
        register = importlib.import_module('auth_register')
        login    = importlib.import_module('auth_login')

        reg_resp = register.handler({'body': json.dumps({
            'email': 'newuser@example.com',
            'password': 'SecurePass123!',
            'name': 'New User',
        })}, None)
        self.assertEqual(reg_resp['statusCode'], 201)
        user_id = json.loads(reg_resp['body'])['userId']
        self.assertEqual(user_id, 'user-uuid-abc')

        login_resp = login.handler({'body': json.dumps({
            'email': 'newuser@example.com',
            'password': 'SecurePass123!',
        })}, None)
        self.assertEqual(login_resp['statusCode'], 200)
        tokens = json.loads(login_resp['body'])
        self.assertIn('accessToken',  tokens)
        self.assertIn('idToken',      tokens)
        self.assertIn('refreshToken', tokens)

    @patch('boto3.client')
    def test_duplicate_registration_rejected(self, mock_boto):
        """Second registration with same email returns 409."""
        mock_cognito = _make_cognito_mock()
        mock_cognito.sign_up.side_effect = \
            mock_cognito.exceptions.UsernameExistsException('already exists')
        mock_boto.return_value = mock_cognito

        import importlib
        register = importlib.import_module('auth_register')
        resp = register.handler({'body': json.dumps({
            'email': 'existing@example.com', 'password': 'Pass123!', 'name': 'User'})}, None)
        self.assertEqual(resp['statusCode'], 409)


class TestProtectedEndpointAccess(unittest.TestCase):

    @mock_dynamodb
    def test_authenticated_user_gets_profile(self):
        """Simulated JWT claims allow profile access."""
        ddb = boto3.resource('dynamodb', region_name='us-east-1')
        ddb.create_table(
            TableName='UserProfiles',
            KeySchema=[{'AttributeName': 'userId', 'KeyType': 'HASH'}],
            AttributeDefinitions=[{'AttributeName': 'userId', 'AttributeType': 'S'}],
            BillingMode='PAY_PER_REQUEST',
        )

        import importlib
        profile = importlib.import_module('user_profile')
        resp = profile.handler({
            'httpMethod': 'GET',
            'queryStringParameters': None,
            'body': None,
            'requestContext': {'authorizer': {'claims': {
                'sub':   'user_integration_test',
                'email': 'integration@test.com',
                'name':  'Integration User',
                'cognito:groups': '',
            }}},
        }, None)

        self.assertEqual(resp['statusCode'], 200)
        body = json.loads(resp['body'])
        self.assertEqual(body['userId'], 'user_integration_test')

    def test_unauthenticated_request_rejected(self):
        """Missing JWT claims → 401."""
        import importlib
        profile = importlib.import_module('user_profile')
        resp = profile.handler({
            'httpMethod': 'GET',
            'requestContext': {},
            'queryStringParameters': None,
            'body': None,
        }, None)
        self.assertEqual(resp['statusCode'], 401)

    @mock_dynamodb
    def test_admin_accesses_all_orders(self):
        """Admin group member can scan all orders."""
        ddb = boto3.resource('dynamodb', region_name='us-east-1')
        ddb.create_table(
            TableName='Orders',
            KeySchema=[{'AttributeName': 'order_id', 'KeyType': 'HASH'}],
            AttributeDefinitions=[{'AttributeName': 'order_id', 'AttributeType': 'S'}],
            BillingMode='PAY_PER_REQUEST',
        )

        import importlib
        admin = importlib.import_module('admin_orders')
        resp = admin.handler({
            'httpMethod': 'GET',
            'queryStringParameters': None,
            'requestContext': {'authorizer': {'claims': {
                'sub': 'admin_uuid', 'cognito:groups': 'Admins'}}},
        }, None)
        self.assertEqual(resp['statusCode'], 200)

    @mock_dynamodb
    def test_customer_blocked_from_admin_endpoint(self):
        """Customer group member receives 403 on admin endpoint."""
        import importlib
        admin = importlib.import_module('admin_orders')
        resp = admin.handler({
            'httpMethod': 'GET',
            'queryStringParameters': None,
            'requestContext': {'authorizer': {'claims': {
                'sub': 'customer_uuid', 'cognito:groups': 'Customers'}}},
        }, None)
        self.assertEqual(resp['statusCode'], 403)


if __name__ == '__main__':
    unittest.main()
