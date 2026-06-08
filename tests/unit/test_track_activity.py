import sys, os, json, unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../layers/product_utils/python'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../lambda_code'))

VALID_EVENT = {'event_type': 'product_view', 'user_id': 'user_123',
               'session_id': 'sess_abc', 'product_id': 'prod_001'}

class TestTrackActivity(unittest.TestCase):
    @patch('boto3.client')
    def test_success(self, mock_boto):
        mock_firehose = MagicMock()
        mock_firehose.put_record.return_value = {'RecordId': 'rec_1'}
        mock_boto.return_value = mock_firehose

        with patch.dict(os.environ, {'ACTIVITY_STREAM_NAME': 'customer-activity-stream'}):
            from track_activity import handler
            r = handler({'body': json.dumps(VALID_EVENT)}, None)
            self.assertEqual(r['statusCode'], 202)
            mock_firehose.put_record.assert_called_once()

    @patch('boto3.client')
    def test_missing_fields(self, mock_boto):
        with patch.dict(os.environ, {'ACTIVITY_STREAM_NAME': 'customer-activity-stream'}):
            from track_activity import handler
            r = handler({'body': json.dumps({'user_id': 'u1'})}, None)
            self.assertEqual(r['statusCode'], 400)

    @patch('boto3.client')
    def test_invalid_event_type(self, mock_boto):
        with patch.dict(os.environ, {'ACTIVITY_STREAM_NAME': 'customer-activity-stream'}):
            from track_activity import handler
            bad = {**VALID_EVENT, 'event_type': 'invalid_type'}
            r = handler({'body': json.dumps(bad)}, None)
            self.assertEqual(r['statusCode'], 400)

    @patch('boto3.client')
    def test_invalid_json(self, mock_boto):
        with patch.dict(os.environ, {'ACTIVITY_STREAM_NAME': 'customer-activity-stream'}):
            from track_activity import handler
            r = handler({'body': 'not json {'}, None)
            self.assertEqual(r['statusCode'], 400)

if __name__ == '__main__':
    unittest.main()
