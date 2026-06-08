import os, logging, traceback
import boto3
from datetime import datetime
import products_db

logger    = logging.getLogger(__name__)
s3_client = boto3.client('s3')

def handler(event, context):
    for record in event.get('Records', []):
        bucket_name = record['s3']['bucket']['name']
        object_key  = record['s3']['object']['key']
        try:
            parts      = object_key.split('/')
            product_id = parts[1] if len(parts) >= 3 else None
            if not product_id:
                logger.warning(f"Could not extract product ID from key: {object_key}")
                continue
            meta      = s3_client.head_object(Bucket=bucket_name, Key=object_key)
            file_size = meta['ContentLength']
            region    = os.environ.get('AWS_REGION', 'us-east-1')
            image_url = f"https://{bucket_name}.s3.{region}.amazonaws.com/{object_key}"
            products_db.add_image_url(product_id, image_url, file_size)
            logger.info(f"Updated image metadata for product {product_id}")
        except Exception as e:
            logger.error(f"Error processing {object_key}: {str(e)}")
            traceback.print_exc()
    return {'statusCode': 200, 'body': 'Image metadata processed'}
