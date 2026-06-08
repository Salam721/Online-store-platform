"""
Unit tests for secrets_helper and secret_rotation.
"""
import sys, os, json, unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../layers/product_utils/python'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../lambda_code'))

os.environ.setdefault('PAYMENT_SECRET_NAME', 'prod/payment/api-key')
os.environ.setdefault('DB_SECRET_NAME',      'prod/database/credentials')


class TestSecretsHelper(unittest.TestCase):

    @patch('boto3.client')
    def test_get_secret_returns_parsed_dict(self, mock_boto):
        mock_sm = MagicMock()
        mock_sm.get_secret_value.return_value = {
            'SecretString': json.dumps({'api_key': 'sk_live_abc123'})}
        mock_boto.return_value = mock_sm

        # Clear cache between tests
        import secrets_helper
        secrets_helper._cache.clear()
        secrets_helper._client = None

        result = secrets_helper.get_secret('prod/payment/api-key')
        self.assertEqual(result['api_key'], 'sk_live_abc123')

    @patch('boto3.client')
    def test_secret_is_cached(self, mock_boto):
        mock_sm = MagicMock()
        mock_sm.get_secret_value.return_value = {
            'SecretString': json.dumps({'api_key': 'sk_live_xyz'})}
        mock_boto.return_value = mock_sm

        import secrets_helper
        secrets_helper._cache.clear()
        secrets_helper._client = None

        secrets_helper.get_secret('prod/payment/api-key')
        secrets_helper.get_secret('prod/payment/api-key')

        # Should only call API once
        mock_sm.get_secret_value.assert_called_once()

    @patch('boto3.client')
    def test_force_refresh_bypasses_cache(self, mock_boto):
        mock_sm = MagicMock()
        mock_sm.get_secret_value.return_value = {
            'SecretString': json.dumps({'api_key': 'sk_live_new'})}
        mock_boto.return_value = mock_sm

        import secrets_helper
        secrets_helper._cache = {'prod/payment/api-key': {'api_key': 'sk_live_old'}}
        secrets_helper._client = None

        result = secrets_helper.get_secret('prod/payment/api-key', force_refresh=True)
        self.assertEqual(result['api_key'], 'sk_live_new')


class TestSecretRotation(unittest.TestCase):

    def _make_sm(self, existing_pending=False):
        sm = MagicMock()
        sm.exceptions.ResourceNotFoundException = type('ResourceNotFoundException', (Exception,), {})
        if existing_pending:
            sm.get_secret_value.return_value = {
                'SecretString': json.dumps({'api_key': 'sk_live_existing_pending'})}
        else:
            sm.get_secret_value.side_effect = [
                sm.exceptions.ResourceNotFoundException('not found'),
                {'SecretString': json.dumps({'api_key': 'sk_live_current'})},
            ]
        sm.describe_secret.return_value = {
            'VersionIdsToStages': {'old_version': ['AWSCURRENT']}}
        return sm

    @patch('boto3.client')
    def test_create_secret_stages_new_key(self, mock_boto):
        sm = self._make_sm()
        mock_boto.return_value = sm

        from secret_rotation import handler
        handler({'SecretId': 'arn:test', 'ClientRequestToken': 'tok1',
                 'Step': 'createSecret'}, None)

        sm.put_secret_value.assert_called_once()
        call_kwargs = sm.put_secret_value.call_args[1]
        self.assertIn('AWSPENDING', call_kwargs['VersionStages'])

    @patch('boto3.client')
    def test_finish_secret_promotes_pending(self, mock_boto):
        sm = MagicMock()
        sm.describe_secret.return_value = {
            'VersionIdsToStages': {'old_ver': ['AWSCURRENT']}}
        mock_boto.return_value = sm

        from secret_rotation import handler
        handler({'SecretId': 'arn:test', 'ClientRequestToken': 'new_ver',
                 'Step': 'finishSecret'}, None)

        sm.update_secret_version_stage.assert_called_once()

    @patch('boto3.client')
    def test_unknown_step_raises(self, mock_boto):
        mock_boto.return_value = MagicMock()
        from secret_rotation import handler
        with self.assertRaises(ValueError):
            handler({'SecretId': 'arn:test', 'ClientRequestToken': 't',
                     'Step': 'unknownStep'}, None)


if __name__ == '__main__':
    unittest.main()
