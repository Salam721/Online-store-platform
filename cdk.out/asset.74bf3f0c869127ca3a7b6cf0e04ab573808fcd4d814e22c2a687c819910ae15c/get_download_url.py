import logging, traceback
import boto3
from botocore.exceptions import ClientError
from response_utils import create_success_response, create_error_response
from config import get_image_bucket

logger    = logging.getLogger(__name__)
s3_client = boto3.client('s3')

def handler(event, context):
    try:
        product_id = (event.get('pathParameters') or {}).get('id')
        if not product_id:
            return create_error_response(400, 'Product ID is required')
        params     = event.get('queryStringParameters') or {}
        image_type = params.get('type', 'main')
        bucket     = get_image_bucket()
        object_key = f"products/{product_id}/{image_type}.jpg"
        download_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket, 'Key': object_key},
            ExpiresIn=3600,
        )
        return create_success_response(200, {'download_url': download_url, 'expires_in': 3600})
    except ClientError as e:
        logger.error(f"S3 error: {str(e)}")
        return create_error_response(404, 'Image not found or inaccessible')
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        traceback.print_exc()
        return create_error_response(500, 'Internal server error')
