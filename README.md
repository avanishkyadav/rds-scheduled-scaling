
# Scheduled Scaling of RDS

Currently, AWS doesn't provide any autoscaling capability for RDS instances except for RDS Aurora. But Scheduled scaling can be implemented for RDS using Amazon EventBridge and AWS Lambda. This solutions have two stacks one for vertical scaling and other for horizontal scaling and these can be deployed independently. 

### Vertical Scaling 
Scheduled vertical scaling changes the RDS instance type, provisioned iops, storage etc. 

### Horizontal Scaling 
Scheduled horizontal scaling adds or removes the read replicas associated with RDS instances.

## Architecture
![Architecture Diagram](architecture/rds-scheduled-scaling.png)

### How It Works
Each of these stacks creates two separate Amazon EventBridge rules. One triggers lambda to scale-up the resources and other triggers lambda to scale it down.

1. A scheduled EventBridge rule triggers lambda.
2. Lambda then scans each RDS instances one by one and checks for the tag `SCHEDULED_SCALING`:`ENABLED`. If this tag is found then lambda looks for tags `SCALE_DOWN_INSTANCE_CLASS`,`SCALE_UP_INSTANCE_CLASS` for vertical-scaling and `SCALE_IN_REPLICA_COUNT`,`SCALE_OUT_REPLICA_COUNT` for horizontal-scaling.
3. Lambda then make API calls to modify instances, create or delete read replica depending on which EventBridge rule is triggered and type of scaling happening.
4. SNS notification is sent containing the summary of scaling operation.

| Tag Key | Tag Value |
| ----------- | ----------- |
| SCHEDULED_SCALING |	ENABLED |
| SCALE_UP_INSTANCE_CLASS | db.t3.xlarge |
| SCALE_DOWN_INSTANCE_CLASS | db.t3.large |
| SCALE_OUT_REPLICA_COUNT | 3 |
| SCALE_IN_REPLICA_COUNT | 1 |


## Installation
This solution can be build either by deploying cdk stack from your environment or by using cloudformation stack already synthesized.

### CDK Stack
To build the solution using cdk stack

Clone this repository to your local machine

```
$ git clone https://github.com/avanishkyadav/rds-scheduled-scaling.git
```
   
Install cdk if you don’t have it already installed

```
$ npm install -g aws-cdk
```

If this is first time you are using cdk then, run cdk bootstrap

```
$ cdk bootstrap
```

Make sure you in root directory

```
$ cd rds-scheduled-scaling
```
   
Activate virtual environment

```
$ source .venv/bin/activate
```

Install any dependencies

```
$ pip install -r requirements.txt
```

List stacks. This will list out the stacks present in the project. In this case the stacks will be `rds-scheduled-horizontal-scaling` and `rds-scheduled-vertical-scaling`.

```
$ cdk ls
```