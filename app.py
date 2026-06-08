"""
CDK app entry point.

Deploy to a specific environment:
  cdk deploy --context environment=dev
  cdk deploy --context environment=staging
  cdk deploy --context environment=prod

Defaults to 'dev' if no context provided.
"""
import json, os
import aws_cdk as cdk
from product_api.product_api_stack import ProductApiStack

app = cdk.App()

# ── Read environment from CDK context ─────────────────────────────────────────
env_name   = app.node.try_get_context('environment') or 'dev'
param_file = os.path.join(os.path.dirname(__file__), 'parameters', f'{env_name}.json')

if not os.path.exists(param_file):
    raise FileNotFoundError(
        f"Parameter file not found: {param_file}. "
        f"Valid environments: dev, staging, prod")

with open(param_file) as f:
    config = json.load(f)

print(f"Deploying environment: {env_name}")
print(f"Config: {json.dumps(config, indent=2)}")

ProductApiStack(app, f"ProductApiStack-{env_name}",
    env_config=config,
    env=cdk.Environment(
        account=os.getenv('CDK_DEFAULT_ACCOUNT'),
        region=os.getenv('CDK_DEFAULT_REGION', 'us-east-1'),
    ))

app.synth()
