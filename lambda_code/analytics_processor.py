import json, logging, os, traceback
import boto3

logger   = logging.getLogger(__name__)
dynamodb = boto3.resource('dynamodb')

def handler(event, context):
    try:
        # Handle both EventBridge and SQS-wrapped events
        if 'detail-type' in event:
            _store_event(event, context.aws_request_id)
        else:
            for record in event.get('Records', []):
                _store_event(json.loads(record['body']), context.aws_request_id)

        return {'statusCode': 200, 'body': 'Analytics processed'}

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        traceback.print_exc()
        raise e


def _store_event(ev, request_id):
    table_name = os.environ.get('ANALYTICS_TABLE', 'AnalyticsEvents')
    try:
        table = dynamodb.Table(table_name)
        table.put_item(Item={
            'event_id':     request_id,
            'event_type':   ev.get('detail-type', ev.get('source', 'unknown')),
            'event_source': ev.get('source', ''),
            'event_time':   ev.get('time', ''),
            'event_detail': json.dumps(ev.get('detail', ev)),
        })
    except Exception as e:
        logger.warning(f"Could not store analytics event: {e}")
