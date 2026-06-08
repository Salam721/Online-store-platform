from aws_cdk import (
    Stack, RemovalPolicy, Duration,
    aws_lambda as lambda_,
    aws_apigateway as apigw,
    aws_dynamodb as dynamodb,
    aws_sqs as sqs,
    aws_sns as sns,
    aws_s3 as s3,
    aws_s3_notifications as s3n,
    aws_ec2 as ec2,
    aws_elasticache as elasticache,
    aws_ssm as ssm,
    aws_iam as iam,
    aws_events as events,
    aws_events_targets as targets,
    aws_kinesisfirehose as firehose,
    aws_ecr as ecr,
    aws_ecs as ecs,
    aws_elasticloadbalancingv2 as elbv2,
)
from aws_cdk.aws_lambda_event_sources import SqsEventSource
from aws_cdk import aws_autoscaling as autoscaling
from aws_cdk import aws_cognito as cognito
from aws_cdk import aws_kms as kms
from aws_cdk import aws_appconfig as appconfig
from aws_cdk import aws_codedeploy as codedeploy
from aws_cdk import aws_logs as logs
from aws_cdk import aws_cloudfront as cf
from aws_cdk import aws_cloudfront_origins as cf_origins
from aws_cdk import aws_cloudwatch as cloudwatch
from aws_cdk import aws_secretsmanager as secretsmanager
from constructs import Construct

class ProductApiStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, env_config: dict = None, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        # ── Environment configuration ─────────────────────────────────────
        cfg = env_config or {}
        env = cfg.get('environment', 'dev')

        # Resource sizing from parameter file
        lambda_memory   = cfg.get('lambda_memory_mb',          512)
        log_retention   = cfg.get('log_retention_days',         7)
        ecs_count       = cfg.get('ecs_desired_count',          1)
        asg_min         = cfg.get('asg_min',                    1)
        asg_desired     = cfg.get('asg_desired',                1)
        asg_max         = cfg.get('asg_max',                    3)
        cache_node_type = cfg.get('cache_node_type',   'cache.t3.micro')
        cache_count     = cfg.get('cache_node_count',           1)
        ec2_type        = cfg.get('ec2_instance_type',  't3.micro')

        _dynamo_removal = RemovalPolicy.DESTROY if cfg.get('dynamo_removal_policy','DESTROY')=='DESTROY' else RemovalPolicy.RETAIN
        _s3_removal     = RemovalPolicy.DESTROY if cfg.get('s3_removal_policy',    'DESTROY')=='DESTROY' else RemovalPolicy.RETAIN

        # ── Dead-Letter Queues ────────────────────────────────────────────────
        api_dlq = sqs.Queue(self, "ProductApiDLQ",
            queue_name="product-api-dlq",
            retention_period=Duration.days(14),
            visibility_timeout=Duration.seconds(300))

        order_dlq = sqs.Queue(self, "OrderProcessingDLQ",
            queue_name="order-processing-dlq",
            retention_period=Duration.days(14),
            visibility_timeout=Duration.seconds(60))

        eventbridge_dlq = sqs.Queue(self, "EventBridgeDLQ",
            queue_name="eventbridge-failed-events-dlq",
            retention_period=Duration.days(14),
            visibility_timeout=Duration.seconds(300))

        analytics_queue = sqs.Queue(self, "AnalyticsQueue",
            queue_name="analytics-processing-queue",
            retention_period=Duration.days(4))

        order_queue = sqs.Queue(self, "OrderProcessingQueue",
            queue_name="order-processing-queue",
            visibility_timeout=Duration.seconds(300),
            retention_period=Duration.days(14),
            receive_message_wait_time=Duration.seconds(20),
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=3, queue=order_dlq))

        # ── SNS Topics ────────────────────────────────────────────────────────
        customer_topic = sns.Topic(self, "CustomerNotificationTopic",
            topic_name="customer-notifications",
            display_name="Customer Notifications")
        system_topic = sns.Topic(self, "SystemAlertTopic",
            topic_name="system-alerts", display_name="System Alerts")
        inventory_topic = sns.Topic(self, "InventoryAlertTopic",
            topic_name="inventory-alerts", display_name="Inventory Alerts")

        # ── DynamoDB Tables ───────────────────────────────────────────────────
        products_table = dynamodb.Table(self, "ProductsTable",
            table_name="Products",
            partition_key=dynamodb.Attribute(name="id", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY)
        products_table.add_global_secondary_index(
            index_name="category-index",
            partition_key=dynamodb.Attribute(name="category", type=dynamodb.AttributeType.STRING))

        orders_table = dynamodb.Table(self, "OrdersTable",
            table_name="Orders",
            partition_key=dynamodb.Attribute(name="order_id", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY)

        analytics_table = dynamodb.Table(self, "AnalyticsTable",
            table_name="AnalyticsEvents",
            partition_key=dynamodb.Attribute(name="event_id", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY)

        # ── S3 Buckets ────────────────────────────────────────────────────────
        images_bucket = s3.Bucket(self, "ProductImagesBucket",
            versioned=True, removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            block_public_access=s3.BlockPublicAccess(
                block_public_acls=True, ignore_public_acls=True,
                block_public_policy=False, restrict_public_buckets=False),
            lifecycle_rules=[s3.LifecycleRule(
                id="ProductImageLifecycle", prefix="products/",
                transitions=[
                    s3.Transition(storage_class=s3.StorageClass.INFREQUENT_ACCESS,
                                  transition_after=Duration.days(30)),
                    s3.Transition(storage_class=s3.StorageClass.GLACIER,
                                  transition_after=Duration.days(90))],
                expiration=Duration.days(2555))])

        activity_bucket = s3.Bucket(self, "CustomerActivityBucket",
            removal_policy=RemovalPolicy.DESTROY, auto_delete_objects=True,
            lifecycle_rules=[s3.LifecycleRule(
                id="ActivityDataLifecycle", prefix="customer-activity/",
                transitions=[
                    s3.Transition(storage_class=s3.StorageClass.INFREQUENT_ACCESS,
                                  transition_after=Duration.days(30)),
                    s3.Transition(storage_class=s3.StorageClass.GLACIER,
                                  transition_after=Duration.days(90))],
                expiration=Duration.days(365))])

        # ── Parameter Store ───────────────────────────────────────────────────
        ssm.StringParameter(self, "ParamProductsTable",
            parameter_name=f"/store/{env}/products_table",
            string_value=products_table.table_name)
        ssm.StringParameter(self, "ParamImageBucket",
            parameter_name=f"/store/{env}/image_bucket",
            string_value=images_bucket.bucket_name)

        # ── VPC ───────────────────────────────────────────────────────────────
        vpc = ec2.Vpc(self, "ProductApiVpc", max_azs=2, nat_gateways=0)

        cache_sg = ec2.SecurityGroup(self, "CacheSecurityGroup", vpc=vpc,
            description="ElastiCache security group", allow_all_outbound=True)
        cache_sg.add_ingress_rule(ec2.Peer.ipv4(vpc.vpc_cidr_block), ec2.Port.tcp(6379))

        # Security group for ECS tasks
        ecs_sg = ec2.SecurityGroup(self, "EcsSecurityGroup", vpc=vpc,
            description="ECS recommendation engine security group",
            allow_all_outbound=True)
        ecs_sg.add_ingress_rule(ec2.Peer.ipv4(vpc.vpc_cidr_block), ec2.Port.tcp(8000))

        subnet_ids = ([s.subnet_id for s in vpc.private_subnets]
                      or [s.subnet_id for s in vpc.public_subnets])

        # ── ElastiCache ───────────────────────────────────────────────────────
        subnet_group = elasticache.CfnSubnetGroup(self, "CacheSubnetGroup",
            description="ElastiCache subnet group", subnet_ids=subnet_ids)
        cache_cluster = elasticache.CfnCacheCluster(self, "ProductCacheCluster",
            cache_node_type="cache.t3.micro", engine="redis", num_cache_nodes=1,
            cache_subnet_group_name=subnet_group.ref,
            vpc_security_group_ids=[cache_sg.security_group_id])


        # ── EventBridge Buses ─────────────────────────────────────────────────
        order_bus     = events.EventBus(self, "OrderEventBus",     event_bus_name="online-store-orders")
        inventory_bus = events.EventBus(self, "InventoryEventBus", event_bus_name="online-store-inventory")
        customer_bus  = events.EventBus(self, "CustomerEventBus",  event_bus_name="online-store-customers")  # noqa: F841

        # ── ECR Repository ────────────────────────────────────────────────────
        recommendation_repo = ecr.Repository(self, "RecommendationEngineRepo",
            repository_name="store-recommendations",
            removal_policy=RemovalPolicy.DESTROY,
            empty_on_delete=True,
            lifecycle_rules=[
                ecr.LifecycleRule(
                    description="Remove untagged images after 1 day",
                    tag_status=ecr.TagStatus.UNTAGGED,
                    max_image_age=Duration.days(1)),
                ecr.LifecycleRule(
                    description="Keep only 10 most recent tagged images",
                    tag_status=ecr.TagStatus.TAGGED,
                    tag_prefix_list=["latest", "prod", "v"],
                    max_image_count=10),
            ])

        # ── ECS Cluster ───────────────────────────────────────────────────────
        ecs_cluster = ecs.Cluster(self, "StoreEcsCluster",
            cluster_name="store-cluster",
            vpc=vpc)

        # ── ECS Task Execution Role ───────────────────────────────────────────
        task_execution_role = iam.Role(self, "EcsTaskExecutionRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AmazonECSTaskExecutionRolePolicy")])

        # ── ECS Task Role (app permissions) ───────────────────────────────────
        task_role = iam.Role(self, "EcsTaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"))
        products_table.grant_read_data(task_role)

        # ── Fargate Task Definition ───────────────────────────────────────────
        task_definition = ecs.FargateTaskDefinition(self, "RecommendationTaskDef",
            family="recommendation-engine-task",
            cpu=512,
            memory_limit_mib=1024,
            execution_role=task_execution_role,
            task_role=task_role)

        task_definition.add_container("RecommendationContainer",
            container_name="recommendation-engine",
            # Image will be pushed separately; using ECR placeholder URI
            image=ecs.ContainerImage.from_ecr_repository(
                recommendation_repo, tag="latest"),
            port_mappings=[ecs.PortMapping(container_port=8000, protocol=ecs.Protocol.TCP)],
            environment={
                "PRODUCTS_TABLE": products_table.table_name,
                "AWS_REGION":     self.region,
                "PORT":           "8000",
            },
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="ecs",
                log_retention=ecs.LogDrivers.aws_logs.__self__  # placeholder
            ) if False else ecs.LogDrivers.aws_logs(stream_prefix="recommendation-engine"),
            health_check=ecs.HealthCheck(
                command=["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"],
                interval=Duration.seconds(30),
                timeout=Duration.seconds(5),
                retries=3,
                start_period=Duration.seconds(60)))

        # ── Application Load Balancer ─────────────────────────────────────────
        alb = elbv2.ApplicationLoadBalancer(self, "RecommendationAlb",
            vpc=vpc,
            internet_facing=True,
            load_balancer_name="recommendation-alb")

        # Target group with health check
        target_group = elbv2.ApplicationTargetGroup(self, "RecommendationTargetGroup",
            vpc=vpc,
            port=8000,
            protocol=elbv2.ApplicationProtocol.HTTP,
            target_type=elbv2.TargetType.IP,
            health_check=elbv2.HealthCheck(
                path="/health",
                healthy_http_codes="200",
                interval=Duration.seconds(30),
                timeout=Duration.seconds(5),
                healthy_threshold_count=2,
                unhealthy_threshold_count=3))

        # ALB listener
        alb.add_listener("RecommendationListener",
            port=80,
            default_target_groups=[target_group])

        # ── ECS Fargate Service ───────────────────────────────────────────────
        '''ecs_service = ecs.FargateService(self, "RecommendationService",
            cluster=ecs_cluster,
            task_definition=task_definition,
            service_name="recommendation-service",
            desired_count=2,
            assign_public_ip=True,
            security_groups=[ecs_sg],
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PUBLIC))

        ecs_service.attach_to_application_target_group(target_group)'''

        # ── Lambda Layer ──────────────────────────────────────────────────────
        product_utils_layer = lambda_.LayerVersion(self, "ProductUtilsLayer",
            code=lambda_.Code.from_asset("layers/product_utils"),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_12],
            description="v3.0.0 - Shared utilities")

        runtime = lambda_.Runtime.PYTHON_3_12
        code    = lambda_.Code.from_asset("lambda_code")
        layers  = [product_utils_layer]

        # ── Firehose transformer ──────────────────────────────────────────────
        transformer_fn = lambda_.Function(self, "FirehoseTransformer",
            runtime=runtime, handler="firehose_transformer.handler",
            code=code, layers=layers,
            environment={"APP_ENV": env},
            timeout=Duration.minutes(5))

        firehose_role = iam.Role(self, "FirehoseDeliveryRole",
            assumed_by=iam.ServicePrincipal("firehose.amazonaws.com"))
        activity_bucket.grant_read_write(firehose_role)
        transformer_fn.grant_invoke(firehose_role)

        activity_stream = firehose.CfnDeliveryStream(
            self, "CustomerActivityStream",
            delivery_stream_name="customer-activity-stream",
            delivery_stream_type="DirectPut",
            extended_s3_destination_configuration=firehose.CfnDeliveryStream
                .ExtendedS3DestinationConfigurationProperty(
                role_arn=firehose_role.role_arn,
                bucket_arn=activity_bucket.bucket_arn,
                prefix="customer-activity/year=!{timestamp:yyyy}/month=!{timestamp:MM}/day=!{timestamp:dd}/hour=!{timestamp:HH}/",
                error_output_prefix="customer-activity-errors/!{firehose:error-output-type}/year=!{timestamp:yyyy}/month=!{timestamp:MM}/",
                buffering_hints=firehose.CfnDeliveryStream.BufferingHintsProperty(
                    size_in_m_bs=1, interval_in_seconds=60),
                compression_format="GZIP",
                processing_configuration=firehose.CfnDeliveryStream
                    .ProcessingConfigurationProperty(
                    enabled=True,
                    processors=[firehose.CfnDeliveryStream.ProcessorProperty(
                        type="Lambda",
                        parameters=[firehose.CfnDeliveryStream.ProcessorParameterProperty(
                            parameter_name="LambdaArn",
                            parameter_value=transformer_fn.function_arn)])])))

        # ── Common Lambda env ─────────────────────────────────────────────────
        common_env = {
            "APP_ENV":                      env,
            "PRODUCTS_TABLE":               products_table.table_name,
            "ORDERS_TABLE":                 orders_table.table_name,
            "ANALYTICS_TABLE":              analytics_table.table_name,
            "PRODUCT_IMAGE_BUCKET":         images_bucket.bucket_name,
            "CACHE_ENDPOINT":               cache_cluster.attr_redis_endpoint_address,
            "CACHE_PORT":                   "6379",
            "ORDER_QUEUE_URL":              order_queue.queue_url,
            "CUSTOMER_NOTIFICATION_TOPIC":  customer_topic.topic_arn,
            "SYSTEM_ALERT_TOPIC":           system_topic.topic_arn,
            "INVENTORY_ALERT_TOPIC":        inventory_topic.topic_arn,
            "ORDER_EVENT_BUS":              order_bus.event_bus_name,
            "INVENTORY_EVENT_BUS":          inventory_bus.event_bus_name,
            "ACTIVITY_STREAM_NAME":         "customer-activity-stream",
            "CLOUDFRONT_DISTRIBUTION_ID":    "",
            "CUSTOMERS_TABLE":           "Customers",
            "PAYMENT_SECRET_NAME":       "prod/payment/api-key",
            "RECOMMENDATION_SERVICE_URL":   f"http://{alb.load_balancer_dns_name}",
        }

        ssm_policy = iam.PolicyStatement(
            actions=["ssm:GetParameter", "ssm:GetParameters"],
            resources=[f"arn:aws:ssm:{self.region}:{self.account}:parameter/store/{env}/*"])

        appconfig_policy = iam.PolicyStatement(
            actions=["appconfig:GetConfiguration","appconfig:StartConfigurationSession"],
            resources=["*"])

        firehose_policy = iam.PolicyStatement(
            actions=["firehose:PutRecord", "firehose:PutRecordBatch"],
            resources=[activity_stream.attr_arn])

        def make_fn(cid, handler_name, read_write=False, needs_s3=False,
                    in_vpc=False, extra_tables=None, needs_firehose=False):
            fn = lambda_.Function(self, cid,
                runtime=runtime, handler=handler_name, code=code, layers=layers,
                environment=common_env, retry_attempts=2,
                tracing=lambda_.Tracing.ACTIVE,
                vpc=vpc if in_vpc else None,
                security_groups=[cache_sg] if in_vpc else None)
            fn.add_to_role_policy(ssm_policy)
            fn.add_to_role_policy(appconfig_policy)
            fn.add_to_role_policy(iam.PolicyStatement(
                actions=["xray:PutTraceSegments","xray:PutTelemetryRecords"],
                resources=["*"]))
            if read_write:
                products_table.grant_read_write_data(fn)
            else:
                products_table.grant_read_data(fn)
            if needs_s3:
                images_bucket.grant_read_write(fn)
            if needs_firehose:
                fn.add_to_role_policy(firehose_policy)
            if extra_tables:
                for tbl, rw in extra_tables:
                    if rw: tbl.grant_read_write_data(fn)
                    else:  tbl.grant_read_data(fn)
            return fn

        # ── Lambda functions ──────────────────────────────────────────────────
        get_product_fn    = make_fn("GetProduct",    "get_product.handler",    in_vpc=True)
        query_products_fn = make_fn("QueryProducts", "query_products.handler", in_vpc=True)
        insert_product_fn = make_fn("InsertProduct", "insert_product.handler", read_write=True, in_vpc=True)
        update_product_fn = make_fn("UpdateProduct", "update_product.handler", read_write=True, in_vpc=True)
        upload_url_fn     = make_fn("GetUploadUrl",  "get_upload_url.handler", needs_s3=True)
        download_url_fn   = make_fn("GetDownloadUrl","get_download_url.handler",needs_s3=True)
        process_image_fn  = make_fn("ProcessImage",  "process_image.handler",  read_write=True, needs_s3=True)
        track_activity_fn = make_fn("TrackActivity", "track_activity.handler", needs_firehose=True)
        place_order_fn    = make_fn("PlaceOrder",    "place_order.handler",    extra_tables=[(orders_table, True)])
        order_processor_fn= make_fn("OrderProcessor","order_processor.handler",extra_tables=[(orders_table, True)])
        inventory_processor_fn = make_fn("InventoryProcessor", "inventory_processor.handler",
            read_write=True, extra_tables=[(orders_table, False)])
        notification_processor_fn = make_fn("NotificationProcessor", "notification_processor.handler")
        analytics_processor_fn    = make_fn("AnalyticsProcessor",    "analytics_processor.handler",
            extra_tables=[(analytics_table, True)])
        options_fn = lambda_.Function(self, "Options",
            runtime=runtime, handler="options.handler", code=code, layers=layers)

        # Grant topic/queue permissions
        order_queue.grant_send_messages(place_order_fn)
        order_bus.grant_put_events_to(place_order_fn)
        customer_topic.grant_publish(order_processor_fn)
        system_topic.grant_publish(order_processor_fn)
        inventory_bus.grant_put_events_to(inventory_processor_fn)
        for fn in [notification_processor_fn]:
            customer_topic.grant_publish(fn)
            inventory_topic.grant_publish(fn)
            system_topic.grant_publish(fn)

        # ── SQS event sources ─────────────────────────────────────────────────
        order_processor_fn.add_event_source(
            SqsEventSource(order_queue, batch_size=10,
                max_batching_window=Duration.seconds(5)))
        analytics_processor_fn.add_event_source(
            SqsEventSource(analytics_queue, batch_size=10))

        # ── S3 trigger ────────────────────────────────────────────────────────
        images_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(process_image_fn),
            s3.NotificationKeyFilter(prefix="products/", suffix=".jpg"))

        # ── EventBridge rules ─────────────────────────────────────────────────
        events.Rule(self, "OrderInventoryRule",
            event_bus=order_bus,
            event_pattern=events.EventPattern(
                source=["store.orders"], detail_type=["Order Placed"]),
            targets=[targets.LambdaFunction(inventory_processor_fn,
                dead_letter_queue=eventbridge_dlq, retry_attempts=3)])

        events.Rule(self, "OrderNotificationRule",
            event_bus=order_bus,
            event_pattern=events.EventPattern(
                source=["store.orders"],
                detail_type=["Order Placed", "Order Shipped", "Order Delivered"]),
            targets=[targets.LambdaFunction(notification_processor_fn,
                dead_letter_queue=eventbridge_dlq, retry_attempts=3)])

        events.Rule(self, "AnalyticsRule",
            event_bus=order_bus,
            event_pattern=events.EventPattern(
                source=["store.orders", "store.inventory", "store.customers"]),
            targets=[targets.SqsQueue(analytics_queue)])

        events.Rule(self, "LowStockNotificationRule",
            event_bus=inventory_bus,
            event_pattern=events.EventPattern(
                source=["store.inventory"], detail_type=["Stock Low"]),
            targets=[targets.LambdaFunction(notification_processor_fn,
                dead_letter_queue=eventbridge_dlq, retry_attempts=2)])


        # ── EC2: IAM Role ─────────────────────────────────────────────────────
        ec2_role = iam.Role(self, "Ec2InstanceRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonSSMManagedInstanceCore"),  # Session Manager access
            ])
        products_table.grant_read_write_data(ec2_role)
        ec2_role.add_to_policy(iam.PolicyStatement(
            actions=["cloudwatch:PutMetricData", "logs:CreateLogGroup",
                     "logs:CreateLogStream", "logs:PutLogEvents"],
            resources=["*"]))

        # ── EC2: Security Group ───────────────────────────────────────────────
        ec2_sg = ec2.SecurityGroup(self, "Ec2ApiSecurityGroup", vpc=vpc,
            description="EC2 inventory API security group",
            allow_all_outbound=True)
        # HTTP from ALB only — no direct public SSH
        ec2_sg.add_ingress_rule(ec2.Peer.ipv4(vpc.vpc_cidr_block), ec2.Port.tcp(5000),
            "Allow HTTP from within VPC (ALB)")
        # SSH restricted to VPC CIDR (use Session Manager for production)
        ec2_sg.add_ingress_rule(ec2.Peer.ipv4(vpc.vpc_cidr_block), ec2.Port.tcp(22),
            "SSH from VPC only")

        # ── EC2: User Data ────────────────────────────────────────────────────
        user_data = ec2.UserData.for_linux()
        user_data.add_commands(
            "yum update -y",
            "yum install -y python3 python3-pip git",
            "mkdir -p /home/ec2-user/app",
            "chown ec2-user:ec2-user /home/ec2-user/app",
            "cd /home/ec2-user && python3 -m venv venv",
            "chown -R ec2-user:ec2-user /home/ec2-user/venv",
            "/home/ec2-user/venv/bin/pip install flask gunicorn boto3",
        )

        # ── EC2: Launch Template ──────────────────────────────────────────────
        launch_template = ec2.LaunchTemplate(self, "Ec2LaunchTemplate",
            instance_type=ec2.InstanceType("t3.small"),
            machine_image=ec2.MachineImage.latest_amazon_linux2023(),
            security_group=ec2_sg,
            role=ec2_role,
            user_data=user_data,
            launch_template_name="inventory-api-template")

        # ── EC2: ALB ──────────────────────────────────────────────────────────
        ec2_alb_sg = ec2.SecurityGroup(self, "Ec2AlbSecurityGroup", vpc=vpc,
            description="EC2 ALB security group", allow_all_outbound=True)
        ec2_alb_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(80),
            "Allow HTTP from internet")

        ec2_alb = elbv2.ApplicationLoadBalancer(self, "Ec2InventoryAlb",
            vpc=vpc, internet_facing=True,
            load_balancer_name="inventory-api-alb",
            security_group=ec2_alb_sg)

        ec2_target_group = elbv2.ApplicationTargetGroup(self, "Ec2InventoryTargetGroup",
            vpc=vpc, port=5000,
            protocol=elbv2.ApplicationProtocol.HTTP,
            target_type=elbv2.TargetType.INSTANCE,
            health_check=elbv2.HealthCheck(
                path="/health",
                healthy_http_codes="200",
                interval=Duration.seconds(30),
                timeout=Duration.seconds(5),
                healthy_threshold_count=2,
                unhealthy_threshold_count=3))

        ec2_alb.add_listener("Ec2InventoryListener",
            port=80,
            default_target_groups=[ec2_target_group])

        # ── EC2: Auto Scaling Group ───────────────────────────────────────────
        asg = autoscaling.AutoScalingGroup(self, "InventoryApiAsg",
            vpc=vpc,
            launch_template=launch_template,
            min_capacity=2,
            desired_capacity=2,
            max_capacity=10,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            health_check=autoscaling.HealthCheck.elb(grace=Duration.seconds(60)))

        # Target tracking: maintain 70% average CPU utilisation
        asg.scale_on_cpu_utilization("CpuScaling",
            target_utilization_percent=70,
            cooldown=Duration.seconds(300))

        # Register ASG with ALB target group
        asg.attach_to_application_target_group(ec2_target_group)



        # ── KMS Customer Managed Key ──────────────────────────────────────────
        customer_data_key = kms.Key(self, "CustomerDataKey",
            description="Encryption key for customer PII",
            enable_key_rotation=True,
            removal_policy=RemovalPolicy.RETAIN)
        customer_data_key.add_alias("alias/customer-data")

        # ── Secrets Manager — Payment API key ─────────────────────────────────
        payment_secret = secretsmanager.Secret(self, "PaymentApiSecret",
            secret_name="prod/payment/api-key",
            description="Payment processor API key",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template='{"api_key": "sk_live_placeholder"}',
                generate_string_key="api_key",
                exclude_punctuation=True,
                password_length=32))

        # ── Secrets Manager — rotation Lambda ────────────────────────────────
        rotation_fn = lambda_.Function(self, "SecretRotationFn",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="secret_rotation.handler",
            code=lambda_.Code.from_asset("lambda_code"),
            layers=layers,
            environment=common_env)
        payment_secret.add_rotation_schedule("PaymentRotationSchedule",
            rotation_lambda=rotation_fn,
            automatically_after=Duration.days(30))
        rotation_fn.add_to_role_policy(iam.PolicyStatement(
            actions=["secretsmanager:GetSecretValue","secretsmanager:PutSecretValue",
                     "secretsmanager:UpdateSecretVersionStage","secretsmanager:DescribeSecret"],
            resources=[payment_secret.secret_arn]))

        # ── Customers table (KMS-encrypted, tenant-isolated) ─────────────────
        customers_table = dynamodb.Table(self, "CustomersTable",
            table_name="Customers",
            partition_key=dynamodb.Attribute(name="pk", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.CUSTOMER_MANAGED,
            encryption_key=customer_data_key,
            removal_policy=RemovalPolicy.DESTROY)

        # ── Cognito User Pool ─────────────────────────────────────────────────
        user_pool = cognito.UserPool(self, "StoreUserPool",
            user_pool_name="online-store-users",
            self_sign_up_enabled=True,
            auto_verify=cognito.AutoVerifiedAttrs(email=True),
            password_policy=cognito.PasswordPolicy(
                min_length=8,
                require_digits=True,
                require_lowercase=True,
                require_uppercase=True,
                require_symbols=True),
            standard_attributes=cognito.StandardAttributes(
                email=cognito.StandardAttribute(required=True, mutable=False),
                fullname=cognito.StandardAttribute(required=True, mutable=True)),
            removal_policy=RemovalPolicy.DESTROY)

        # Admin group
        cognito.CfnUserPoolGroup(self, "AdminsGroup",
            user_pool_id=user_pool.user_pool_id,
            group_name="Admins",
            description="Store administrators")

        # App client
        user_pool_client = user_pool.add_client("StoreAppClient",
            auth_flows=cognito.AuthFlow(
                user_password=True, user_srp=True),
            prevent_user_existence_errors=True,
            access_token_validity=Duration.hours(1),
            id_token_validity=Duration.hours(1),
            refresh_token_validity=Duration.days(30))
        
# Add Cognito vars to env after user pool is created
        common_env["COGNITO_USER_POOL_ID"]  = user_pool.user_pool_id
        common_env["COGNITO_CLIENT_ID"]     = user_pool_client.user_pool_client_id
        common_env["USER_PROFILES_TABLE"]   = "UserProfiles"


        # User Profiles table
        user_profiles_table = dynamodb.Table(self, "UserProfilesTable",
            table_name="UserProfiles",
            partition_key=dynamodb.Attribute(
                name="userId", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY)

        # Cognito Authorizer for API Gateway
        cognito_authorizer = apigw.CognitoUserPoolsAuthorizer(
            self, "CognitoAuthorizer",
            cognito_user_pools=[user_pool],
            authorizer_name="CognitoUserPoolAuthorizer")



        # ── Customer data Lambda ──────────────────────────────────────────────
        customer_data_fn = make_fn("CustomerData", "customer_data.handler",
            extra_tables=[(customers_table, True)])
        customer_data_key.grant_encrypt_decrypt(customer_data_fn)
        payment_secret.grant_read(customer_data_fn)


        # ── Health check Lambda ───────────────────────────────────────────────
        health_check_fn = make_fn("HealthCheck", "health_check.handler")

        # ── Auth Lambda functions ─────────────────────────────────────────
        auth_register_fn = make_fn("AuthRegister", "auth_register.handler")
        auth_login_fn    = make_fn("AuthLogin",    "auth_login.handler")

        user_profile_fn  = make_fn("UserProfile",  "user_profile.handler",
            extra_tables=[(user_profiles_table, True)])

        admin_orders_fn  = make_fn("AdminOrders",  "admin_orders.handler",
            extra_tables=[(orders_table, False)])

        # Grant Cognito access to auth functions
        auth_register_fn.add_to_role_policy(iam.PolicyStatement(
            actions=["cognito-idp:SignUp"],
            resources=[user_pool.user_pool_arn]))
        auth_login_fn.add_to_role_policy(iam.PolicyStatement(
            actions=["cognito-idp:InitiateAuth"],
            resources=[user_pool.user_pool_arn]))


        # ── AppConfig — feature flags ─────────────────────────────────────────
        appconfig_app = appconfig.CfnApplication(self, "StoreAppConfig",
            name=f"online-store-{env}",
            description=f"Online store feature flags ({env})")

        appconfig_env = appconfig.CfnEnvironment(self, "StoreAppConfigEnv",
            application_id=appconfig_app.ref,
            name=env,
            description=f"Feature flags for {env} environment")

        appconfig_profile = appconfig.CfnConfigurationProfile(self, "FeatureFlagsProfile",
            application_id=appconfig_app.ref,
            name="feature-flags",
            location_uri="hosted",
            type="AWS.AppConfig.FeatureFlags")

        # Update common_env with AppConfig identifiers
        common_env.update({
            "APPCONFIG_APP":     f"online-store-{env}",
            "APPCONFIG_ENV":     env,
            "APPCONFIG_PROFILE": "feature-flags",
        })


        # ── CloudWatch Alarms ─────────────────────────────────────────────────
        alarm_topic = None
        try:
            from aws_cdk import aws_sns as alarm_sns
            alarm_topic = alarm_sns.Topic(self, "AlarmNotificationTopic",
                topic_name=f"online-store-alarms-{env}",
                display_name=f"Online Store Alarms ({env})")
        except Exception:
            pass

        from aws_cdk import aws_cloudwatch as cw, aws_cloudwatch_actions as cwa

        # High error rate on get_product
        get_product_error_alarm = cw.Alarm(self, "GetProductErrorAlarm",
            metric=get_product_fn.metric_errors(
                period=Duration.minutes(5), statistic="Sum"),
            threshold=10,
            evaluation_periods=2,
            datapoints_to_alarm=2,
            alarm_name=f"get-product-high-errors-{env}",
            alarm_description="get_product error count > 10 in 5 min",
            treat_missing_data=cw.TreatMissingData.NOT_BREACHING)

        # High latency on order processor
        order_latency_alarm = cw.Alarm(self, "OrderProcessorLatencyAlarm",
            metric=order_processor_fn.metric_duration(
                period=Duration.minutes(5), statistic="Average"),
            threshold=10000,
            evaluation_periods=2,
            alarm_name=f"order-processor-high-latency-{env}",
            alarm_description="Order processor avg duration > 10s",
            treat_missing_data=cw.TreatMissingData.NOT_BREACHING)

        # Throttles across the API
        insert_throttle_alarm = cw.Alarm(self, "InsertProductThrottleAlarm",
            metric=insert_product_fn.metric_throttles(
                period=Duration.minutes(5), statistic="Sum"),
            threshold=5,
            evaluation_periods=1,
            alarm_name=f"insert-product-throttles-{env}",
            alarm_description="insert_product throttled > 5 times in 5 min",
            treat_missing_data=cw.TreatMissingData.NOT_BREACHING)

        # Composite alarm — alert only when multiple issues occur together
        composite_alarm = cw.CompositeAlarm(self, "ApiHealthCompositeAlarm",
            alarm_description="API health degraded — multiple alarms triggered",
            composite_alarm_name=f"api-health-composite-{env}",
            alarm_rule=cw.AlarmRule.any_of(
                get_product_error_alarm, order_latency_alarm))

        # Wire alarms to SNS if topic was created
        if alarm_topic:
            from aws_cdk import aws_cloudwatch_actions as cwa2
            for alarm in [get_product_error_alarm, order_latency_alarm,
                          insert_throttle_alarm]:
                alarm.add_alarm_action(cwa2.SnsAction(alarm_topic))

        # ── Log retention (from env config) ───────────────────────────────────
        # Lambda creates log groups automatically; set retention via custom resource
        # (CDK handles this via aws_logs.LogRetention if desired)
        # Using log_retention_days value from env config for documentation
        _ = log_retention   # referenced in common_env for future use




        # Provisioned concurrency on prod to eliminate cold starts
        if env == 'prod':
            try:
                prod_version = get_product_fn.current_version
                lambda_.Alias(self, "GetProductProdAlias2",
                    alias_name="warm",
                    version=prod_version,
                    provisioned_concurrent_executions=5)
            except Exception:
                pass  # May conflict with blue/green alias — skip

        # ── CloudFront CDN distribution ───────────────────────────────────────
        # Only create on staging/prod to save dev costs
        cf_distribution = None
        

        # ── API Gateway ───────────────────────────────────────────────────────
        api = apigw.RestApi(self, "ProductsAPI")

        products = api.root.add_resource("products")
        products.add_method("GET",     apigw.LambdaIntegration(query_products_fn))
        products.add_method("POST",    apigw.LambdaIntegration(insert_product_fn))
        products.add_method("OPTIONS", apigw.LambdaIntegration(options_fn))

        product_by_id = products.add_resource("{id}")
        product_by_id.add_method("GET",     apigw.LambdaIntegration(get_product_fn))
        product_by_id.add_method("PUT",     apigw.LambdaIntegration(update_product_fn))
        product_by_id.add_method("OPTIONS", apigw.LambdaIntegration(options_fn))

        upload_url_res = product_by_id.add_resource("upload-url")
        upload_url_res.add_method("POST",    apigw.LambdaIntegration(upload_url_fn))
        upload_url_res.add_method("OPTIONS", apigw.LambdaIntegration(options_fn))

        image_url_res = product_by_id.add_resource("image-url")
        image_url_res.add_method("GET",     apigw.LambdaIntegration(download_url_fn))
        image_url_res.add_method("OPTIONS", apigw.LambdaIntegration(options_fn))

        orders_res = api.root.add_resource("orders")
        orders_res.add_method("POST",    apigw.LambdaIntegration(place_order_fn))
        orders_res.add_method("OPTIONS", apigw.LambdaIntegration(options_fn))

        activity_res = api.root.add_resource("activity")
        activity_res.add_method("POST",    apigw.LambdaIntegration(track_activity_fn))
        activity_res.add_method("OPTIONS", apigw.LambdaIntegration(options_fn))

        # ── Auth endpoints (public) ───────────────────────────────────────────
        auth_res      = api.root.add_resource("auth")
        register_res  = auth_res.add_resource("register")
        login_res     = auth_res.add_resource("login")
        register_res.add_method("POST",    apigw.LambdaIntegration(auth_register_fn))
        register_res.add_method("OPTIONS", apigw.LambdaIntegration(options_fn))
        login_res.add_method("POST",       apigw.LambdaIntegration(auth_login_fn))
        login_res.add_method("OPTIONS",    apigw.LambdaIntegration(options_fn))

        # ── Protected user endpoints ──────────────────────────────────────────
        users_res   = api.root.add_resource("users")
        profile_res = users_res.add_resource("profile")
        profile_res.add_method("GET",
            apigw.LambdaIntegration(user_profile_fn),
            authorizer=cognito_authorizer,
            authorization_type=apigw.AuthorizationType.COGNITO)
        profile_res.add_method("PUT",
            apigw.LambdaIntegration(user_profile_fn),
            authorizer=cognito_authorizer,
            authorization_type=apigw.AuthorizationType.COGNITO)
        profile_res.add_method("OPTIONS", apigw.LambdaIntegration(options_fn))

        # ── Admin-only endpoints ──────────────────────────────────────────────
        admin_res        = api.root.add_resource("admin")
        admin_orders_res = admin_res.add_resource("orders")
        admin_orders_res.add_method("GET",
            apigw.LambdaIntegration(admin_orders_fn),
            authorizer=cognito_authorizer,
            authorization_type=apigw.AuthorizationType.COGNITO)
        admin_orders_res.add_method("OPTIONS", apigw.LambdaIntegration(options_fn))


        # ── Customer data endpoints (protected + KMS-encrypted) ──────────────
        customers_res  = api.root.add_resource("customers")
        customers_res.add_method("POST",
            apigw.LambdaIntegration(customer_data_fn),
            authorizer=cognito_authorizer,
            authorization_type=apigw.AuthorizationType.COGNITO)
        customers_res.add_method("OPTIONS", apigw.LambdaIntegration(options_fn))

        customer_by_id = customers_res.add_resource("{customerId}")
        customer_by_id.add_method("GET",
            apigw.LambdaIntegration(customer_data_fn),
            authorizer=cognito_authorizer,
            authorization_type=apigw.AuthorizationType.COGNITO)
        customer_by_id.add_method("DELETE",
            apigw.LambdaIntegration(customer_data_fn),
            authorizer=cognito_authorizer,
            authorization_type=apigw.AuthorizationType.COGNITO)
        customer_by_id.add_method("OPTIONS", apigw.LambdaIntegration(options_fn))


        # ── CodeDeploy blue/green for Lambda (prod only) ─────────────────────
        if env == 'prod':
            # Aliases — CodeDeploy shifts traffic between versions
            get_product_alias = lambda_.Alias(self, "GetProductAlias",
                alias_name="prod",
                version=get_product_fn.current_version)

            # CloudWatch alarms that trigger automatic rollback
            error_alarm = cloudwatch.Alarm(self, "GetProductDeployErrorAlarm",
                metric=get_product_fn.metric_errors(
                    period=Duration.minutes(1), statistic="Sum"),
                threshold=5,
                evaluation_periods=1,
                alarm_description="Rollback trigger: Lambda errors > 5/min")

            latency_alarm = cloudwatch.Alarm(self, "GetProductLatencyAlarm",
                metric=get_product_fn.metric_duration(
                    period=Duration.minutes(1), statistic="Average"),
                threshold=3000,
                evaluation_periods=2,
                alarm_description="Rollback trigger: p50 latency > 3s")

            # Pre/post traffic hook Lambdas
            pre_hook_fn = lambda_.Function(self, "PreTrafficHook",
                runtime=lambda_.Runtime.PYTHON_3_12,
                handler="pre_traffic_hook.handler",
                code=lambda_.Code.from_asset("pipeline/hooks"),
                environment={
                    "TARGET_FUNCTION": get_product_fn.function_name,
                    **common_env,
                })

            post_hook_fn = lambda_.Function(self, "PostTrafficHook",
                runtime=lambda_.Runtime.PYTHON_3_12,
                handler="post_traffic_hook.handler",
                code=lambda_.Code.from_asset("pipeline/hooks"),
                environment={
                    "TARGET_FUNCTION": get_product_fn.function_name,
                    **common_env,
                })
            post_hook_fn.add_to_role_policy(iam.PolicyStatement(
                actions=["cloudwatch:GetMetricStatistics"],
                resources=["*"]))

            # CodeDeploy application + deployment group
            cd_app = codedeploy.LambdaApplication(self, "StoreDeployApp",
                application_name=f"online-store-{env}")

            codedeploy.LambdaDeploymentGroup(self, "GetProductDeployGroup",
                application=cd_app,
                alias=get_product_alias,
                # Canary: 10% for 5 min, then 90%
                deployment_config=codedeploy.LambdaDeploymentConfig.CANARY_10PERCENT_5MINUTES,
                alarms=[error_alarm, latency_alarm],
                pre_hook=pre_hook_fn,
                post_hook=post_hook_fn,
                auto_rollback=codedeploy.AutoRollbackConfig(
                    failed_deployment=True,
                    stopped_deployment=True,
                    deployment_in_alarm=True))

            # Grant hook functions CodeDeploy reporting permission
            for fn in [pre_hook_fn, post_hook_fn]:
                fn.add_to_role_policy(iam.PolicyStatement(
                    actions=["codedeploy:PutLifecycleEventHookExecutionStatus"],
                    resources=["*"]))
                get_product_fn.grant_invoke(fn)



        health_res = api.root.add_resource("health")
        health_res.add_method("GET",     apigw.LambdaIntegration(health_check_fn))
        health_res.add_method("OPTIONS", apigw.LambdaIntegration(options_fn))

        if env in ('staging', 'prod'):
            try:
                # Cache policy: cache API responses 10 min
                api_cache_policy = cf.CachePolicy(self, "ApiCachePolicy",
                    cache_policy_name=f"online-store-api-cache-{env}",
                    default_ttl=Duration.seconds(600),
                    max_ttl=Duration.seconds(3600),
                    min_ttl=Duration.seconds(0),
                    comment="Cache API responses, vary on Accept-Encoding")

                cf_distribution = cf.Distribution(self, "OnlineStoreCDN",
                    default_behavior=cf.BehaviorOptions(
                        origin=cf_origins.HttpOrigin(
                            f"{api.rest_api_id}.execute-api.{self.region}.amazonaws.com",
                            origin_path=f"/{env}"),
                        cache_policy=api_cache_policy,
                        allowed_methods=cf.AllowedMethods.ALLOW_GET_HEAD_OPTIONS,
                        viewer_protocol_policy=cf.ViewerProtocolPolicy.REDIRECT_TO_HTTPS),
                    additional_behaviors={
                        # Static product images — aggressive caching
                        "/products/*/image-url": cf.BehaviorOptions(
                            origin=cf_origins.HttpOrigin(
                                f"{api.rest_api_id}.execute-api.{self.region}.amazonaws.com",
                                origin_path=f"/{env}"),
                            cache_policy=cf.CachePolicy.CACHING_OPTIMIZED),
                        # Health checks — never cache
                        "/health": cf.BehaviorOptions(
                            origin=cf_origins.HttpOrigin(
                                f"{api.rest_api_id}.execute-api.{self.region}.amazonaws.com",
                                origin_path=f"/{env}"),
                            cache_policy=cf.CachePolicy.CACHING_DISABLED),
                    },
                    price_class=cf.PriceClass.PRICE_CLASS_100,
                    comment=f"Online store CDN ({env})")

                common_env["CLOUDFRONT_DISTRIBUTION_ID"] = cf_distribution.distribution_id
            except Exception as e:
                pass  # CloudFront not available in all regions/contexts
