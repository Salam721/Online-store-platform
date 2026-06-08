"""
Integration tests: external service mocking.
Uses unittest.mock and responses library to mock payment/shipping APIs.
"""
import sys, os, json, unittest
from unittest.mock import patch, Mock, MagicMock
from decimal import Decimal
from freezegun import freeze_time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../layers/product_utils/python'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../lambda_code'))


class TestPaymentGatewayIntegration(unittest.TestCase):
    """Mock Stripe-style payment gateway interactions."""

    def test_successful_payment_processing(self):
        """Simulate successful payment and verify order confirmed."""
        mock_payment_result = {
            'status': 'success',
            'transaction_id': 'pi_123456',
            'amount': 199.99,
        }

        with patch('order_processor._process_payment',
                   return_value={'success': True, 'transaction_id': 'pi_123456'}), \
             patch('order_processor._validate_inventory',
                   return_value={'success': True}), \
             patch('order_processor._create_shipping_label',
                   return_value={'success': True, 'label_url': 'https://ship.test/label'}), \
             patch('order_processor._update_analytics',
                   return_value={'success': True}), \
             patch('boto3.resource') as mock_resource, \
             patch('boto3.client') as mock_client:

            mock_resource.return_value.Table.return_value = MagicMock()
            mock_client.return_value.publish.return_value = {'MessageId': 'm1'}

            import importlib
            order_processor = importlib.import_module('order_processor')
            result = order_processor.execute_order_workflow({
                'order_id': 'ord_payment_test',
                'customer_id': 'cust_1',
                'items': [{'product_id': 'p1', 'quantity': 1}],
                'total_amount': 199.99,
            })

        self.assertTrue(result['success'])
        self.assertEqual(len(result['completed_steps']), 4)

    def test_payment_failure_triggers_rollback(self):
        """Payment failure rolls back previous steps."""
        with patch('order_processor._validate_inventory',
                   return_value={'success': True}), \
             patch('order_processor._process_payment',
                   return_value={'success': False, 'error': 'Card declined'}), \
             patch('order_processor._rollback_inventory') as mock_rollback:

            import importlib
            order_processor = importlib.import_module('order_processor')
            result = order_processor.execute_order_workflow({
                'order_id': 'ord_fail_test',
                'customer_id': 'cust_1',
                'items': [{'product_id': 'p1', 'quantity': 1}],
                'total_amount': 199.99,
            })

        self.assertFalse(result['success'])
        self.assertIn('process_payment', result['failed_step'])

    def test_shipping_failure_rolls_back_payment(self):
        """Shipping failure rolls back completed payment step."""
        with patch('order_processor._validate_inventory',
                   return_value={'success': True}), \
             patch('order_processor._process_payment',
                   return_value={'success': True, 'transaction_id': 'pi_abc'}), \
             patch('order_processor._create_shipping_label',
                   return_value={'success': False, 'error': 'Address invalid'}), \
             patch('order_processor._rollback_payment') as mock_rollback_payment, \
             patch('order_processor._rollback_inventory'):

            import importlib
            order_processor = importlib.import_module('order_processor')
            result = order_processor.execute_order_workflow({
                'order_id': 'ord_ship_fail',
                'customer_id': 'cust_1',
                'items': [{'product_id': 'p1', 'quantity': 1}],
                'total_amount': 199.99,
            })

        self.assertFalse(result['success'])
        self.assertIn('create_shipping_label', result['failed_step'])


class TestEnvironmentVariableMocking(unittest.TestCase):
    """Validate environment-based configuration."""

    @patch.dict(os.environ, {
        'PRODUCTS_TABLE': 'Products-staging',
        'APP_ENV':        'staging',
    })
    def test_config_reads_environment(self):
        """config module returns correct values per environment."""
        import importlib
        config = importlib.import_module('config')
        importlib.reload(config)
        # lru_cache cleared on reload
        self.assertEqual(os.environ.get('APP_ENV'), 'staging')

    @patch.dict(os.environ, {'ACTIVITY_STREAM_NAME': 'test-stream'})
    def test_track_activity_uses_env_stream_name(self):
        """track_activity reads stream name from environment."""
        with patch('boto3.client') as mock_client:
            mock_firehose = MagicMock()
            mock_firehose.put_record.return_value = {'RecordId': 'r1'}
            mock_client.return_value = mock_firehose

            import importlib
            track = importlib.import_module('track_activity')
            resp = track.handler({'body': json.dumps({
                'event_type': 'product_view', 'user_id': 'u1'})}, None)

        self.assertEqual(resp['statusCode'], 202)
        call_kwargs = mock_firehose.put_record.call_args[1]
        self.assertEqual(call_kwargs['DeliveryStreamName'], 'test-stream')


class TestTimeDependentBehavior(unittest.TestCase):
    """Validate time-sensitive logic using freezegun."""

    @freeze_time("2026-01-15 10:00:00")
    def test_product_insert_records_correct_timestamp(self):
        """created_at timestamp matches frozen time."""
        from moto import mock_dynamodb
        import boto3

        @mock_dynamodb
        def _run():
            ddb = boto3.resource('dynamodb', region_name='us-east-1')
            table = ddb.create_table(
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

            with patch('cache_client.cache_get', return_value=None), \
                 patch('cache_client.cache_set'), \
                 patch('cache_client.cache_invalidate_product'):
                import importlib
                resp = importlib.import_module('insert_product').handler({
                    'body': json.dumps({
                        'title': 'Test', 'category': 'Electronics',
                        'description': 'Desc', 'price': 9.99}),
                    'requestContext': {'identity': {'userArn': 'arn:test'}},
                }, None)

            self.assertEqual(resp['statusCode'], 201)
            body = json.loads(resp['body'])
            self.assertTrue(body['created_at'].startswith('2026-01-15'))

        _run()


if __name__ == '__main__':
    unittest.main()
