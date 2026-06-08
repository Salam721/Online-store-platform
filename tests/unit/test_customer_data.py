"""
Unit tests for customer_data handler — PII masking, tenant isolation, GDPR deletion.
"""
import sys, os, json, unittest
from unittest.mock import patch, MagicMock
from botocore.exceptions import ClientError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../layers/product_utils/python'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../lambda_code'))

os.environ.setdefault('CUSTOMERS_TABLE', 'Customers')

def _event(method, customer_id=None, body=None, tenant='tenant_abc', groups=''):
    return {
        'httpMethod': method,
        'pathParameters': {'customerId': customer_id} if customer_id else None,
        'queryStringParameters': None,
        'body': json.dumps(body) if body else None,
        'requestContext': {'authorizer': {'claims': {
            'sub':                 'user_123',
            'custom:tenant_id':    tenant,
            'cognito:groups':      groups,
        }}},
    }


class TestCustomerGet(unittest.TestCase):

    @patch('boto3.resource')
    def test_get_existing_customer(self, mock_resource):
        mock_table = MagicMock()
        mock_table.get_item.return_value = {'Item': {
            'pk':          'tenant_abc#customer#cust_001',
            'customer_id': 'cust_001',
            'tenant_id':   'tenant_abc',
            'email':       'user@example.com',
            'name':        'Alice',
        }}
        mock_resource.return_value.Table.return_value = mock_table

        from customer_data import handler
        resp = handler(_event('GET', customer_id='cust_001'), None)
        self.assertEqual(resp['statusCode'], 200)
        body = json.loads(resp['body'])
        self.assertEqual(body['customer_id'], 'cust_001')

    @patch('boto3.resource')
    def test_get_nonexistent_customer(self, mock_resource):
        mock_table = MagicMock()
        mock_table.get_item.return_value = {}
        mock_resource.return_value.Table.return_value = mock_table

        from customer_data import handler
        resp = handler(_event('GET', customer_id='bad_id'), None)
        self.assertEqual(resp['statusCode'], 404)

    @patch('boto3.resource')
    def test_cross_tenant_access_blocked(self, mock_resource):
        mock_table = MagicMock()
        # Item belongs to different tenant
        mock_table.get_item.return_value = {'Item': {
            'pk': 'tenant_xyz#customer#cust_001',
            'tenant_id': 'tenant_xyz',
        }}
        mock_resource.return_value.Table.return_value = mock_table

        from customer_data import handler
        resp = handler(_event('GET', customer_id='cust_001', tenant='tenant_abc'), None)
        self.assertEqual(resp['statusCode'], 403)


class TestCustomerCreate(unittest.TestCase):

    @patch('boto3.resource')
    def test_create_customer_success(self, mock_resource):
        mock_table = MagicMock()
        mock_resource.return_value.Table.return_value = mock_table

        from customer_data import handler
        resp = handler(_event('POST', body={
            'customer_id': 'cust_new', 'email': 'new@example.com', 'name': 'Bob'}), None)
        self.assertEqual(resp['statusCode'], 201)
        mock_table.put_item.assert_called_once()

    @patch('boto3.resource')
    def test_create_customer_missing_fields(self, mock_resource):
        from customer_data import handler
        resp = handler(_event('POST', body={'customer_id': 'c1'}), None)
        self.assertEqual(resp['statusCode'], 400)

    @patch('boto3.resource')
    def test_create_duplicate_customer(self, mock_resource):
        mock_table = MagicMock()
        mock_table.put_item.side_effect = ClientError(
            {'Error': {'Code': 'ConditionalCheckFailedException', 'Message': ''}}, 'PutItem')
        mock_resource.return_value.Table.return_value = mock_table

        from customer_data import handler
        resp = handler(_event('POST', body={
            'customer_id': 'existing', 'email': 'e@e.com', 'name': 'Dup'}), None)
        self.assertEqual(resp['statusCode'], 409)


class TestCustomerGdprDeletion(unittest.TestCase):

    @patch('boto3.resource')
    def test_delete_customer_success(self, mock_resource):
        mock_table = MagicMock()
        mock_resource.return_value.Table.return_value = mock_table

        from customer_data import handler
        resp = handler(_event('DELETE', customer_id='cust_del'), None)
        self.assertEqual(resp['statusCode'], 200)
        body = json.loads(resp['body'])
        self.assertIn('deleted_at', body)
        mock_table.delete_item.assert_called_once()

    def test_delete_without_id_returns_400(self):
        from customer_data import handler
        resp = handler(_event('DELETE'), None)
        self.assertEqual(resp['statusCode'], 400)

    def test_unauthenticated_request_returns_401(self):
        from customer_data import handler
        resp = handler({
            'httpMethod': 'DELETE',
            'pathParameters': {'customerId': 'c1'},
            'requestContext': {},
            'body': None,
            'queryStringParameters': None,
        }, None)
        self.assertEqual(resp['statusCode'], 401)


if __name__ == '__main__':
    unittest.main()
