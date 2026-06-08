import json, uuid, logging, traceback, os
import boto3
from datetime import datetime
from response_utils import create_success_response, create_error_response

logger   = logging.getLogger(__name__)
sqs      = boto3.client('sqs')
eventbridge = boto3.client('events')

def handler(event, context):
    try:
        raw_data = json.loads(event.get('body') or '{}')

        required = ['customer_id', 'items', 'total_amount']
        missing  = [f for f in required if f not in raw_data]
        if missing:
            return create_error_response(400, f'Missing required fields: {missing}')

        order_id = str(uuid.uuid4())
        order_data = {
            'order_id':     order_id,
            'customer_id':  raw_data['customer_id'],
            'items':        raw_data['items'],
            'total_amount': raw_data['total_amount'],
            'customer_tier': raw_data.get('customer_tier', 'regular'),
            'order_type':   raw_data.get('order_type', 'standard'),
            'shipping_address': raw_data.get('shipping_address', {}),
            'payment_method':   raw_data.get('payment_method', 'credit_card'),
            'timestamp':    datetime.utcnow().isoformat() + 'Z',
            'processing_steps': [
                'validate_inventory', 'process_payment',
                'create_shipping_label', 'send_confirmation'
            ],
        }

        # Send to SQS for background processing
        queue_url = os.environ['ORDER_QUEUE_URL']
        sqs.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(order_data),
            MessageAttributes={
                'order_priority': {'StringValue': raw_data.get('priority', 'standard'), 'DataType': 'String'},
                'customer_tier':  {'StringValue': order_data['customer_tier'],           'DataType': 'String'},
            },
        )

        # Publish to EventBridge
        event_bus = os.environ.get('ORDER_EVENT_BUS', 'online-store-orders')
        eventbridge.put_events(Entries=[{
            'Source':      'store.orders',
            'DetailType':  'Order Placed',
            'Detail':      json.dumps(order_data),
            'EventBusName': event_bus,
        }])

        return create_success_response(202, {
            'order_id': order_id,
            'status':   'accepted',
            'message':  'Order received and queued for processing',
        })

    except json.JSONDecodeError as e:
        return create_error_response(400, f'Invalid JSON: {str(e)}')
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        traceback.print_exc()
        return create_error_response(500, 'Internal server error')
