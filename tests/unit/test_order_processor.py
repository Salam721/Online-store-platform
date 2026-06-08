import sys, os, json, unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../layers/product_utils/python'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../lambda_code'))

SAMPLE_ORDER = {
    'order_id':     'order_abc123',
    'customer_id':  'cust_001',
    'items':        [{'product_id': 'prod_001', 'quantity': 1}],
    'total_amount': 99.99,
    'customer_tier':'regular',
    'order_type':   'standard',
}

SQS_EVENT = {'Records': [{'body': json.dumps(SAMPLE_ORDER)}]}

class TestOrderProcessor(unittest.TestCase):
    @patch('boto3.resource')
    @patch('boto3.client')
    def test_successful_workflow(self, mock_client, mock_resource):
        mock_table = MagicMock()
        mock_resource.return_value.Table.return_value = mock_table
        mock_client.return_value.publish.return_value = {'MessageId': 'msg_1'}

        with patch.dict(os.environ, {'ORDERS_TABLE': 'Orders',
                                     'CUSTOMER_NOTIFICATION_TOPIC': 'arn:aws:sns:us-east-1:123:customer-notifications',
                                     'SYSTEM_ALERT_TOPIC': 'arn:aws:sns:us-east-1:123:system-alerts'}):
            from order_processor import handler
            r = handler(SQS_EVENT, None)
            self.assertEqual(r['statusCode'], 200)

    @patch('boto3.resource')
    @patch('boto3.client')
    def test_rollback_on_failure(self, mock_client, mock_resource):
        mock_resource.return_value.Table.return_value = MagicMock()
        mock_client.return_value.publish.return_value = {'MessageId': 'msg_1'}

        with patch.dict(os.environ, {'ORDERS_TABLE': 'Orders',
                                     'CUSTOMER_NOTIFICATION_TOPIC': 'arn:aws:sns:us-east-1:123:ct',
                                     'SYSTEM_ALERT_TOPIC': 'arn:aws:sns:us-east-1:123:st'}):
            from order_processor import execute_order_workflow, _validate_inventory
            with patch('order_processor._validate_inventory', return_value={'success': False, 'error': 'Out of stock'}):
                result = execute_order_workflow(SAMPLE_ORDER)
                self.assertFalse(result['success'])
                self.assertIn('validate_inventory', result['failed_step'])

if __name__ == '__main__':
    unittest.main()
