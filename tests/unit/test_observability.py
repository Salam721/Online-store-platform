"""
Unit tests for observability.py — structured logging, EMF metrics, health checks.
"""
import sys, os, json, unittest
from unittest.mock import patch, MagicMock
from io import StringIO

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../layers/product_utils/python'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../lambda_code'))

os.environ.setdefault('APP_ENV', 'test')
os.environ.setdefault('PRODUCTS_TABLE', 'Products')


class TestStructuredLogging(unittest.TestCase):

    @patch('lambda_code.observability.logger')
    def test_log_event_emits_json(self, mock_logger):
        from observability import log_event
        log_event('order_started', {'order_id': 'ord_1', 'total': 99.99})
        mock_logger.info.assert_called_once()
        arg = mock_logger.info.call_args[0][0]
        parsed = json.loads(arg)
        self.assertEqual(parsed['event_type'], 'order_started')
        self.assertEqual(parsed['details']['order_id'], 'ord_1')
        self.assertIn('timestamp', parsed)
        self.assertIn('environment', parsed)

    @patch('lambda_code.observability.logger')
    def test_log_event_includes_env(self, mock_logger):
        from observability import log_event
        log_event('test_event', {})
        arg = json.loads(mock_logger.info.call_args[0][0])
        self.assertEqual(arg['environment'], 'test')


class TestEmfMetrics(unittest.TestCase):

    def test_record_metric_prints_emf(self):
        from observability import record_metric
        with patch('builtins.print') as mock_print:
            record_metric('CartAbandonment', 1, 'Count')
            mock_print.assert_called_once()
            payload = json.loads(mock_print.call_args[0][0])
            self.assertIn('_aws', payload)
            self.assertEqual(payload['CartAbandonment'], 1)
            self.assertEqual(
                payload['_aws']['CloudWatchMetrics'][0]['Namespace'],
                'OnlineStore/Business')

    def test_track_cart_abandonment_emits_two_metrics(self):
        from observability import track_cart_abandonment
        with patch('builtins.print') as mock_print, \
             patch('lambda_code.observability.logger'):
            track_cart_abandonment('user_1', 75.50, 'payment_failed')
            mock_print.assert_called_once()
            payload = json.loads(mock_print.call_args[0][0])
            metric_names = [m['Name'] for m in
                            payload['_aws']['CloudWatchMetrics'][0]['Metrics']]
            self.assertIn('CartAbandonment',   metric_names)
            self.assertIn('AbandonedCartValue', metric_names)

    def test_value_range_bucketing(self):
        from observability import track_cart_abandonment
        ranges = []
        with patch('builtins.print') as mock_print, \
             patch('lambda_code.observability.logger'):
            for val in [10, 75, 150, 300]:
                track_cart_abandonment('u', val, 'test')
                payload = json.loads(mock_print.call_args[0][0])
                ranges.append(payload.get('cart_value_range'))
        self.assertEqual(ranges, ['Under50', '50to100', '100to200', 'Over200'])

    def test_track_order_completed_emits_metrics(self):
        from observability import track_order_completed
        with patch('builtins.print') as mock_print, \
             patch('lambda_code.observability.logger'):
            track_order_completed('ord_1', 'user_1', 199.99, 3)
            payload = json.loads(mock_print.call_args[0][0])
            metric_names = [m['Name'] for m in
                            payload['_aws']['CloudWatchMetrics'][0]['Metrics']]
            self.assertIn('OrderCompleted', metric_names)
            self.assertIn('OrderValue',     metric_names)
            self.assertIn('OrderItemCount', metric_names)


class TestXRaySubsegment(unittest.TestCase):

    def test_subsegment_noop_without_sdk(self):
        """xray_subsegment silently skips when SDK not installed."""
        from observability import xray_subsegment
        with xray_subsegment('test_op') as seg:
            pass  # Should not raise
        # seg is None when SDK missing — acceptable

    def test_xray_annotate_noop_without_sdk(self):
        from observability import xray_annotate
        xray_annotate('customer_type', 'premium')  # Should not raise

    def test_xray_metadata_noop_without_sdk(self):
        from observability import xray_metadata
        xray_metadata('cart_items', [1, 2, 3])  # Should not raise


class TestHealthChecks(unittest.TestCase):

    @patch('boto3.client')
    def test_check_dynamodb_healthy(self, mock_boto):
        mock_boto.return_value.describe_table.return_value = {'Table': {}}
        from observability import check_dynamodb
        result = check_dynamodb('Products')
        self.assertEqual(result['status'], 'healthy')

    @patch('boto3.client')
    def test_check_dynamodb_unhealthy(self, mock_boto):
        from botocore.exceptions import ClientError
        mock_boto.return_value.describe_table.side_effect = ClientError(
            {'Error': {'Code': 'ResourceNotFoundException', 'Message': ''}},
            'DescribeTable')
        from observability import check_dynamodb
        result = check_dynamodb('NonExistentTable')
        self.assertEqual(result['status'], 'unhealthy')
        self.assertIn('error', result)


class TestHealthCheckHandler(unittest.TestCase):

    @patch('boto3.client')
    def test_healthy_when_all_pass(self, mock_boto):
        mock_boto.return_value.describe_table.return_value = {'Table': {}}
        os.environ['CACHE_ENDPOINT'] = ''  # Skip cache check

        from health_check import handler
        resp = handler({}, None)
        self.assertEqual(resp['statusCode'], 200)
        body = json.loads(resp['body'])
        self.assertEqual(body['status'], 'healthy')
        self.assertIn('dynamodb', body['checks'])

    @patch('boto3.client')
    def test_degraded_when_dynamodb_fails(self, mock_boto):
        from botocore.exceptions import ClientError
        mock_boto.return_value.describe_table.side_effect = ClientError(
            {'Error': {'Code': 'ResourceNotFoundException', 'Message': ''}},
            'DescribeTable')
        os.environ['CACHE_ENDPOINT'] = ''

        from health_check import handler
        resp = handler({}, None)
        self.assertEqual(resp['statusCode'], 503)
        body = json.loads(resp['body'])
        self.assertEqual(body['status'], 'degraded')

    def test_returns_json_with_timestamp(self):
        with patch('boto3.client') as mock_boto:
            mock_boto.return_value.describe_table.return_value = {}
            os.environ['CACHE_ENDPOINT'] = ''
            from health_check import handler
            resp = handler({}, None)
            body = json.loads(resp['body'])
            self.assertIn('timestamp', body)
            self.assertIn('environment', body)
            self.assertIn('service', body)


if __name__ == '__main__':
    unittest.main()
