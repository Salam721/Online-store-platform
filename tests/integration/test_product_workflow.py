"""
Integration tests: product CRUD operations across DynamoDB + S3.
Uses moto to mock AWS — no real AWS calls or costs.
"""
import sys, os, json, unittest
from decimal import Decimal
from moto import mock_dynamodb, mock_s3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../layers/product_utils/python'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../lambda_code'))

import boto3

# ── helpers ───────────────────────────────────────────────────────────────────
def _create_products_table(dynamodb):
    return dynamodb.create_table(
        TableName='Products',
        KeySchema=[{'AttributeName': 'id', 'KeyType': 'HASH'}],
        AttributeDefinitions=[
            {'AttributeName': 'id',       'AttributeType': 'S'},
            {'AttributeName': 'category', 'AttributeType': 'S'},
        ],
        GlobalSecondaryIndexes=[{
            'IndexName': 'category-index',
            'KeySchema': [{'AttributeName': 'category', 'KeyType': 'HASH'}],
            'Projection': {'ProjectionType': 'ALL'},
            'ProvisionedThroughput': {'ReadCapacityUnits': 1, 'WriteCapacityUnits': 1},
        }],
        BillingMode='PAY_PER_REQUEST',
    )


VALID_PRODUCT = {
    'title': 'Gaming Mouse', 'category': 'Electronics',
    'description': 'High precision gaming mouse', 'price': 79.99,
}


class TestProductCrudIntegration(unittest.TestCase):

    @mock_dynamodb
    def test_insert_and_get_product(self):
        """Insert a product then retrieve it — validates DynamoDB round-trip."""
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        _create_products_table(dynamodb)

        # Insert
        from insert_product import handler as insert_handler
        with unittest.mock.patch('cache_client.cache_get', return_value=None), \
             unittest.mock.patch('cache_client.cache_set'), \
             unittest.mock.patch('cache_client.cache_invalidate_product'):
            insert_event = {
                'body': json.dumps(VALID_PRODUCT),
                'requestContext': {'identity': {'userArn': 'arn:aws:iam::123:user/test'}},
            }
            insert_resp = insert_handler(insert_event, None)

        self.assertEqual(insert_resp['statusCode'], 201)
        product_id = json.loads(insert_resp['body'])['id']

        # Retrieve
        from get_product import handler as get_handler
        with unittest.mock.patch('cache_client.cache_get', return_value=None), \
             unittest.mock.patch('cache_client.cache_set'):
            get_resp = get_handler({'pathParameters': {'id': product_id}}, None)

        self.assertEqual(get_resp['statusCode'], 200)
        body = json.loads(get_resp['body'])
        self.assertEqual(body['title'], 'Gaming Mouse')
        self.assertEqual(body['category'], 'Electronics')

    @mock_dynamodb
    def test_insert_update_get_product(self):
        """Insert then update a product — validates update expression."""
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        _create_products_table(dynamodb)

        with unittest.mock.patch('cache_client.cache_get', return_value=None), \
             unittest.mock.patch('cache_client.cache_set'), \
             unittest.mock.patch('cache_client.cache_invalidate_product'):
            insert_resp = __import__('insert_product').handler(
                {'body': json.dumps(VALID_PRODUCT),
                 'requestContext': {'identity': {'userArn': 'arn:test'}}}, None)
            product_id = json.loads(insert_resp['body'])['id']

            update_body = {**VALID_PRODUCT, 'title': 'Ultra Gaming Mouse', 'price': 99.99}
            update_resp = __import__('update_product').handler(
                {'pathParameters': {'id': product_id},
                 'body': json.dumps(update_body),
                 'requestContext': {'identity': {'userArn': 'arn:test'}}}, None)

        self.assertEqual(update_resp['statusCode'], 200)
        self.assertEqual(json.loads(update_resp['body'])['title'], 'Ultra Gaming Mouse')

    @mock_dynamodb
    def test_query_products_by_category(self):
        """Seed products then query by category using GSI."""
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = _create_products_table(dynamodb)
        table.put_item(Item={'id': 'p1', 'title': 'Headphones', 'category': 'Electronics',
                              'description': 'Wireless', 'price': Decimal('199.99')})
        table.put_item(Item={'id': 'p2', 'title': 'Lamp', 'category': 'Home',
                              'description': 'LED', 'price': Decimal('34.99')})

        with unittest.mock.patch('cache_client.cache_get', return_value=None), \
             unittest.mock.patch('cache_client.cache_set'):
            resp = __import__('query_products').handler(
                {'queryStringParameters': {'category': 'Electronics'}}, None)

        self.assertEqual(resp['statusCode'], 200)
        items = json.loads(resp['body'])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['title'], 'Headphones')

    @mock_dynamodb
    def test_get_nonexistent_product_returns_404(self):
        """Verify 404 when product doesn't exist."""
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        _create_products_table(dynamodb)

        with unittest.mock.patch('cache_client.cache_get', return_value=None):
            resp = __import__('get_product').handler(
                {'pathParameters': {'id': 'does_not_exist'}}, None)

        self.assertEqual(resp['statusCode'], 404)

    @mock_dynamodb
    @mock_s3
    def test_upload_url_generated_for_existing_product(self):
        """Verify presigned URL returned for a valid product."""
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = _create_products_table(dynamodb)
        table.put_item(Item={'id': 'prod_img', 'title': 'Camera', 'category': 'Electronics',
                              'description': 'DSLR', 'price': Decimal('799.99')})

        s3 = boto3.client('s3', region_name='us-east-1')
        s3.create_bucket(Bucket='test-images-bucket')
        os.environ['PRODUCT_IMAGE_BUCKET'] = 'test-images-bucket'

        with unittest.mock.patch('config.get_image_bucket', return_value='test-images-bucket'):
            resp = __import__('get_upload_url').handler(
                {'pathParameters': {'id': 'prod_img'},
                 'queryStringParameters': {'type': 'main'}}, None)

        self.assertEqual(resp['statusCode'], 200)
        body = json.loads(resp['body'])
        self.assertIn('upload_url', body)
        self.assertIn('prod_img', body['object_key'])


import unittest.mock
if __name__ == '__main__':
    unittest.main()
