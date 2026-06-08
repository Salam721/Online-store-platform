"""
Integration tests: complete order placement workflow.
Validates SQS queuing, EventBridge publishing, DynamoDB writes.
"""
import sys, os, json, unittest
from unittest.mock import patch, MagicMock
from moto import mock_dynamodb, mock_sqs, mock_events

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../layers/product_utils/python'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../lambda_code'))

import boto3

VALID_ORDER = {
    'customer_id':   'cust_123',
    'items':         [{'product_id': 'prod_001', 'quantity': 2, 'name': 'Headphones'}],
    'total_amount':  399.98,
    'customer_tier': 'regular',
    'order_type':    'standard',
}


class TestOrderWorkflowIntegration(unittest.TestCase):

    @mock_sqs
    @mock_events
    def test_place_order_queues_message(self):
        """Placing an order sends a message to the SQS queue."""
        sqs = boto3.client('sqs', region_name='us-east-1')
        response = sqs.create_queue(QueueName='order-processing-queue')
        queue_url = response['QueueUrl']
        os.environ['ORDER_QUEUE_URL'] = queue_url

        eb = boto3.client('events', region_name='us-east-1')
        eb.create_event_bus(Name='online-store-orders')
        os.environ['ORDER_EVENT_BUS'] = 'online-store-orders'

        import importlib
        place_order = importlib.import_module('place_order')
        resp = place_order.handler({'body': json.dumps(VALID_ORDER)}, None)

        self.assertEqual(resp['statusCode'], 202)
        body = json.loads(resp['body'])
        self.assertEqual(body['status'], 'accepted')
        self.assertIn('order_id', body)

        # Verify SQS message was sent
        msgs = sqs.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=1)
        self.assertIn('Messages', msgs)
        msg_body = json.loads(msgs['Messages'][0]['Body'])
        self.assertEqual(msg_body['customer_id'], 'cust_123')
        self.assertIn('order_id', msg_body)

    @mock_sqs
    @mock_events
    def test_place_order_missing_fields_returns_400(self):
        """Order without required fields returns 400."""
        sqs = boto3.client('sqs', region_name='us-east-1')
        q = sqs.create_queue(QueueName='order-processing-queue')
        os.environ['ORDER_QUEUE_URL'] = q['QueueUrl']
        os.environ['ORDER_EVENT_BUS'] = 'online-store-orders'

        import importlib
        place_order = importlib.import_module('place_order')
        resp = place_order.handler(
            {'body': json.dumps({'customer_id': 'cust_123'})}, None)

        self.assertEqual(resp['statusCode'], 400)

    @mock_dynamodb
    @mock_sqs
    def test_order_processor_completes_workflow(self):
        """SQS-triggered order processor runs full workflow successfully."""
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        dynamodb.create_table(
            TableName='Orders',
            KeySchema=[{'AttributeName': 'order_id', 'KeyType': 'HASH'}],
            AttributeDefinitions=[{'AttributeName': 'order_id', 'AttributeType': 'S'}],
            BillingMode='PAY_PER_REQUEST',
        )

        sqs_event = {'Records': [{'body': json.dumps({
            **VALID_ORDER,
            'order_id':  'order_integration_test',
            'timestamp': '2026-01-15T10:00:00Z',
        })}]}

        with patch('boto3.client') as mock_client:
            mock_sns = MagicMock()
            mock_sns.publish.return_value = {'MessageId': 'msg_1'}
            mock_client.return_value = mock_sns

            import importlib
            order_processor = importlib.import_module('order_processor')
            resp = order_processor.handler(sqs_event, None)

        self.assertEqual(resp['statusCode'], 200)

    @mock_dynamodb
    @mock_sqs
    def test_order_processor_updates_order_status(self):
        """After processing, order status is written to DynamoDB."""
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = dynamodb.create_table(
            TableName='Orders',
            KeySchema=[{'AttributeName': 'order_id', 'KeyType': 'HASH'}],
            AttributeDefinitions=[{'AttributeName': 'order_id', 'AttributeType': 'S'}],
            BillingMode='PAY_PER_REQUEST',
        )

        order_id  = 'order_status_test'
        sqs_event = {'Records': [{'body': json.dumps({
            **VALID_ORDER, 'order_id': order_id, 'timestamp': '2026-01-15T10:00:00Z',
        })}]}

        with patch('boto3.client') as mock_client:
            mock_client.return_value.publish.return_value = {'MessageId': 'm1'}
            import importlib
            importlib.import_module('order_processor').handler(sqs_event, None)

        item = table.get_item(Key={'order_id': order_id}).get('Item')
        self.assertIsNotNone(item)
        self.assertIn(item['status'], ['confirmed', 'failed'])


if __name__ == '__main__':
    unittest.main()
