"""
Lambda rotation function for payment processor API key.
Invoked by Secrets Manager on the rotation schedule.

Implements the 4-step single-user rotation protocol:
  createSecret → setSecret → testSecret → finishSecret
"""
import json, logging, os
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


def handler(event, context):
    sm     = boto3.client('secretsmanager')
    arn    = event['SecretId']
    token  = event['ClientRequestToken']
    step   = event['Step']

    logger.info(f"Rotation step: {step} for secret: {arn}")

    if step == 'createSecret':
        _create_secret(sm, arn, token)
    elif step == 'setSecret':
        _set_secret(sm, arn, token)
    elif step == 'testSecret':
        _test_secret(sm, arn, token)
    elif step == 'finishSecret':
        _finish_secret(sm, arn, token)
    else:
        raise ValueError(f"Unknown rotation step: {step}")


def _create_secret(sm, arn, token):
    """Generate and stage the new API key as AWSPENDING."""
    try:
        sm.get_secret_value(SecretId=arn, VersionId=token, VersionStage='AWSPENDING')
        logger.info("AWSPENDING version already exists — skipping createSecret")
        return
    except sm.exceptions.ResourceNotFoundException:
        pass

    current = json.loads(
        sm.get_secret_value(SecretId=arn, VersionStage='AWSCURRENT')['SecretString'])

    new_key = _generate_new_api_key(current['api_key'])

    sm.put_secret_value(
        SecretId=arn,
        ClientRequestToken=token,
        SecretString=json.dumps({'api_key': new_key}),
        VersionStages=['AWSPENDING'],
    )
    logger.info("Staged new API key as AWSPENDING")


def _set_secret(sm, arn, token):
    """Activate the pending key with the external payment processor."""
    pending = json.loads(
        sm.get_secret_value(SecretId=arn, VersionId=token,
                            VersionStage='AWSPENDING')['SecretString'])
    _activate_api_key(pending['api_key'])
    logger.info("Activated pending API key with payment processor")


def _test_secret(sm, arn, token):
    """Validate the pending key works before finalising rotation."""
    pending = json.loads(
        sm.get_secret_value(SecretId=arn, VersionId=token,
                            VersionStage='AWSPENDING')['SecretString'])
    _test_payment_api(pending['api_key'])
    logger.info("Pending API key validated successfully")


def _finish_secret(sm, arn, token):
    """Promote AWSPENDING to AWSCURRENT."""
    metadata = sm.describe_secret(SecretId=arn)
    for vid, stages in metadata.get('VersionIdsToStages', {}).items():
        if 'AWSCURRENT' in stages:
            if vid == token:
                logger.info("Token already marked AWSCURRENT")
                return
            sm.update_secret_version_stage(
                SecretId=arn,
                VersionStage='AWSCURRENT',
                MoveToVersionId=token,
                RemoveFromVersionId=vid,
            )
            logger.info(f"Promoted {token} to AWSCURRENT")
            return


# ── Stubs — replace with real payment processor SDK calls ────────────────────
def _generate_new_api_key(current_key: str) -> str:
    """Call payment processor API to create a new key. Replace with real SDK."""
    import secrets
    return f"sk_live_{secrets.token_hex(16)}"


def _activate_api_key(new_key: str) -> None:
    """Activate new key with payment processor. Replace with real SDK."""
    pass


def _test_payment_api(api_key: str) -> None:
    """Smoke-test the new key. Replace with real SDK."""
    if not api_key.startswith('sk_'):
        raise ValueError("API key format validation failed")
