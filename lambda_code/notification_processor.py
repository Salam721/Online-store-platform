import json, logging, os, traceback
import boto3

logger = logging.getLogger(__name__)
sns    = boto3.client('sns')

def handler(event, context):
    try:
        # Handles both EventBridge direct and SNS-wrapped events
        if 'detail-type' in event:
            event_type   = event['detail-type']
            event_detail = event['detail']
        else:
            for record in event.get('Records', []):
                _dispatch(json.loads(record['Sns']['Message']),
                          record['Sns'].get('MessageAttributes', {}))
            return {'statusCode': 200, 'body': 'Notifications dispatched'}

        _dispatch(event_detail, {}, event_type)
        return {'statusCode': 200, 'body': 'Notification sent'}

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        traceback.print_exc()
        raise e


def _dispatch(detail, attributes, event_type=''):
    notification_type = (attributes.get('notification_type', {}).get('Value')
                         or event_type or 'general')

    if 'Order' in notification_type or 'order' in notification_type.lower():
        _send_order_notification(detail)
    elif 'inventory' in notification_type.lower() or 'Stock' in notification_type:
        _send_inventory_notification(detail)
    elif 'system' in notification_type.lower():
        _send_system_notification(detail)
    else:
        logger.info(f"Unhandled notification type: {notification_type}")


def _send_order_notification(detail):
    topic_arn = os.environ.get('CUSTOMER_NOTIFICATION_TOPIC')
    if topic_arn:
        sns.publish(
            TopicArn=topic_arn,
            Message=json.dumps({'default': f"Order update for {detail.get('orderId', detail.get('order_id', '?'))}",
                                 'email': json.dumps(detail)}),
            MessageStructure='json',
            Subject='Order Update',
        )


def _send_inventory_notification(detail):
    topic_arn = os.environ.get('INVENTORY_ALERT_TOPIC')
    if topic_arn:
        sns.publish(
            TopicArn=topic_arn,
            Message=json.dumps(detail),
            Subject=f"Inventory Alert: {detail.get('productName', '')}",
            MessageAttributes={
                'alert_type': {'DataType': 'String', 'StringValue': 'inventory_low'},
                'urgency':    {'DataType': 'String',
                               'StringValue': 'high' if int(detail.get('currentStock', 1)) == 0 else 'medium'},
            },
        )


def _send_system_notification(detail):
    topic_arn = os.environ.get('SYSTEM_ALERT_TOPIC')
    if topic_arn:
        sns.publish(TopicArn=topic_arn, Message=json.dumps(detail), Subject='System Alert')
