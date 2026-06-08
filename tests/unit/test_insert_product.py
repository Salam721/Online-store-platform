import sys, os, json, unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../layers/product_utils/python'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../lambda_code'))
from event_factory import APIGatewayEventFactory

VALID = {'title':'Gaming Mouse','category':'Electronics',
         'description':'High precision gaming mouse','price':79.99}

class TestInsertProduct(unittest.TestCase):
    @patch('cache_client.cache_invalidate_product')
    @patch('products_db.insert_product')
    def test_success(self, mock_db, *_):
        mock_db.return_value = {**VALID, 'id':'gen-uuid'}
        from insert_product import handler
        r = handler(APIGatewayEventFactory.create_product(VALID), None)
        self.assertEqual(r['statusCode'], 201)

    def test_invalid_category(self):
        from insert_product import handler
        r = handler(APIGatewayEventFactory.create_product({**VALID,'category':'Fake'}), None)
        self.assertEqual(r['statusCode'], 400)

    def test_negative_price(self):
        from insert_product import handler
        r = handler(APIGatewayEventFactory.create_product({**VALID,'price':-5}), None)
        self.assertEqual(r['statusCode'], 400)

    def test_id_rejected(self):
        from insert_product import handler
        r = handler(APIGatewayEventFactory.create_product({**VALID,'id':'custom'}), None)
        self.assertEqual(r['statusCode'], 400)

    @patch('products_db.insert_product')
    def test_missing_fields(self, mock_db):
        from insert_product import handler
        r = handler(APIGatewayEventFactory.create_product({'title':'Only'}), None)
        self.assertEqual(r['statusCode'], 400)
        mock_db.assert_not_called()

if __name__ == '__main__':
    unittest.main()
