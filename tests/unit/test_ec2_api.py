"""
Unit tests for the EC2-hosted inventory API.
Tests use Flask test client directly — no EC2 instance needed.
"""
import sys, os, json, unittest
from unittest.mock import patch, MagicMock
from botocore.exceptions import ClientError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../ec2/websocket_server'))

SAMPLE_PRODUCT = {
    'id': 'prod_001', 'title': 'Wireless Headphones',
    'category': 'Electronics', 'price': '199.99', 'inventory_count': 42,
    'updated_at': '2026-01-15T10:00:00Z',
}

SAMPLE_PRODUCTS = [SAMPLE_PRODUCT,
    {'id': 'prod_002', 'title': 'USB-C Cable', 'category': 'Electronics',
     'price': '12.99', 'inventory_count': 100}]


class TestEc2InventoryApi(unittest.TestCase):

    def setUp(self):
        self.dynamo_patcher = patch('boto3.resource')
        mock_boto = self.dynamo_patcher.start()
        self.mock_table = MagicMock()
        mock_boto.return_value.Table.return_value = self.mock_table

        os.environ.setdefault('PRODUCTS_TABLE', 'Products')
        os.environ.setdefault('AWS_REGION', 'us-east-1')

        import app as ec2_app
        import importlib; importlib.reload(ec2_app)
        self.client = ec2_app.app.test_client()

    def tearDown(self):
        self.dynamo_patcher.stop()

    # ── Health check ──────────────────────────────────────────────────────────
    def test_health_returns_200(self):
        r = self.client.get('/health')
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        self.assertEqual(data['status'], 'healthy')

    # ── Get products ──────────────────────────────────────────────────────────
    def test_get_products_success(self):
        self.mock_table.scan.return_value = {'Items': SAMPLE_PRODUCTS}
        r = self.client.get('/api/products')
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        self.assertEqual(len(data), 2)

    def test_get_products_dynamodb_error_returns_500(self):
        self.mock_table.scan.side_effect = ClientError(
            {'Error': {'Code': 'InternalServerError', 'Message': 'boom'}}, 'Scan')
        r = self.client.get('/api/products')
        self.assertEqual(r.status_code, 500)

    # ── Get inventory ─────────────────────────────────────────────────────────
    def test_get_inventory_success(self):
        self.mock_table.get_item.return_value = {'Item': SAMPLE_PRODUCT}
        r = self.client.get('/api/products/prod_001/inventory')
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        self.assertEqual(data['inventory_count'], 42)

    def test_get_inventory_not_found(self):
        self.mock_table.get_item.return_value = {}
        r = self.client.get('/api/products/bad_id/inventory')
        self.assertEqual(r.status_code, 404)

    # ── Update inventory ──────────────────────────────────────────────────────
    def test_update_inventory_success(self):
        self.mock_table.update_item.return_value = {
            'Attributes': {**SAMPLE_PRODUCT, 'inventory_count': 50}}
        r = self.client.put('/api/products/prod_001/inventory',
            data=json.dumps({'quantity': 50}),
            content_type='application/json')
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        self.assertEqual(data['inventory_count'], 50)

    def test_update_inventory_missing_quantity(self):
        r = self.client.put('/api/products/prod_001/inventory',
            data=json.dumps({}), content_type='application/json')
        self.assertEqual(r.status_code, 400)

    def test_update_inventory_product_not_found(self):
        self.mock_table.update_item.side_effect = ClientError(
            {'Error': {'Code': 'ConditionalCheckFailedException', 'Message': ''}},
            'UpdateItem')
        r = self.client.put('/api/products/bad_id/inventory',
            data=json.dumps({'quantity': 10}),
            content_type='application/json')
        self.assertEqual(r.status_code, 404)

    # ── Bulk update ───────────────────────────────────────────────────────────
    def test_bulk_update_success(self):
        self.mock_table.update_item.return_value = {}
        payload = {'updates': [
            {'product_id': 'prod_001', 'quantity': 50},
            {'product_id': 'prod_002', 'quantity': 100},
        ]}
        r = self.client.post('/api/inventory/bulk',
            data=json.dumps(payload), content_type='application/json')
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        self.assertEqual(data['success'], 2)
        self.assertEqual(data['failed'], 0)

    def test_bulk_update_missing_updates(self):
        r = self.client.post('/api/inventory/bulk',
            data=json.dumps({}), content_type='application/json')
        self.assertEqual(r.status_code, 400)

    def test_bulk_update_partial_failure(self):
        call_count = {'n': 0}
        def side_effect(**kwargs):
            call_count['n'] += 1
            if call_count['n'] == 2:
                raise ClientError(
                    {'Error': {'Code': 'ProvisionedThroughputExceededException',
                               'Message': 'throttled'}}, 'UpdateItem')
            return {}
        self.mock_table.update_item.side_effect = side_effect
        payload = {'updates': [
            {'product_id': 'prod_001', 'quantity': 10},
            {'product_id': 'prod_002', 'quantity': 20},
            {'product_id': 'prod_003', 'quantity': 30},
        ]}
        r = self.client.post('/api/inventory/bulk',
            data=json.dumps(payload), content_type='application/json')
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        self.assertEqual(data['success'], 2)
        self.assertEqual(data['failed'], 1)

if __name__ == '__main__':
    unittest.main()
