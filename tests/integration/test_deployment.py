"""
Deployment tests: validate critical paths still work after a CDK stack update.
Run these after every cdk deploy against a staging environment.
"""
import sys, os, json, unittest
from unittest.mock import patch, MagicMock
from moto import mock_dynamodb, mock_s3, mock_sqs

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../layers/product_utils/python'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../lambda_code'))

import boto3


def _setup_products_table(dynamodb):
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


class TestDeploymentCriticalPaths(unittest.TestCase):
    """
    Smoke tests for critical business flows.
    Run after every CDK deployment to catch regressions before customers do.
    """

    @mock_dynamodb
    def test_can_create_product(self):
        """Product creation works after deployment."""
        _setup_products_table(boto3.resource('dynamodb', region_name='us-east-1'))

        with patch('cache_client.cache_get', return_value=None), \
             patch('cache_client.cache_set'), \
             patch('cache_client.cache_invalidate_product'):
            import importlib
            resp = importlib.import_module('insert_product').handler({
                'body': json.dumps({
                    'title': 'Deployment Test Product', 'category': 'Electronics',
                    'description': 'Smoke test', 'price': 1.00}),
                'requestContext': {'identity': {'userArn': 'arn:test'}},
            }, None)

        self.assertEqual(resp['statusCode'], 201,
            f"Product creation failed after deployment: {resp['body']}")

    @mock_dynamodb
    def test_can_retrieve_product(self):
        """Product retrieval works after deployment."""
        from decimal import Decimal
        ddb = boto3.resource('dynamodb', region_name='us-east-1')
        table = _setup_products_table(ddb)
        table.put_item(Item={'id': 'smoke_001', 'title': 'Smoke Product',
                              'category': 'Electronics', 'price': Decimal('9.99'),
                              'description': 'Smoke test'})

        with patch('cache_client.cache_get', return_value=None), \
             patch('cache_client.cache_set'):
            import importlib
            resp = importlib.import_module('get_product').handler(
                {'pathParameters': {'id': 'smoke_001'}}, None)

        self.assertEqual(resp['statusCode'], 200,
            f"Product retrieval failed after deployment: {resp['body']}")

    @mock_sqs
    def test_can_place_order(self):
        """Order placement works after deployment."""
        sqs = boto3.client('sqs', region_name='us-east-1')
        q   = sqs.create_queue(QueueName='order-processing-queue')
        os.environ['ORDER_QUEUE_URL']  = q['QueueUrl']
        os.environ['ORDER_EVENT_BUS']  = 'online-store-orders'

        with patch('boto3.client') as mock_client:
            mock_sqs_c = MagicMock()
            mock_eb_c  = MagicMock()
            mock_sqs_c.send_message.return_value = {'MessageId': 'm1'}
            mock_eb_c.put_events.return_value    = {
                'FailedEntryCount': 0, 'Entries': [{'EventId': 'e1'}]}
            mock_client.side_effect = lambda s, **kw: (
                mock_sqs_c if s == 'sqs' else mock_eb_c)

            import importlib
            resp = importlib.import_module('place_order').handler({
                'body': json.dumps({
                    'customer_id': 'smoke_user',
                    'items': [{'product_id': 'p1', 'quantity': 1}],
                    'total_amount': 9.99,
                })}, None)

        self.assertEqual(resp['statusCode'], 202,
            f"Order placement failed after deployment: {resp['body']}")

    @mock_dynamodb
    def test_validation_still_enforced(self):
        """Input validation works after deployment — invalid data rejected."""
        _setup_products_table(boto3.resource('dynamodb', region_name='us-east-1'))

        with patch('cache_client.cache_get', return_value=None), \
             patch('cache_client.cache_invalidate_product'):
            import importlib
            resp = importlib.import_module('insert_product').handler({
                'body': json.dumps({
                    'title': '', 'category': 'InvalidCategory',
                    'description': 'x', 'price': -1}),
                'requestContext': {'identity': {'userArn': 'arn:test'}},
            }, None)

        self.assertEqual(resp['statusCode'], 400,
            "Validation not enforced after deployment — security risk!")


if __name__ == '__main__':
    unittest.main()
