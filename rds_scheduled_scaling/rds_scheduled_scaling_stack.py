from aws_cdk import (
    aws_lambda as _lambda,
    aws_iam as iam,
    aws_events as event,
    aws_events_targets as targets,
    core
)


class RdsScheduledScalingStack(core.Stack):

    def __init__(self, scope: core.Construct, construct_id: str, scaling_type=False, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        up='up'
        down='down'
        
        if scaling_type=='horizontal':
            up='out'
            down='in'
        
        enable_sns = core.CfnParameter(
            self, "Enable-Notification",
            type="String",
            allowed_values=["yes","no"],
            default="no",
            description='Select "yes" if you want to be notified about scaling events.'
        )
        
        sns_arn = core.CfnParameter(
            self, "Notification-Topic-Arn",
            type="String",
            default="<sns-topic-arn>",
            description='If selected "yes". Topic arn to which notification will be sent.'
        )
        
        scale_down_time = core.CfnParameter(
            self, "Scale-" +down.capitalize()+ "-Time",
            type="String",
            description='(Required) Time at which scale-'+ down +'('+scaling_type+') will take place in the format "minute hour" (without quotes). Use UTC timezone (IST - 5:30). e.g, "0 14" equals to "2:00PM" in UTC and "17:30PM" in IST.'
        )
        
        scale_up_time = core.CfnParameter(
            self, "Scale-" +up.capitalize()+ "-Time",
            type="String",
            description='(Required) Time at which scale-'+ up +'('+scaling_type+') will take place in the format "minute hour" (without quotes). Use UTC timezone (IST - 5:30). e.g, "0 14" equals to "2:00PM" in UTC and "17:30PM" in IST.'
        )
        
        cron_expression_scale_up = core.StringConcat().join('cron(',core.StringConcat().join(scale_up_time.value_as_string,' * * ? *)'))
        cron_expression_scale_down = core.StringConcat().join('cron(',core.StringConcat().join(scale_down_time.value_as_string,' * * ? *)'))
        
        scheduled_scaling_function_policy = iam.PolicyDocument(
            statements=[
                iam.PolicyStatement(
                    sid='WriteCloudWatchLogs',
                    actions=["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
                    effect=iam.Effect.ALLOW,
                    resources=['*']
                ),
                iam.PolicyStatement(
                    sid="rdsReadInstanceAndTagging",
                    actions=["rds:ListTagsForResource","rds:DescribeDBInstances"],
                    effect=iam.Effect.ALLOW,
                    resources= ["*"]    
                ),
                iam.PolicyStatement(
                    sid="snsPublishNotification",
                    actions=["sns:Publish"],
                    effect=iam.Effect.ALLOW,
                    resources=["*"]    
                )
            ]
        )
        
        if scaling_type=='vertical':
            scheduled_scaling_function_policy.add_statements(
                iam.PolicyStatement(
                    sid="rdsmodifyDBInstance",
                    actions=["rds:ModifyDBInstance"],
                    effect=iam.Effect.ALLOW,
                    resources=["*"],
                    conditions={"StringEquals": {"aws:ResourceTag/SCHEDULED_SCALING": "ENABLED"}}
                )
            )
        else:
            scheduled_scaling_function_policy.add_statements(
                iam.PolicyStatement(
                    sid="rdscreateAndDeleteReplica",
                    actions=["rds:DeleteDBInstance","rds:CreateDBInstanceReadReplica"],
                    effect=iam.Effect.ALLOW,
                    resources=["*"],
                    conditions={"StringEquals": {"aws:ResourceTag/SCHEDULED_SCALING": "ENABLED"}}
                )
            )
        
        rds_scaling_lambda = _lambda.Function(
            self, "RDSScheduled" + scaling_type.capitalize() + "ScalingFunction",
            handler="rds-scheduled-" + scaling_type + "-scaling.lambda_handler",
            function_name="rds-scheduled-" + scaling_type + "-scaling-function",
            code=_lambda.Code.from_asset(path='lambda/'),
            runtime=_lambda.Runtime.PYTHON_3_7,
            timeout=core.Duration.seconds(900),
            memory_size=128,
            role=iam.Role(
                self, "RDS-" + scaling_type.capitalize() + "ScalingLambdaRole",
                assumed_by=iam.ServicePrincipal('lambda.amazonaws.com'),
                role_name="rds-scheduled-" + scaling_type + "-scaling-role",
                inline_policies={
                    "rds-scheduled-" + scaling_type + "-scaling-policy": scheduled_scaling_function_policy
                }
            ),
            environment={
                'ENABLE_SNS':enable_sns.value_as_string,
                'SNS_ARN':sns_arn.value_as_string
            }
        )
        
        scale_up_scheduled_event =  event.Rule(
            self,'Scale' + up.capitalize() + 'LambdaTrigger',
            rule_name='rds-scheduled-scale-' + up + '-rule',
            schedule=event.Schedule.expression(cron_expression_scale_up)
        )
        scale_up_scheduled_event.add_target(targets.LambdaFunction(rds_scaling_lambda))
        scale_down_scheduled_event =  event.Rule(
            self,'Scale' + down.capitalize() + 'LambdaTrigger',
            rule_name='rds-scheduled-scale-' + down + '-rule',
            schedule=event.Schedule.expression(cron_expression_scale_down)
        )
        scale_down_scheduled_event.add_target(targets.LambdaFunction(rds_scaling_lambda))
