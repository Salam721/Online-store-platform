import sys, os, json, unittest
from unittest.mock import patch
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../layers/product_utils/python'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../lambda_code'))
from event_factory import APIGatewayEventFactory

SAMPLE = {'id':'prod_123','title':'Headphones','category':'Electronics',
          'description':'Great','price':Decimal('199.99')}

class TestGetProduct(unittest.TestCase):
    @patch('cache_client.cache_get', return_value=None)
    @patch('cache_client.cache_set')
    @patch('products_db.get_product')
    def test_success(self, mock_db, *_):
        mock_db.return_value = SAMPLE
        from get_product import handler
        r = handler(APIGatewayEventFactory.get_product('prod_123'), None)
        self.assertEqual(r['statusCode'], 200)

    @patch('cache_client.cache_get', return_value=None)
    @patch('products_db.get_product', return_value=None)
    def test_not_found(self, *_):
        from get_product import handler
        r = handler(APIGatewayEventFactory.get_product('bad'), None)
        self.assertEqual(r['statusCode'], 404)

    def test_missing_id(self):
        from get_product import handler
        r = handler({'pathParameters': None}, None)
        self.assertEqual(r['statusCode'], 400)

    @patch('cache_client.cache_get')
    def test_cache_hit(self, mock_cache):
        mock_cache.return_value = SAMPLE
        from get_product import handler
        r = handler(APIGatewayEventFactory.get_product('prod_123'), None)
        self.assertEqual(r['statusCode'], 200)

    @patch('cache_client.cache_get', return_value=None)
    @patch('products_db.get_product')
    def test_circuit_open_returns_503(self, mock_db, *_):
        from circuit_breaker import CircuitBreakerOpenError
        mock_db.side_effect = CircuitBreakerOpenError("Open")
        from get_product import handler
        r = handler(APIGatewayEventFactory.get_product('prod_123'), None)
        self.assertEqual(r['statusCode'], 503)

if __name__ == '__main__':
    unittest.main()
