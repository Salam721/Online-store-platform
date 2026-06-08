import sys, os, json, base64, unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../layers/product_utils/python'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../lambda_code'))

def _make_record(record_id, data):
    encoded = base64.b64encode(json.dumps(data).encode()).decode()
    return {'recordId': record_id, 'data': encoded}

def _decode_output(record):
    return json.loads(base64.b64decode(record['data']).decode().strip())

class TestFirehoseTransformer(unittest.TestCase):
    def setUp(self):
        os.environ['APP_ENV'] = 'test'

    def test_transforms_valid_record(self):
        from firehose_transformer import handler
        event = {'records': [_make_record('r1', {
            'event_type': 'product_view', 'user_id': 'user_123',
            'timestamp': '2026-01-15T10:30:00Z'})]}
        result = handler(event, None)
        self.assertEqual(len(result['records']), 1)
        self.assertEqual(result['records'][0]['result'], 'Ok')
        out = _decode_output(result['records'][0])
        self.assertEqual(out['event_category'], 'browse')
        self.assertEqual(out['event_date'], '2026-01-15')
        self.assertIn('processed_at', out)

    def test_drops_bot_users(self):
        from firehose_transformer import handler
        event = {'records': [_make_record('r2', {
            'event_type': 'product_view', 'user_id': 'bot_crawler',
            'timestamp': '2026-01-15T10:30:00Z'})]}
        result = handler(event, None)
        self.assertEqual(result['records'][0]['result'], 'Dropped')

    def test_classifies_purchase_as_conversion(self):
        from firehose_transformer import handler
        event = {'records': [_make_record('r3', {
            'event_type': 'purchase', 'user_id': 'user_456',
            'timestamp': '2026-01-15T10:30:00Z'})]}
        result = handler(event, None)
        out = _decode_output(result['records'][0])
        self.assertEqual(out['event_category'], 'conversion')

    def test_classifies_cart_add_as_engagement(self):
        from firehose_transformer import handler
        event = {'records': [_make_record('r4', {
            'event_type': 'cart_add', 'user_id': 'user_789',
            'timestamp': '2026-01-15T10:30:00Z'})]}
        result = handler(event, None)
        out = _decode_output(result['records'][0])
        self.assertEqual(out['event_category'], 'engagement')

    def test_handles_batch_of_records(self):
        from firehose_transformer import handler
        records = [
            _make_record('r5', {'event_type': 'product_view', 'user_id': 'u1', 'timestamp': '2026-01-15T10:00:00Z'}),
            _make_record('r6', {'event_type': 'purchase',     'user_id': 'u2', 'timestamp': '2026-01-15T10:01:00Z'}),
            _make_record('r7', {'event_type': 'search',       'user_id': 'bot_spider', 'timestamp': '2026-01-15T10:02:00Z'}),
        ]
        result = handler({'records': records}, None)
        self.assertEqual(len(result['records']), 3)
        statuses = [r['result'] for r in result['records']]
        self.assertEqual(statuses.count('Ok'),      2)
        self.assertEqual(statuses.count('Dropped'), 1)

if __name__ == '__main__':
    unittest.main()
