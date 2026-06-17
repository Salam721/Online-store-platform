# Online Store Platform

A serverless e-commerce platform on AWS, defined with the **AWS CDK (Python)**, paired with a **React + TypeScript** storefront frontend.

The backend is a single CDK stack ([`product_api/product_api_stack.py`](product_api/product_api_stack.py)) that provisions the full system: API Gateway + ~30 Lambda functions, DynamoDB, S3, ElastiCache (Redis), SQS/SNS/EventBridge, Kinesis Firehose, an ECS Fargate recommendation service, an EC2 inventory API, Cognito auth, KMS, Secrets Manager, CloudWatch alarms, AppConfig feature flags, CloudFront, and CodeDeploy blue/green deployments.

## Repository layout

| Path | Description |
|------|-------------|
| `app.py` | CDK entry point — reads env config from `parameters/{env}.json` |
| `product_api/product_api_stack.py` | The entire infrastructure stack |
| `lambda_code/` | Lambda handlers (products, orders, auth, customers, processors, etc.) |
| `layers/product_utils/` | Shared Lambda layer (cache client, circuit breaker, config, schemas) |
| `containers/` | ECS Fargate recommendation-engine app |
| `ec2/` | EC2 inventory API app (Flask) |
| `parameters/` | Per-environment config (`dev`, `staging`, `prod`) + `feature_flags.json` |
| `pipeline/` | CI/CD pipeline stack and CodeDeploy traffic hooks |
| `tests/` | Unit, integration (moto), performance (locust) tests |
| `artillery.yml` | Load-test scenarios |
| `buildspec.yml` | CodeBuild build/test spec |
| `ui/` | React + Vite + Tailwind storefront frontend |
| `DEPLOY.md` | Detailed deployment, feature-flag, and performance guide |

## Architecture

**API layer** — API Gateway REST API (`ProductsAPI`) backed by Lambda:

| Route | Methods | Auth |
|-------|---------|------|
| `/products` | GET, POST | — |
| `/products/{id}` | GET, PUT | — |
| `/products/{id}/upload-url` | POST | — |
| `/products/{id}/image-url` | GET | — |
| `/orders` | POST | — |
| `/activity` | POST | — |
| `/auth/register`, `/auth/login` | POST | Public (Cognito) |
| `/users/profile` | GET, PUT | Cognito |
| `/admin/orders` | GET | Cognito |
| `/customers`, `/customers/{customerId}` | POST / GET, DELETE | Cognito |
| `/health` | GET | — |

**Data** — DynamoDB (Products, Orders, AnalyticsEvents, Customers [KMS-encrypted], UserProfiles), S3 (product images, customer activity), ElastiCache Redis.

**Async / events** — SQS queues with DLQs, SNS topics (customer/system/inventory), EventBridge buses (orders/inventory/customers) with routing rules, Kinesis Firehose → S3.

**Extra compute** — ECS Fargate recommendation service behind an ALB; EC2 Auto Scaling inventory API behind an ALB.

**Ops** — CloudWatch alarms + composite alarm, X-Ray tracing, AppConfig feature flags, Secrets Manager with rotation, CloudFront (staging/prod), CodeDeploy canary blue/green for Lambda (prod).

## Backend — setup & deploy

Prerequisites: Python 3.12, Node.js (for the CDK CLI), AWS credentials, and the AWS CDK CLI (`npm install -g aws-cdk`).

```bash
# Create and activate a virtualenv
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt   # for running tests

# Bootstrap CDK in your account/region (first time only)
cdk bootstrap

# Deploy to dev (default environment)
cdk deploy --context environment=dev

# Preview changes / deploy other environments
cdk diff   --context environment=prod
cdk deploy --context environment=staging --require-approval broadening
cdk deploy --context environment=prod    --require-approval any
```

Environments are selected via CDK context and configured in `parameters/{dev,staging,prod}.json` (Lambda memory, cache/EC2 sizing, ASG counts, log retention, removal policies). See **[DEPLOY.md](DEPLOY.md)** for feature flags, CI/CD pipeline, deployment strategies, and performance tuning.

## Tests

```bash
source .venv/bin/activate
pytest                    # all tests
pytest -m unit            # fast unit tests (mocked)
pytest -m integration     # integration tests via moto AWS mocks
```

Markers: `unit`, `integration`, `deployment` (post-deploy smoke), `performance` (locust, run separately). See [`tests/README.md`](tests/README.md).

## Frontend (`ui/`)

A Vite + React 18 + TypeScript + Tailwind storefront: catalog, product detail, cart, checkout, order confirmation, and Cognito-backed auth (register/login/email verification). State lives in `AuthContext` and `CartContext`; the typed API client is in `src/api/client.ts`.

```bash
cd ui
npm install

# Point the app at your deployed API
cp .env.example .env        # then set VITE_API_URL to your API Gateway / CloudFront URL

npm run dev                 # local dev server
npm run build               # type-check + production build to dist/
npm run preview             # preview the production build
```

The frontend reads its backend URL from the `VITE_API_URL` environment variable.
