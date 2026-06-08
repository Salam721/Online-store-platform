"""
CodeDeploy pre-traffic lifecycle hook.
Runs smoke tests against the NEW Lambda version before any traffic shifts.
If tests fail the deployment is rolled back automatically.

Invoked by CodeDeploy with:
  {"DeploymentId": "d-XXXXX", "LifecycleEventHookExecutionId": "..."}
"""
import os, json, logging
import boto3

logger   = logging.getLogger(__name__)
codedeploy = boto3.client('codedeploy')
lambda_client = boto3.client('lambda')


def handler(event, context):
    deployment_id  = event['DeploymentId']
    hook_exec_id   = event['LifecycleEventHookExecutionId']
    logger.info(f"Pre-traffic hook: deployment {deployment_id}")

    try:
        passed = _run_smoke_tests()
        status = 'Succeeded' if passed else 'Failed'
        logger.info(f"Smoke tests {'passed' if passed else 'FAILED'}")
    except Exception as e:
        logger.error(f"Smoke test error: {e}")
        status = 'Failed'

    codedeploy.put_lifecycle_event_hook_execution_status(
        deploymentId=deployment_id,
        lifecycleEventHookExecutionId=hook_exec_id,
        status=status,
    )
    return {'statusCode': 200, 'status': status}


def _run_smoke_tests() -> bool:
    """Invoke the new Lambda version directly to verify it starts correctly."""
    fn_name = os.environ.get('TARGET_FUNCTION', 'get_product')

    tests = [
        # Missing path parameter — expect 400
        {'pathParameters': None},
        # Valid structure — expect 400 (no DB in hook env) or 200
        {'pathParameters': {'id': 'smoke-test-product'}},
    ]

    for payload in tests:
        try:
            resp = lambda_client.invoke(
                FunctionName=fn_name,
                InvocationType='RequestResponse',
                Payload=json.dumps(payload),
            )
            result = json.loads(resp['Payload'].read())
            # Any 5xx from the function itself = problem
            if result.get('statusCode', 500) >= 500:
                logger.error(f"Smoke test returned {result.get('statusCode')}: {result}")
                return False
        except Exception as e:
            logger.error(f"Smoke test invocation failed: {e}")
            return False

    return True
