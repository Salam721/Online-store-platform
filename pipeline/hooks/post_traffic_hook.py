"""
CodeDeploy post-traffic lifecycle hook.
Validates the deployed version is serving real traffic correctly.
Signals CodeDeploy to complete or roll back.
"""
import os, json, logging
import boto3

logger     = logging.getLogger(__name__)
codedeploy = boto3.client('codedeploy')
cloudwatch = boto3.client('cloudwatch')


def handler(event, context):
    deployment_id = event['DeploymentId']
    hook_exec_id  = event['LifecycleEventHookExecutionId']
    logger.info(f"Post-traffic hook: deployment {deployment_id}")

    try:
        passed = _check_error_rate()
        status = 'Succeeded' if passed else 'Failed'
    except Exception as e:
        logger.error(f"Post-traffic check error: {e}")
        status = 'Failed'

    codedeploy.put_lifecycle_event_hook_execution_status(
        deploymentId=deployment_id,
        lifecycleEventHookExecutionId=hook_exec_id,
        status=status,
    )
    return {'statusCode': 200, 'status': status}


def _check_error_rate() -> bool:
    """Check that error rate stayed below 1% in the last 2 minutes."""
    from datetime import datetime, timedelta, timezone
    fn_name = os.environ.get('TARGET_FUNCTION', 'get_product')
    now     = datetime.now(timezone.utc)
    start   = now - timedelta(minutes=2)

    def _get_metric(metric_name):
        resp = cloudwatch.get_metric_statistics(
            Namespace='AWS/Lambda',
            MetricName=metric_name,
            Dimensions=[{'Name': 'FunctionName', 'Value': fn_name}],
            StartTime=start, EndTime=now,
            Period=120, Statistics=['Sum'],
        )
        points = resp.get('Datapoints', [])
        return sum(p['Sum'] for p in points) if points else 0

    errors     = _get_metric('Errors')
    invocations= _get_metric('Invocations')

    if invocations == 0:
        logger.info("No invocations yet — assuming healthy")
        return True

    error_rate = errors / invocations
    logger.info(f"Error rate: {error_rate:.2%} ({errors}/{invocations})")
    return error_rate < 0.01  # < 1%
