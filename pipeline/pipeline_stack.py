"""
CDK stack that defines the CI/CD pipeline.
Kept separate from the application stack so the pipeline can self-update.

Deploy once:
  cdk deploy PipelineStack

After that, every push to main triggers the pipeline automatically.
"""
from aws_cdk import (
    Stack, Duration, RemovalPolicy,
    aws_codepipeline as cp,
    aws_codepipeline_actions as cpa,
    aws_codebuild as cb,
    aws_codedeploy as cd,
    aws_lambda as lambda_,
    aws_cloudwatch as cw,
    aws_iam as iam,
    aws_sns as sns,
    aws_codecommit as codecommit,
)
from constructs import Construct


class PipelineStack(Stack):
    def __init__(self, scope: Construct, construct_id: str,
                 app_stack_name: str = "ProductApiStack",
                 repo_name: str = "online-store-api",
                 **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        # ── CodeCommit repository ──────────────────────────────────────────────
        repo = codecommit.Repository(self, "StoreRepo",
            repository_name=repo_name,
            description="Online store API source code")

        # ── SNS topic for approval notifications ──────────────────────────────
        approval_topic = sns.Topic(self, "ApprovalTopic",
            topic_name="pipeline-production-approval")

        # ── Artifacts ─────────────────────────────────────────────────────────
        source_output = cp.Artifact("SourceOutput")
        build_output  = cp.Artifact("BuildOutput")

        # ── Pipeline ──────────────────────────────────────────────────────────
        pipeline = cp.Pipeline(self, "OnlineStorePipeline",
            pipeline_name="online-store-api-pipeline",
            cross_account_keys=False)

        # ── Stage 1: Source ───────────────────────────────────────────────────
        source_stage = pipeline.add_stage(stage_name="Source")
        source_stage.add_action(cpa.CodeCommitSourceAction(
            action_name="CodeCommit",
            repository=repo,
            output=source_output,
            branch="main"))

        # ── Stage 2: Build + Test (dev) ───────────────────────────────────────
        dev_build = cb.PipelineProject(self, "DevBuildProject",
            project_name="online-store-build-dev",
            build_spec=cb.BuildSpec.from_source_filename("buildspec.yml"),
            environment=cb.BuildEnvironment(
                build_image=cb.LinuxBuildImage.STANDARD_7_0,
                compute_type=cb.ComputeType.MEDIUM),
            environment_variables={
                "ENVIRONMENT": cb.BuildEnvironmentVariable(value="dev"),
            })

        # Grant CDK deploy permissions
        dev_build.add_to_role_policy(iam.PolicyStatement(
            actions=["cloudformation:*", "iam:*", "lambda:*",
                     "dynamodb:*", "s3:*", "apigateway:*",
                     "cognito-idp:*", "kms:*", "secretsmanager:*",
                     "sqs:*", "sns:*", "events:*", "firehose:*",
                     "elasticache:*", "ec2:*", "ecs:*", "ecr:*",
                     "appconfig:*", "ssm:*", "logs:*"],
            resources=["*"]))

        build_stage = pipeline.add_stage(stage_name="BuildAndTest")
        build_stage.add_action(cpa.CodeBuildAction(
            action_name="BuildTestDeploy",
            project=dev_build,
            input=source_output,
            outputs=[build_output]))

        # ── Stage 3: Deploy to staging ────────────────────────────────────────
        staging_build = cb.PipelineProject(self, "StagingDeployProject",
            project_name="online-store-deploy-staging",
            build_spec=cb.BuildSpec.from_object({
                "version": "0.2",
                "phases": {
                    "install": {"commands": ["npm install -g aws-cdk",
                                             "pip install -r requirements.txt"]},
                    "build":   {"commands": [
                        "cdk deploy ProductApiStack-staging "
                        "--context environment=staging "
                        "--require-approval never"]},
                }}),
            environment=cb.BuildEnvironment(
                build_image=cb.LinuxBuildImage.STANDARD_7_0))
        staging_build.add_to_role_policy(iam.PolicyStatement(
            actions=["cloudformation:*", "iam:PassRole", "sts:AssumeRole"],
            resources=["*"]))

        staging_stage = pipeline.add_stage(stage_name="DeployStaging")
        staging_stage.add_action(cpa.CodeBuildAction(
            action_name="DeployToStaging",
            project=staging_build,
            input=source_output))

        # ── Stage 4: Manual approval ──────────────────────────────────────────
        approval_stage = pipeline.add_stage(stage_name="Approval")
        approval_stage.add_action(cpa.ManualApprovalAction(
            action_name="ProductionApproval",
            notification_topic=approval_topic,
            additional_information=(
                "Review staging test results and CloudWatch metrics "
                "before approving production deployment.")))

        # ── Stage 5: Deploy to production (blue/green via CodeDeploy) ─────────
        prod_deploy = cb.PipelineProject(self, "ProdDeployProject",
            project_name="online-store-deploy-prod",
            build_spec=cb.BuildSpec.from_object({
                "version": "0.2",
                "phases": {
                    "install": {"commands": ["npm install -g aws-cdk",
                                             "pip install -r requirements.txt"]},
                    "build":   {"commands": [
                        "cdk deploy ProductApiStack-prod "
                        "--context environment=prod "
                        "--require-approval never"]},
                }}),
            environment=cb.BuildEnvironment(
                build_image=cb.LinuxBuildImage.STANDARD_7_0))
        prod_deploy.add_to_role_policy(iam.PolicyStatement(
            actions=["cloudformation:*", "iam:PassRole", "sts:AssumeRole",
                     "codedeploy:*"],
            resources=["*"]))

        prod_stage = pipeline.add_stage(stage_name="DeployProduction")
        prod_stage.add_action(cpa.CodeBuildAction(
            action_name="DeployToProduction",
            project=prod_deploy,
            input=source_output))
