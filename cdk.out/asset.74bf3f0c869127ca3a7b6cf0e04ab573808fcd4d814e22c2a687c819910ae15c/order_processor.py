import json, logging, os, traceback
import boto3
from datetime import datetime

logger = logging.getLogger(__name__)
try:
    from observability import log_event, track_order_completed, xray_subsegment, xray_annotate
except ImportError:
    def log_event(*a, **kw): pass
    def track_order_completed(*a, **kw): pass
    def xray_subsegment(name, **kw): return __import__("contextlib").nullcontext()
    def xray_annotate(*a, **kw): pass
sns    = boto3.client('sns')
dynamodb = boto3.resource('dynamodb')

class OrderProcessingError(Exception):
    pass

def handler(event, context):
    for record in event['Records']:
        order_data = None
        try:
            order_data = json.loads(record['body'])
            order_id   = order_data['order_id']
            logger.info(f"Processing order {order_id}")

            result = execute_order_workflow(order_data)

            if result['success']:
                _update_order_status(order_id, 'confirmed')
                _send_confirmation(order_data)
                logger.info(f"Order {order_id} processed successfully")
                track_order_completed(
                    order_id, order_data.get('customer_id', ''),
                    order_data.get('total_amount', 0),
                    len(order_data.get('items', [])))
            else:
                _update_order_status(order_id, 'failed')
                _send_system_alert(order_data, result['error'])
                raise OrderProcessingError(f"Order {order_id} failed: {result['error']}")

        except OrderProcessingError:
            raise
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            traceback.print_exc()
            if order_data:
                _send_system_alert(order_data, str(e))
            raise e

    return {'statusCode': 200, 'body': 'Orders processed'}


def execute_order_workflow(order_data):
    steps = [
        ('validate_inventory',   _validate_inventory),
        ('process_payment',      _process_payment),
        ('create_shipping_label',_create_shipping_label),
        ('update_analytics',     _update_analytics),
    ]
    completed = []
    try:
        for step_name, step_fn in steps:
            result = step_fn(order_data)
            if not result['success']:
                _rollback(completed, order_data)
                return {'success': False, 'error': f"{step_name}: {result['error']}",
                        'failed_step': step_name}
            completed.append({'step': step_name, 'result': result,
                               'timestamp': datetime.utcnow().isoformat()})
        return {'success': True, 'completed_steps': completed}
    except Exception as e:
        _rollback(completed, order_data)
        return {'success': False, 'error': str(e)}


def _rollback(completed_steps, order_data):
    rollback_map = {
        'validate_inventory':    _rollback_inventory,
        'process_payment':       _rollback_payment,
        'create_shipping_label': _rollback_shipping,
        'update_analytics':      _rollback_analytics,
    }
    for step in reversed(completed_steps):
        fn = rollback_map.get(step['step'])
        if fn:
            try:
                fn(order_data, step['result'])
                logger.info(f"Rolled back {step['step']}")
            except Exception as e:
                logger.error(f"Rollback failed for {step['step']}: {e}")


# ── stub workflow steps (replace with real implementations) ───────────────────
def _validate_inventory(order_data):
    return {'success': True}

def _process_payment(order_data):
    return {'success': True, 'transaction_id': f"txn_{order_data['order_id'][:8]}"}

def _create_shipping_label(order_data):
    return {'success': True, 'label_url': f"https://shipping.example.com/{order_data['order_id']}"}

def _update_analytics(order_data):
    return {'success': True}

def _rollback_inventory(order_data, result): pass
def _rollback_payment(order_data, result):   pass
def _rollback_shipping(order_data, result):  pass
def _rollback_analytics(order_data, result): pass


def _update_order_status(order_id, status):
    try:
        table = dynamodb.Table(os.environ.get('ORDERS_TABLE', 'Orders'))
        table.update_item(
            Key={'order_id': order_id},
            UpdateExpression='SET #s = :s, updated_at = :t',
            ExpressionAttributeNames={'#s': 'status'},
            ExpressionAttributeValues={':s': status, ':t': datetime.utcnow().isoformat() + 'Z'},
        )
    except Exception as e:
        logger.warning(f"Could not update order status: {e}")


def _send_confirmation(order_data):
    topic_arn = os.environ.get('CUSTOMER_NOTIFICATION_TOPIC')
    if not topic_arn:
        return
    message = {
        'default': f"Order {order_data['order_id']} confirmed. Total: ${order_data['total_amount']:.2f}",
        'email':   _email_body(order_data),
        'sms':     f"Order {order_data['order_id']} confirmed! Total: ${order_data['total_amount']:.2f}",
    }
    sns.publish(
        TopicArn=topic_arn,
        Message=json.dumps(message),
        MessageStructure='json',
        Subject=f"Order Confirmation - {order_data['order_id']}",
        MessageAttributes={
            'order_type':    {'DataType': 'String', 'StringValue': order_data.get('order_type', 'standard')},
            'customer_tier': {'DataType': 'String', 'StringValue': order_data.get('customer_tier', 'regular')},
        },
    )


def _send_system_alert(order_data, error_msg):
    topic_arn = os.environ.get('SYSTEM_ALERT_TOPIC')
    if not topic_arn:
        return
    sns.publish(
        TopicArn=topic_arn,
        Message=json.dumps({'error_type': 'order_processing_error',
                            'error_message': error_msg,
                            'order_id': order_data.get('order_id', 'unknown')}),
        Subject='Order Processing Error',
    )


def _email_body(order_data):
    items = '\n'.join([f"- {i.get('name', i.get('product_id', '?'))} (Qty: {i['quantity']})"
                       for i in order_data.get('items', [])])
    return (f"Thank you for your order!\n\n"
            f"Order ID: {order_data['order_id']}\n"
            f"Items:\n{items}\n"
            f"Total: ${order_data['total_amount']:.2f}\n\n"
            f"Track at: https://store.example.com/orders/{order_data['order_id']}")
