import json, logging, os, traceback
import boto3

logger   = logging.getLogger(__name__)
dynamodb = boto3.resource('dynamodb')
eventbridge = boto3.client('events')

def handler(event, context):
    try:
        event_type   = event['detail-type']
        event_detail = event['detail']
        logger.info(f"Processing {event_type} event")

        table = dynamodb.Table(os.environ.get('PRODUCTS_TABLE', 'Products'))

        if event_type == 'Order Placed':
            for item in event_detail.get('items', []):
                product_id = item.get('product_id') or item.get('productId')
                quantity   = item.get('quantity', 1)
                try:
                    response = table.update_item(
                        Key={'id': product_id},
                        UpdateExpression='ADD inventory_count :qty',
                        ConditionExpression='attribute_exists(id) AND inventory_count >= :qty',
                        ExpressionAttributeValues={':qty': -quantity},
                        ReturnValues='ALL_NEW',
                    )
                    updated = response['Attributes']
                    # Publish low-stock event if needed
                    if int(updated.get('inventory_count', 999)) <= 10:
                        _publish_low_stock(updated, os.environ.get('INVENTORY_EVENT_BUS', 'online-store-inventory'))
                except Exception as e:
                    logger.error(f"Failed to update inventory for {product_id}: {e}")

        return {'statusCode': 200, 'body': 'Inventory updated'}

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        traceback.print_exc()
        raise e


def _publish_low_stock(product, event_bus):
    try:
        eventbridge.put_events(Entries=[{
            'Source':      'store.inventory',
            'DetailType':  'Stock Low',
            'Detail':      json.dumps({
                'productId':    product.get('id'),
                'productName':  product.get('title', ''),
                'category':     product.get('category', ''),
                'currentStock': int(product.get('inventory_count', 0)),
                'reorderLevel': 10,
            }),
            'EventBusName': event_bus,
        }])
    except Exception as e:
        logger.warning(f"Could not publish low-stock event: {e}")
