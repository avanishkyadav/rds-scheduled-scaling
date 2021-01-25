#!/usr/bin/env python3

from aws_cdk import core

from rds_scheduled_scaling.rds_scheduled_scaling_stack import RdsScheduledScalingStack


app = core.App()
RdsScheduledScalingStack(app, "rds-scheduled-horizontal-scaling",scaling_type="horizontal")
RdsScheduledScalingStack(app, "rds-scheduled-vertical-scaling",scaling_type="vertical")

app.synth()
