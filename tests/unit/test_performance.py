"""
Unit tests for performance.py utilities.
"""
import sys, os, json, time, unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../layers/product_utils/python'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../lambda_code'))

os.environ.setdefault('APP_ENV', 'test')


def _mock_context(remaining_ms=30000, memory_mb=512, fn_name='test_fn'):
    ctx = MagicMock()
    ctx.get_remaining_time_in_millis.return_value = remaining_ms
    ctx.memory_limit_in_mb = memory_mb
    ctx.function_name = fn_name
    return ctx


class TestTimeoutGuard(unittest.TestCase):

    def test_no_exception_when_time_sufficient(self):
        from performance import timeout_guard
        timeout_guard(_mock_context(30000))  # 30 seconds remaining — fine

    def test_raises_when_time_insufficient(self):
        from performance import timeout_guard
        with self.assertRaises(TimeoutError):
            timeout_guard(_mock_context(3000))  # 3 seconds < 5s buffer

    def test_custom_buffer(self):
        from performance import timeout_guard
        timeout_guard(_mock_context(2000), buffer_ms=1000)  # 2s > 1s buffer — fine
        with self.assertRaises(TimeoutError):
            timeout_guard(_mock_context(500), buffer_ms=1000)  # 0.5s < 1s buffer


class TestTimedDecorator(unittest.TestCase):

    def test_returns_handler_result(self):
        from performance import timed

        @timed
        def handler(event, context):
            return {'statusCode': 200}

        result = handler({}, _mock_context())
        self.assertEqual(result['statusCode'], 200)

    def test_reraises_exception(self):
        from performance import timed

        @timed
        def handler(event, context):
            raise ValueError("boom")

        with self.assertRaises(ValueError):
            handler({}, _mock_context())

    def test_logs_timing(self):
        from performance import timed

        @timed
        def handler(event, context):
            return {}

        with patch('performance.logger') as mock_log:
            handler({}, _mock_context())
            mock_log.info.assert_called_once()
            log_data = json.loads(mock_log.info.call_args[0][0])
            self.assertEqual(log_data['event'], 'lambda_timing')
            self.assertIn('duration_ms', log_data)


class TestETagHelpers(unittest.TestCase):

    def test_etag_is_quoted_hex(self):
        from performance import generate_etag
        etag = generate_etag('{"id":"p1"}', '2026-01-01')
        self.assertTrue(etag.startswith('"'))
        self.assertTrue(etag.endswith('"'))

    def test_same_content_same_etag(self):
        from performance import generate_etag
        e1 = generate_etag('content', 'ts')
        e2 = generate_etag('content', 'ts')
        self.assertEqual(e1, e2)

    def test_different_content_different_etag(self):
        from performance import generate_etag
        self.assertNotEqual(generate_etag('a', 'ts'), generate_etag('b', 'ts'))

    def test_check_etag_match(self):
        from performance import generate_etag, check_etag
        etag  = generate_etag('content', 'ts')
        event = {'headers': {'If-None-Match': etag}}
        self.assertTrue(check_etag(event, etag))

    def test_check_etag_no_match(self):
        from performance import generate_etag, check_etag
        etag  = generate_etag('content', 'ts')
        event = {'headers': {'If-None-Match': '"old_etag"'}}
        self.assertFalse(check_etag(event, etag))


class TestCacheHeaders(unittest.TestCase):

    def test_static_assets_long_ttl(self):
        from performance import cache_headers
        h = cache_headers('static')
        self.assertIn('immutable', h['Cache-Control'])
        self.assertIn('max-age=31536000', h['Cache-Control'])

    def test_api_medium_ttl(self):
        from performance import cache_headers
        h = cache_headers('api')
        self.assertIn('max-age=600', h['Cache-Control'])
        self.assertIn('public', h['Cache-Control'])

    def test_user_private(self):
        from performance import cache_headers
        h = cache_headers('user')
        self.assertIn('private', h['Cache-Control'])

    def test_no_cache_for_dynamic(self):
        from performance import cache_headers
        h = cache_headers('no_cache')
        self.assertEqual(h['Cache-Control'], 'no-cache')


class TestL1Cache(unittest.TestCase):

    def setUp(self):
        import performance
        performance._L1.clear()

    def test_set_and_get(self):
        from performance import l1_set, l1_get
        l1_set('product_details', 'p1', {'title': 'Widget'})
        result = l1_get('product_details', 'p1')
        self.assertEqual(result['title'], 'Widget')

    def test_miss_returns_none(self):
        from performance import l1_get
        self.assertIsNone(l1_get('product_details', 'nonexistent'))

    def test_expired_returns_none(self):
        import performance
        performance._TTL_MAP['test_type'] = 0  # 0-second TTL
        performance._L1['test_type:k'] = {'data': 'val', 'expires_at': time.time() - 1}
        result = performance.l1_get('test_type', 'k')
        self.assertIsNone(result)

    def test_delete(self):
        from performance import l1_set, l1_get, l1_delete
        l1_set('product_details', 'p2', 'value')
        l1_delete('product_details', 'p2')
        self.assertIsNone(l1_get('product_details', 'p2'))

    def test_clear_type(self):
        from performance import l1_set, l1_get, l1_clear_type
        l1_set('product_details', 'p3', 'a')
        l1_set('product_details', 'p4', 'b')
        l1_clear_type('product_details')
        self.assertIsNone(l1_get('product_details', 'p3'))
        self.assertIsNone(l1_get('product_details', 'p4'))


class TestCloudfrontInvalidation(unittest.TestCase):

    @patch('boto3.client')
    def test_invalidation_returns_id(self, mock_boto):
        mock_cf = MagicMock()
        mock_cf.create_invalidation.return_value = {
            'Invalidation': {'Id': 'I123ABC'}}
        mock_boto.return_value = mock_cf

        from performance import invalidate_cloudfront
        inv_id = invalidate_cloudfront('DIST_ABC', ['/products/p1', '/products/p1/image-url'])
        self.assertEqual(inv_id, 'I123ABC')

    def test_no_op_without_distribution_id(self):
        from performance import invalidate_cloudfront
        result = invalidate_cloudfront('', ['/products/p1'])
        self.assertIsNone(result)

    @patch('boto3.client')
    def test_returns_none_on_failure(self, mock_boto):
        mock_boto.return_value.create_invalidation.side_effect = Exception("CF error")
        from performance import invalidate_cloudfront
        result = invalidate_cloudfront('DIST_ABC', ['/products/p1'])
        self.assertIsNone(result)


if __name__ == '__main__':
    unittest.main()
