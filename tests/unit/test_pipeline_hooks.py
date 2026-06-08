"""
Unit tests for CodeDeploy pre/post traffic hook handlers.
"""
import sys, os, json, unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../layers/product_utils/python'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../pipeline/hooks'))

os.environ.setdefault('TARGET_FUNCTION', 'get_product')
os.environ.setdefault('PRODUCTS_TABLE',  'Products')
os.environ.setdefault('APP_ENV',         'test')

HOOK_EVENT = {
    'DeploymentId':                  'd-ABC123',
    'LifecycleEventHookExecutionId': 'hook-exec-001',
}


class TestPreTrafficHook(unittest.TestCase):

    @patch('boto3.client')
    def test_succeeds_when_smoke_tests_pass(self, mock_boto):
        mock_cd     = MagicMock()
        mock_lambda = MagicMock()
        mock_lambda.invoke.return_value = {
            'Payload': __import__('io').BytesIO(
                json.dumps({'statusCode': 400, 'body': '{"error":"Product ID required"}'}).encode())}
        mock_boto.side_effect = lambda svc, **kw: (
            mock_cd if svc == 'codedeploy' else mock_lambda)

        from pre_traffic_hook import handler
        resp = handler(HOOK_EVENT, None)
        self.assertEqual(resp['status'], 'Succeeded')
        mock_cd.put_lifecycle_event_hook_execution_status.assert_called_once_with(
            deploymentId='d-ABC123',
            lifecycleEventHookExecutionId='hook-exec-001',
            status='Succeeded')

    @patch('boto3.client')
    def test_fails_when_lambda_returns_500(self, mock_boto):
        mock_cd     = MagicMock()
        mock_lambda = MagicMock()
        mock_lambda.invoke.return_value = {
            'Payload': __import__('io').BytesIO(
                json.dumps({'statusCode': 500, 'body': 'Internal error'}).encode())}
        mock_boto.side_effect = lambda svc, **kw: (
            mock_cd if svc == 'codedeploy' else mock_lambda)

        from pre_traffic_hook import handler
        resp = handler(HOOK_EVENT, None)
        self.assertEqual(resp['status'], 'Failed')
        mock_cd.put_lifecycle_event_hook_execution_status.assert_called_once_with(
            deploymentId='d-ABC123',
            lifecycleEventHookExecutionId='hook-exec-001',
            status='Failed')

    @patch('boto3.client')
    def test_fails_when_invocation_throws(self, mock_boto):
        mock_cd     = MagicMock()
        mock_lambda = MagicMock()
        mock_lambda.invoke.side_effect = Exception("Connection refused")
        mock_boto.side_effect = lambda svc, **kw: (
            mock_cd if svc == 'codedeploy' else mock_lambda)

        from pre_traffic_hook import handler
        resp = handler(HOOK_EVENT, None)
        self.assertEqual(resp['status'], 'Failed')

    @patch('boto3.client')
    def test_reports_status_regardless_of_outcome(self, mock_boto):
        """CodeDeploy MUST always be notified — even on exception."""
        mock_cd     = MagicMock()
        mock_lambda = MagicMock()
        mock_lambda.invoke.side_effect = RuntimeError("boom")
        mock_boto.side_effect = lambda svc, **kw: (
            mock_cd if svc == 'codedeploy' else mock_lambda)

        from pre_traffic_hook import handler
        handler(HOOK_EVENT, None)
        mock_cd.put_lifecycle_event_hook_execution_status.assert_called_once()


class TestPostTrafficHook(unittest.TestCase):

    @patch('boto3.client')
    def test_succeeds_when_error_rate_low(self, mock_boto):
        mock_cd = MagicMock()
        mock_cw = MagicMock()
        # 2 errors out of 1000 invocations = 0.2% — below 1% threshold
        mock_cw.get_metric_statistics.side_effect = [
            {'Datapoints': [{'Sum': 2}]},     # Errors
            {'Datapoints': [{'Sum': 1000}]},  # Invocations
        ]
        mock_boto.side_effect = lambda svc, **kw: (
            mock_cd if svc == 'codedeploy' else mock_cw)

        from post_traffic_hook import handler
        resp = handler(HOOK_EVENT, None)
        self.assertEqual(resp['status'], 'Succeeded')

    @patch('boto3.client')
    def test_fails_when_error_rate_high(self, mock_boto):
        mock_cd = MagicMock()
        mock_cw = MagicMock()
        # 50 errors out of 100 invocations = 50% — above 1% threshold
        mock_cw.get_metric_statistics.side_effect = [
            {'Datapoints': [{'Sum': 50}]},
            {'Datapoints': [{'Sum': 100}]},
        ]
        mock_boto.side_effect = lambda svc, **kw: (
            mock_cd if svc == 'codedeploy' else mock_cw)

        from post_traffic_hook import handler
        resp = handler(HOOK_EVENT, None)
        self.assertEqual(resp['status'], 'Failed')

    @patch('boto3.client')
    def test_succeeds_with_no_invocations_yet(self, mock_boto):
        mock_cd = MagicMock()
        mock_cw = MagicMock()
        mock_cw.get_metric_statistics.return_value = {'Datapoints': []}
        mock_boto.side_effect = lambda svc, **kw: (
            mock_cd if svc == 'codedeploy' else mock_cw)

        from post_traffic_hook import handler
        resp = handler(HOOK_EVENT, None)
        self.assertEqual(resp['status'], 'Succeeded')


if __name__ == '__main__':
    unittest.main()
