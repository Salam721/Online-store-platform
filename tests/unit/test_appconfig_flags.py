"""
Unit tests for appconfig_flags feature flag client.
"""
import sys, os, json, unittest
from unittest.mock import patch, MagicMock
from io import BytesIO

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../layers/product_utils/python'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../lambda_code'))

os.environ.setdefault('APPCONFIG_APP',     'online-store-test')
os.environ.setdefault('APPCONFIG_ENV',     'test')
os.environ.setdefault('APPCONFIG_PROFILE', 'feature-flags')
os.environ.setdefault('APPCONFIG_CLIENT',  'test-lambda')

SAMPLE_FLAGS = {
    "flags": {
        "ai-recommendations":  {"name": "AI Recommendations"},
        "new-checkout-flow":   {"name": "New Checkout Flow"},
        "real-time-inventory": {"name": "Real-time Inventory"},
    },
    "values": {
        "ai-recommendations":  {"enabled": False},
        "new-checkout-flow":   {"enabled": True, "rollout-percentage": 50},
        "real-time-inventory": {"enabled": True},
    }
}


def _mock_appconfig(flags=None):
    mock = MagicMock()
    flags = flags or SAMPLE_FLAGS
    mock.get_configuration.return_value = {
        'Content': BytesIO(json.dumps(flags).encode())}
    return mock


class TestFeatureFlagRetrieval(unittest.TestCase):

    def setUp(self):
        import appconfig_flags
        appconfig_flags._flag_cache = None
        appconfig_flags._appconfig  = None

    @patch('boto3.client')
    def test_is_enabled_true(self, mock_boto):
        mock_boto.return_value = _mock_appconfig()
        from appconfig_flags import is_enabled
        self.assertTrue(is_enabled('real-time-inventory'))

    @patch('boto3.client')
    def test_is_enabled_false(self, mock_boto):
        mock_boto.return_value = _mock_appconfig()
        from appconfig_flags import is_enabled
        self.assertFalse(is_enabled('ai-recommendations'))

    @patch('boto3.client')
    def test_unknown_flag_returns_false(self, mock_boto):
        mock_boto.return_value = _mock_appconfig()
        from appconfig_flags import is_enabled
        self.assertFalse(is_enabled('nonexistent-flag'))

    @patch('boto3.client')
    def test_get_flag_returns_dict(self, mock_boto):
        mock_boto.return_value = _mock_appconfig()
        from appconfig_flags import get_flag
        flag = get_flag('new-checkout-flow')
        self.assertEqual(flag['rollout-percentage'], 50)

    @patch('boto3.client')
    def test_flags_cached_after_first_call(self, mock_boto):
        mock_boto.return_value = _mock_appconfig()
        from appconfig_flags import get_flags
        get_flags()
        get_flags()
        mock_boto.return_value.get_configuration.assert_called_once()

    @patch('boto3.client')
    def test_force_refresh_bypasses_cache(self, mock_boto):
        mock_boto.return_value = _mock_appconfig()
        from appconfig_flags import get_flags
        get_flags()
        get_flags(force_refresh=True)
        self.assertEqual(mock_boto.return_value.get_configuration.call_count, 2)

    @patch('boto3.client')
    def test_appconfig_unavailable_returns_empty(self, mock_boto):
        from botocore.exceptions import ClientError
        mock_boto.return_value.get_configuration.side_effect = ClientError(
            {'Error': {'Code': 'ServiceUnavailableException', 'Message': ''}}, 'GetConfiguration')
        import appconfig_flags
        appconfig_flags._flag_cache = None
        appconfig_flags._appconfig  = None
        from appconfig_flags import get_flags
        result = get_flags()
        self.assertEqual(result, {})


class TestRolloutLogic(unittest.TestCase):

    def setUp(self):
        import appconfig_flags
        appconfig_flags._flag_cache = None
        appconfig_flags._appconfig  = None

    @patch('boto3.client')
    def test_in_rollout_consistent_for_same_user(self, mock_boto):
        mock_boto.return_value = _mock_appconfig()
        from appconfig_flags import in_rollout
        # Same user should always get the same result
        result1 = in_rollout('new-checkout-flow', 'user_abc')
        result2 = in_rollout('new-checkout-flow', 'user_abc')
        self.assertEqual(result1, result2)

    @patch('boto3.client')
    def test_disabled_flag_never_in_rollout(self, mock_boto):
        mock_boto.return_value = _mock_appconfig()
        from appconfig_flags import in_rollout
        # ai-recommendations is disabled
        self.assertFalse(in_rollout('ai-recommendations', 'user_xyz'))

    @patch('boto3.client')
    def test_100_percent_rollout_always_true(self, mock_boto):
        flags = dict(SAMPLE_FLAGS)
        flags['values'] = dict(flags['values'])
        flags['values']['new-checkout-flow'] = {'enabled': True, 'rollout-percentage': 100}
        mock_boto.return_value = _mock_appconfig(flags)
        from appconfig_flags import in_rollout
        self.assertTrue(in_rollout('new-checkout-flow', 'any_user_123'))

    @patch('boto3.client')
    def test_0_percent_rollout_always_false(self, mock_boto):
        flags = dict(SAMPLE_FLAGS)
        flags['values'] = dict(flags['values'])
        flags['values']['new-checkout-flow'] = {'enabled': True, 'rollout-percentage': 0}
        mock_boto.return_value = _mock_appconfig(flags)
        from appconfig_flags import in_rollout
        self.assertFalse(in_rollout('new-checkout-flow', 'any_user_456'))


if __name__ == '__main__':
    unittest.main()
