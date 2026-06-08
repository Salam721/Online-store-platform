"""
Unit tests for the recommendation engine container service.
Tests run without Docker — Flask test client used directly.
"""
import sys, os, json, unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../containers/recommendation_engine'))

SAMPLE_PRODUCTS = [
    {'id': 'prod_001', 'title': 'Wireless Headphones', 'category': 'Electronics', 'price': '199.99'},
    {'id': 'prod_002', 'title': 'USB-C Cable',         'category': 'Electronics', 'price': '12.99'},
    {'id': 'prod_003', 'title': 'Desk Lamp',           'category': 'Home',        'price': '34.99'},
]

class TestRecommendationEngine(unittest.TestCase):

    def setUp(self):
        # Patch DynamoDB before importing app
        self.dynamo_patcher = patch('boto3.resource')
        mock_boto = self.dynamo_patcher.start()
        mock_table = MagicMock()
        mock_table.scan.return_value = {'Items': SAMPLE_PRODUCTS}
        mock_boto.return_value.Table.return_value = mock_table

        os.environ.setdefault('PRODUCTS_TABLE', 'Products')
        os.environ.setdefault('AWS_REGION',     'us-east-1')

        import app as rec_app
        import importlib
        importlib.reload(rec_app)
        self.app    = rec_app.app
        self.client = self.app.test_client()

    def tearDown(self):
        self.dynamo_patcher.stop()

    def test_health_check(self):
        r = self.client.get('/health')
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        self.assertEqual(data['status'], 'healthy')
        self.assertEqual(data['service'], 'recommendation-engine')

    def test_get_recommendations_success(self):
        r = self.client.get('/recommendations?user_id=user_123')
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        self.assertIn('recommendations', data)
        self.assertEqual(data['user_id'], 'user_123')

    def test_get_recommendations_missing_user_id(self):
        r = self.client.get('/recommendations')
        self.assertEqual(r.status_code, 400)

    def test_get_recommendations_with_limit(self):
        r = self.client.get('/recommendations?user_id=user_123&limit=2')
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        self.assertLessEqual(len(data['recommendations']), 2)

    def test_get_recommendations_excludes_current_product(self):
        r = self.client.get('/recommendations?user_id=user_123&product_id=prod_001')
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        ids = [rec['product_id'] for rec in data['recommendations']]
        self.assertNotIn('prod_001', ids)

    def test_get_recommendations_by_category(self):
        r = self.client.get('/recommendations?user_id=user_123&category=Electronics')
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        for rec in data['recommendations']:
            self.assertEqual(rec['category'], 'Electronics')

    def test_batch_recommendations_success(self):
        r = self.client.post('/recommendations/batch',
            data=json.dumps({'user_ids': ['u1', 'u2'], 'limit': 3}),
            content_type='application/json')
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        self.assertIn('u1', data['results'])
        self.assertIn('u2', data['results'])
        self.assertEqual(data['user_count'], 2)

    def test_batch_recommendations_missing_user_ids(self):
        r = self.client.post('/recommendations/batch',
            data=json.dumps({'limit': 3}),
            content_type='application/json')
        self.assertEqual(r.status_code, 400)

    def test_cache_refresh(self):
        r = self.client.post('/cache/refresh')
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        self.assertEqual(data['status'], 'refreshed')

if __name__ == '__main__':
    unittest.main()
