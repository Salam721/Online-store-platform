import json
from decimal import Decimal
from datetime import datetime

CORS_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
}

def decimal_serializer(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

def create_success_response(status_code, data):
    return {
        "statusCode": status_code,
        "headers": CORS_HEADERS,
        "body": json.dumps(data, default=decimal_serializer),
    }

def create_error_response(status_code, message, details=None, suggestions=None):
    error = {
        "error": {
            "type": _error_type(status_code),
            "message": message,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
    }
    if details:
        error["error"]["details"] = details
    if suggestions:
        error["error"]["suggestions"] = suggestions
    return {"statusCode": status_code, "headers": CORS_HEADERS, "body": json.dumps(error)}

def _error_type(status_code):
    return {400:"bad_request",404:"not_found",409:"conflict",
            500:"internal_server_error",503:"service_unavailable"}.get(status_code,"error")
