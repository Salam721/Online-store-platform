"""
Lambda function invoked by Firehose for inline record transformation.
Must return records with result: 'Ok' | 'Dropped' | 'ProcessingFailed'
Each output record Data must be base64-encoded.
"""
import json, base64, logging, os
from datetime import datetime

logger = logging.getLogger(__name__)

# Bot/test user IDs to drop from analytics
EXCLUDED_USER_PREFIXES = ('bot_', 'test_', 'internal_')


def handler(event, context):
    output = []

    for record in event['records']:
        record_id = record['recordId']
        try:
            # Decode incoming data
            raw       = base64.b64decode(record['data']).decode('utf-8').strip()
            data      = json.loads(raw)

            # ── Filter: drop bot/test events ──────────────────────────────────
            user_id = data.get('user_id', '')
            if any(user_id.startswith(p) for p in EXCLUDED_USER_PREFIXES):
                output.append({'recordId': record_id, 'result': 'Dropped', 'data': record['data']})
                continue

            # ── Enrich: add derived fields ────────────────────────────────────
            ts = data.get('timestamp', datetime.utcnow().isoformat() + 'Z')
            data['processed_at']  = datetime.utcnow().isoformat() + 'Z'
            data['event_date']    = ts[:10]   # YYYY-MM-DD  for S3 partitioning
            data['event_hour']    = ts[11:13] # HH          for S3 partitioning
            data['environment']   = os.environ.get('APP_ENV', 'dev')

            # ── Classify event category ───────────────────────────────────────
            event_type = data.get('event_type', '')
            if event_type in ('purchase',):
                data['event_category'] = 'conversion'
            elif event_type in ('cart_add', 'cart_remove', 'wishlist_add'):
                data['event_category'] = 'engagement'
            elif event_type in ('product_view', 'page_view'):
                data['event_category'] = 'browse'
            elif event_type == 'search':
                data['event_category'] = 'search'
            else:
                data['event_category'] = 'other'

            # ── Re-encode ─────────────────────────────────────────────────────
            transformed = base64.b64encode(
                (json.dumps(data) + '\n').encode('utf-8')
            ).decode('utf-8')

            output.append({'recordId': record_id, 'result': 'Ok', 'data': transformed})

        except Exception as e:
            logger.error(f"Failed to transform record {record_id}: {e}")
            output.append({'recordId': record_id, 'result': 'ProcessingFailed',
                           'data': record['data']})

    logger.info(f"Processed {len(output)} records: "
                f"ok={sum(1 for r in output if r['result']=='Ok')}, "
                f"dropped={sum(1 for r in output if r['result']=='Dropped')}, "
                f"failed={sum(1 for r in output if r['result']=='ProcessingFailed')}")

    return {'records': output}
