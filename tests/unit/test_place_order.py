import sys, os, json, unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../layers/product_utils/python'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../lambda_code'))

VALID_ORDER = {
    'customer_id':   'cust_123',
    'items':         [{'product_id': 'prod_001', 'quantity': 2}],
    'total_amount':  199.99,
    'customer_tier': 'regular',
    'order_type':    'standard',
}

class TestPlaceOrder(unittest.TestCase):
    @patch('boto3.client')
    def test_success(self, mock_boto):
        mock_sqs = MagicMock()
        mock_eb  = MagicMock()
        mock_sqs.send_message.return_value = {'MessageId': 'msg_123'}
        mock_eb.put_events.return_value = {'FailedEntryCount': 0, 'Entries': [{'EventId': 'ev_1'}]}
        mock_boto.side_effect = lambda svc, **kw: mock_sqs if svc == 'sqs' else mock_eb

        with patch.dict(os.environ, {'ORDER_QUEUE_URL': 'https://sqs.test/queue',
                                     'ORDER_EVENT_BUS': 'online-store-orders'}):
            from place_order import handler
            event = {'body': json.dumps(VALID_ORDER)}
            r = handler(event, None)
            self.assertEqual(r['statusCode'], 202)
            body = json.loads(r['body'])
            self.assertIn('order_id', body)
            self.assertEqual(body['status'], 'accepted')

    @patch('boto3.client')
    def test_missing_fields(self, mock_boto):
        with patch.dict(os.environ, {'ORDER_QUEUE_URL': 'https://sqs.test/queue',
                                     'ORDER_EVENT_BUS': 'online-store-orders'}):
            from place_order import handler
            r = handler({'body': json.dumps({'customer_id': 'c1'})}, None)
            self.assertEqual(r['statusCode'], 400)

    @patch('boto3.client')
    def test_invalid_json(self, mock_boto):
        with patch.dict(os.environ, {'ORDER_QUEUE_URL': 'https://sqs.test/queue',
                                     'ORDER_EVENT_BUS': 'online-store-orders'}):
            from place_order import handler
            r = handler({'body': 'not json {'}, None)
            self.assertEqual(r['statusCode'], 400)

if __name__ == '__main__':
    unittest.main()
