"""
Unit tests for auth_register, auth_login, user_profile, admin_orders.
Mocks Cognito and DynamoDB — no real AWS calls.
"""
import sys, os, json, unittest
from unittest.mock import patch, MagicMock
from botocore.exceptions import ClientError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../layers/product_utils/python'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../lambda_code'))

os.environ.setdefault('COGNITO_CLIENT_ID',   'test_client_id')
os.environ.setdefault('COGNITO_USER_POOL_ID','us-east-1_TestPool')
os.environ.setdefault('USER_PROFILES_TABLE', 'UserProfiles')
os.environ.setdefault('ORDERS_TABLE',        'Orders')


def _cognito_error(code):
    return ClientError({'Error': {'Code': code, 'Message': code}}, 'Op')


# ── Registration tests ────────────────────────────────────────────────────────
class TestAuthRegister(unittest.TestCase):

    @patch('boto3.client')
    def test_successful_registration(self, mock_boto):
        mock_cognito = MagicMock()
        mock_cognito.sign_up.return_value = {'UserSub': 'user-uuid-123'}
        mock_boto.return_value = mock_cognito

        from auth_register import handler
        resp = handler({'body': json.dumps({
            'email': 'test@example.com', 'password': 'Pass123!', 'name': 'Test User'})}, None)

        self.assertEqual(resp['statusCode'], 201)
        body = json.loads(resp['body'])
        self.assertIn('userId', body)
        mock_cognito.sign_up.assert_called_once()

    @patch('boto3.client')
    def test_duplicate_email_returns_409(self, mock_boto):
        mock_cognito = MagicMock()
        mock_cognito.exceptions.UsernameExistsException = type(
            'UsernameExistsException', (ClientError,), {})
        mock_cognito.sign_up.side_effect = mock_cognito.exceptions.UsernameExistsException(
            {'Error': {'Code': 'UsernameExistsException', 'Message': ''}}, 'SignUp')
        mock_boto.return_value = mock_cognito

        from auth_register import handler
        resp = handler({'body': json.dumps({
            'email': 'existing@example.com', 'password': 'Pass123!', 'name': 'User'})}, None)
        self.assertEqual(resp['statusCode'], 409)

    @patch('boto3.client')
    def test_missing_fields_returns_400(self, mock_boto):
        from auth_register import handler
        resp = handler({'body': json.dumps({'email': 'test@example.com'})}, None)
        self.assertEqual(resp['statusCode'], 400)

    @patch('boto3.client')
    def test_email_normalized_to_lowercase(self, mock_boto):
        mock_cognito = MagicMock()
        mock_cognito.sign_up.return_value = {'UserSub': 'uuid'}
        mock_boto.return_value = mock_cognito

        from auth_register import handler
        handler({'body': json.dumps({
            'email': 'TEST@EXAMPLE.COM', 'password': 'Pass123!', 'name': 'User'})}, None)

        call_kwargs = mock_cognito.sign_up.call_args[1]
        self.assertEqual(call_kwargs['Username'], 'test@example.com')


# ── Login tests ───────────────────────────────────────────────────────────────
class TestAuthLogin(unittest.TestCase):

    @patch('boto3.client')
    def test_successful_login_returns_tokens(self, mock_boto):
        mock_cognito = MagicMock()
        mock_cognito.initiate_auth.return_value = {'AuthenticationResult': {
            'AccessToken':  'access_tok', 'IdToken': 'id_tok',
            'RefreshToken': 'refresh_tok', 'ExpiresIn': 3600}}
        mock_boto.return_value = mock_cognito

        from auth_login import handler
        resp = handler({'body': json.dumps({
            'email': 'user@example.com', 'password': 'Pass123!'})}, None)

        self.assertEqual(resp['statusCode'], 200)
        body = json.loads(resp['body'])
        self.assertIn('accessToken',  body)
        self.assertIn('idToken',      body)
        self.assertIn('refreshToken', body)

    @patch('boto3.client')
    def test_invalid_credentials_returns_401(self, mock_boto):
        mock_cognito = MagicMock()
        mock_cognito.exceptions.NotAuthorizedException = type(
            'NotAuthorizedException', (ClientError,), {})
        mock_cognito.initiate_auth.side_effect = \
            mock_cognito.exceptions.NotAuthorizedException(
                {'Error': {'Code': 'NotAuthorizedException', 'Message': ''}}, 'InitAuth')
        mock_boto.return_value = mock_cognito

        from auth_login import handler
        resp = handler({'body': json.dumps({
            'email': 'user@example.com', 'password': 'wrong'})}, None)
        self.assertEqual(resp['statusCode'], 401)

    @patch('boto3.client')
    def test_unconfirmed_user_returns_403(self, mock_boto):
        mock_cognito = MagicMock()
        mock_cognito.exceptions.UserNotConfirmedException = type(
            'UserNotConfirmedException', (ClientError,), {})
        mock_cognito.initiate_auth.side_effect = \
            mock_cognito.exceptions.UserNotConfirmedException(
                {'Error': {'Code': 'UserNotConfirmedException', 'Message': ''}}, 'InitAuth')
        mock_boto.return_value = mock_cognito

        from auth_login import handler
        resp = handler({'body': json.dumps({
            'email': 'unconfirmed@example.com', 'password': 'Pass123!'})}, None)
        self.assertEqual(resp['statusCode'], 403)

    @patch('boto3.client')
    def test_missing_credentials_returns_400(self, mock_boto):
        from auth_login import handler
        resp = handler({'body': json.dumps({'email': 'user@example.com'})}, None)
        self.assertEqual(resp['statusCode'], 400)


# ── Profile tests ─────────────────────────────────────────────────────────────
def _profile_event(user_id, method='GET', body=None, groups='', query=None):
    return {
        'httpMethod': method,
        'pathParameters': None,
        'queryStringParameters': query,
        'body': json.dumps(body) if body else None,
        'requestContext': {'authorizer': {'claims': {
            'sub': user_id, 'email': f'{user_id}@test.com',
            'name': 'Test User', 'cognito:groups': groups}}},
    }

class TestUserProfile(unittest.TestCase):

    @patch('boto3.resource')
    def test_get_profile_creates_if_not_exists(self, mock_resource):
        mock_table = MagicMock()
        mock_table.get_item.return_value = {}  # no existing item
        mock_resource.return_value.Table.return_value = mock_table

        from user_profile import handler
        resp = handler(_profile_event('user_abc'), None)
        self.assertEqual(resp['statusCode'], 200)
        mock_table.put_item.assert_called_once()

    @patch('boto3.resource')
    def test_get_existing_profile(self, mock_resource):
        mock_table = MagicMock()
        mock_table.get_item.return_value = {'Item': {
            'userId': 'user_abc', 'name': 'Alice', 'email': 'alice@test.com'}}
        mock_resource.return_value.Table.return_value = mock_table

        from user_profile import handler
        resp = handler(_profile_event('user_abc'), None)
        self.assertEqual(resp['statusCode'], 200)
        self.assertEqual(json.loads(resp['body'])['name'], 'Alice')

    @patch('boto3.resource')
    def test_update_profile_allowed_fields(self, mock_resource):
        mock_table = MagicMock()
        mock_resource.return_value.Table.return_value = mock_table

        from user_profile import handler
        resp = handler(_profile_event('user_abc', method='PUT',
            body={'name': 'New Name', 'phone': '555-1234'}), None)
        self.assertEqual(resp['statusCode'], 200)
        mock_table.update_item.assert_called_once()

    @patch('boto3.resource')
    def test_update_profile_rejects_userId_override(self, mock_resource):
        mock_table = MagicMock()
        mock_resource.return_value.Table.return_value = mock_table

        from user_profile import handler
        # Attempt to change userId via body — should be ignored
        resp = handler(_profile_event('user_abc', method='PUT',
            body={'userId': 'attacker_id', 'name': 'Hacker'}), None)
        # userId is not in allowed fields — only name is updated
        self.assertEqual(resp['statusCode'], 200)
        call = mock_table.update_item.call_args[1]
        self.assertNotIn(':userId', call.get('ExpressionAttributeValues', {}))

    def test_missing_auth_context_returns_401(self):
        from user_profile import handler
        resp = handler({'httpMethod': 'GET', 'requestContext': {}, 'body': None,
                        'queryStringParameters': None}, None)
        self.assertEqual(resp['statusCode'], 401)


# ── Admin orders tests ────────────────────────────────────────────────────────
class TestAdminOrders(unittest.TestCase):

    def _event(self, groups=''):
        return {
            'httpMethod': 'GET',
            'queryStringParameters': None,
            'requestContext': {'authorizer': {'claims': {
                'sub': 'admin_user', 'cognito:groups': groups}}},
        }

    @patch('boto3.resource')
    def test_admin_can_list_all_orders(self, mock_resource):
        mock_table = MagicMock()
        mock_table.scan.return_value = {'Items': [{'order_id': 'o1'}], 'Count': 1}
        mock_resource.return_value.Table.return_value = mock_table

        from admin_orders import handler
        resp = handler(self._event(groups='Admins'), None)
        self.assertEqual(resp['statusCode'], 200)
        mock_table.scan.assert_called_once()

    def test_non_admin_receives_403(self):
        from admin_orders import handler
        resp = handler(self._event(groups=''), None)
        self.assertEqual(resp['statusCode'], 403)

    def test_customer_group_receives_403(self):
        from admin_orders import handler
        resp = handler(self._event(groups='Customers'), None)
        self.assertEqual(resp['statusCode'], 403)


if __name__ == '__main__':
    unittest.main()
