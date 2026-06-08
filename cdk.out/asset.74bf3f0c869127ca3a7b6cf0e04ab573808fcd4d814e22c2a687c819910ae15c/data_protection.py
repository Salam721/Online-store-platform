"""
Shared data protection utilities.
- PII masking for logs (email, phone, address)
- Log sanitization using regex patterns
- Credit card tokenization (stub — use AWS Payment Cryptography in production)
- Tenant isolation helpers

Import this module in any Lambda handler that touches customer PII.
"""
import re, json, logging, base64, os
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

# ── Regex patterns for log sanitization ──────────────────────────────────────
_EMAIL_PATTERN = re.compile(
    r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
_PHONE_PATTERN = re.compile(
    r'\b(?:\+?1[-.]?)?\(?([0-9]{3})\)?[-.]?([0-9]{3})[-.]?([0-9]{4})\b')
_CC_PATTERN = re.compile(
    r'\b(?:4[0-9]{12}(?:[0-9]{3})?'
    r'|5[1-5][0-9]{14}'
    r'|3[47][0-9]{13}'
    r'|6(?:011|5[0-9]{2})[0-9]{12})\b')
_SSN_PATTERN = re.compile(
    r'\b(?!000|666|9\d{2})\d{3}-?(?!00)\d{2}-?(?!0000)\d{4}\b')


def sanitize_log_message(message: str) -> str:
    """Replace PII patterns in a log string with safe placeholders."""
    message = _EMAIL_PATTERN.sub('[EMAIL]',       message)
    message = _PHONE_PATTERN.sub('[PHONE]',        message)
    message = _CC_PATTERN.sub('[CREDIT_CARD]',    message)
    message = _SSN_PATTERN.sub('[SSN]',            message)
    return message


# ── Field-level masking ───────────────────────────────────────────────────────
def mask_email(email: str) -> str:
    if not email or '@' not in email:
        return 'invalid@example.com'
    username, domain = email.split('@', 1)
    masked_user   = (username[0] + '***') if len(username) > 1 else '***'
    parts         = domain.split('.')
    masked_domain = (parts[0][0] + '***.' + parts[-1]) if len(parts) > 1 else '***'
    return f"{masked_user}@{masked_domain}"


def mask_phone(phone: str) -> str:
    if not phone:
        return '***-***-****'
    digits    = re.sub(r'\D', '', phone)
    last_four = digits[-4:] if len(digits) >= 4 else '****'
    if len(digits) == 10:
        return f"***-***-{last_four}"
    elif len(digits) == 11:
        return f"+1-***-***-{last_four}"
    return f"+***-***-{last_four}"


def mask_address(address: dict) -> dict:
    return {
        'street': '*** *** St',
        'city':   address.get('city', 'Unknown'),
        'state':  address.get('state', 'XX'),
        'zip':    (address.get('zip', '')[:2] + '***') if address.get('zip') else '***',
    }


def mask_customer_data(customer: dict) -> dict:
    """Return a copy of customer dict with PII fields masked for safe logging."""
    masked = customer.copy()
    if 'email'   in masked: masked['email']   = mask_email(masked['email'])
    if 'phone'   in masked: masked['phone']   = mask_phone(masked['phone'])
    if 'address' in masked: masked['address'] = mask_address(masked['address'])
    if 'name'    in masked: masked['name']    = masked['name'][0] + '***'
    return masked


# ── KMS client-side encryption ────────────────────────────────────────────────
_kms = None

def _kms_client():
    global _kms
    if _kms is None:
        _kms = boto3.client('kms')
    return _kms


def encrypt_pii(plaintext: str, key_alias: str = 'alias/customer-data') -> str:
    """Encrypt a PII string with KMS and return base64-encoded ciphertext."""
    try:
        resp = _kms_client().encrypt(
            KeyId=plaintext and key_alias,
            Plaintext=plaintext.encode('utf-8'),
        )
        return base64.b64encode(resp['CiphertextBlob']).decode('utf-8')
    except ClientError as e:
        logger.error(f"KMS encrypt failed: {e}")
        raise


def decrypt_pii(ciphertext_b64: str) -> str:
    """Decrypt a base64-encoded KMS ciphertext back to plaintext."""
    try:
        resp = _kms_client().decrypt(
            CiphertextBlob=base64.b64decode(ciphertext_b64))
        return resp['Plaintext'].decode('utf-8')
    except ClientError as e:
        logger.error(f"KMS decrypt failed: {e}")
        raise


# ── Tenant isolation ──────────────────────────────────────────────────────────
def build_tenant_key(tenant_id: str, entity: str, entity_id: str) -> str:
    """Build a composite DynamoDB partition key that embeds tenant isolation."""
    return f"{tenant_id}#{entity}#{entity_id}"


def verify_tenant_access(tenant_id: str, resource: dict) -> None:
    """Raise ValueError if resource doesn't belong to tenant (defense in depth)."""
    if resource.get('tenant_id') != tenant_id:
        logger.error(f"SECURITY ALERT: Tenant isolation violation — "
                     f"expected {tenant_id}, got {resource.get('tenant_id')}")
        raise ValueError("Access denied — tenant isolation violation")


# ── Data residency routing ────────────────────────────────────────────────────
REGION_MAPPING = {
    'EU':   'eu-west-1',
    'UK':   'eu-west-2',
    'US':   'us-east-1',
    'APAC': 'ap-southeast-1',
}

def get_region_for_customer(customer_location: str) -> str:
    return REGION_MAPPING.get(customer_location.upper(), 'us-east-1')
