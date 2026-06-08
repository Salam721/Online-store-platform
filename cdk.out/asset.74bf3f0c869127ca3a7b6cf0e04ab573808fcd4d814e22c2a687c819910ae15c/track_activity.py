import json, logging, traceback, os
import boto3
from datetime import datetime
from response_utils import create_success_response, create_error_response

logger   = logging.getLogger(__name__)
firehose = boto3.client('firehose')

VALID_EVENT_TYPES = {
    'product_view', 'cart_add', 'cart_remove',
    'search', 'purchase', 'wishlist_add', 'page_view',
}

def handler(event, context):
    try:
        raw_data = json.loads(event.get('body') or '{}')

        event_type = raw_data.get('event_type')
        user_id    = raw_data.get('user_id')

        if not event_type or not user_id:
            return create_error_response(400, 'event_type and user_id are required')

        if event_type not in VALID_EVENT_TYPES:
            return create_error_response(400,
                f'Invalid event_type. Must be one of: {sorted(VALID_EVENT_TYPES)}')

        record = {
            'timestamp':   datetime.utcnow().isoformat() + 'Z',
            'event_type':  event_type,
            'user_id':     user_id,
            'session_id':  raw_data.get('session_id', 'unknown'),
            'product_id':  raw_data.get('product_id'),
            'search_query':raw_data.get('search_query'),
            'page':        raw_data.get('page'),
            'metadata':    raw_data.get('metadata', {}),
        }
        # Remove None values
        record = {k: v for k, v in record.items() if v is not None}

        stream_name = os.environ['ACTIVITY_STREAM_NAME']
        firehose.put_record(
            DeliveryStreamName=stream_name,
            Record={'Data': json.dumps(record) + '\n'},
        )

        return create_success_response(202, {
            'status':  'accepted',
            'message': 'Activity event queued for processing',
        })

    except json.JSONDecodeError as e:
        return create_error_response(400, f'Invalid JSON: {str(e)}')
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        traceback.print_exc()
        return create_error_response(500, 'Internal server error')


def send_batch_activities(events, stream_name):
    """Utility for sending multiple events in one API call (up to 500)."""
    records = []
    for ev in events:
        rec = {
            'timestamp':  datetime.utcnow().isoformat() + 'Z',
            'event_type': ev.get('event_type', 'unknown'),
            'user_id':    ev.get('user_id', 'unknown'),
            'session_id': ev.get('session_id', 'unknown'),
        }
        if ev.get('product_id'):
            rec['product_id'] = ev['product_id']
        records.append({'Data': json.dumps(rec) + '\n'})

    response = firehose.put_record_batch(
        DeliveryStreamName=stream_name,
        Records=records,
    )

    if response['FailedPutCount'] > 0:
        logger.error(f"Failed to send {response['FailedPutCount']} records")
        for idx, result in enumerate(response['RequestResponses']):
            if 'ErrorCode' in result:
                logger.error(f"Record {idx} failed: {result['ErrorMessage']}")

    return response
