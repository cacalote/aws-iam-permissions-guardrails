import logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

import argparse

import boto3
from botocore.waiter import SingleWaiterConfig, Waiter

excluded_regions=[]
parser = argparse.ArgumentParser()
parser.add_argument("--excluded_regions","-excluded_regions",help="Regions to exclude as comma separated list, such as those not activate by your organization and unable to deploy",required=False)
args = parser.parse_args()
logger.info(f"args {args}")

if args.excluded_regions:
  logger.info(f"Excluded regions are: {args.excluded_regions}")
  excluded_regions=args.excluded_regions.split(",")

waiter_config = SingleWaiterConfig({
  'delay': 10,
  'operation': 'DescribeStackSetOperation',
  'maxAttempts': 360,
  'acceptors': [
    {
      'argument': 'StackSetOperation.Status',
      'expected': 'SUCCEEDED',
      'matcher': 'path',
      'state': 'success'
    },
    {
      'argument': 'StackSetOperation.Status',
      'expected': 'FAILED',
      'matcher': 'path',
      'state': 'failure'
    },
    {
      'argument': 'StackSetOperation.Status',
      'expected': 'STOPPED',
      'matcher': 'path',
      'state': 'failure'
    },
    {
      'expected': 'ValidationError',
      'matcher': 'error',
      'state': 'failure'
    }
  ]
})

cloudformation_client=boto3.client("cloudformation")

cfn=None
with open('account-analyzer.yaml', 'r') as myfile:
  cfn = myfile.read()

StackSetName="access-analyzer-account"

response=cloudformation_client.create_stack_set(
  StackSetName=StackSetName,
  Description="Access Analyzer Account",
  TemplateBody=cfn,
  Capabilities=["CAPABILITY_IAM","CAPABILITY_NAMED_IAM"],
  PermissionModel='SERVICE_MANAGED',
  #AdministrationRoleARN='AWSControlTowerStackSetRole',
  #ExecutionRoleName='AWSControlTowerExecution',
  AutoDeployment={
    'Enabled':True,
    'RetainStacksOnAccountRemoval': False
  }
)
stack_set_id=response['StackSetId']
print("Stack Set Id is {}".format((stack_set_id)))

organizations_client=boto3.client('organizations')
root_id = organizations_client.list_roots()['Roots'][0]['Id']

waiter = Waiter('StackSetOperationComplete', waiter_config, cloudformation_client.describe_stack_set_operation)

ec2_client = boto3.client('ec2')
all_regions = [region['RegionName'] for region in ec2_client.describe_regions()['Regions']]
for region in excluded_regions:
  all_regions.remove(region)

response=cloudformation_client.create_stack_instances(
  StackSetName=StackSetName,
  DeploymentTargets={
    'OrganizationalUnitIds':[root_id]
  },
  Regions=all_regions,
  OperationPreferences={
    'FailureToleranceCount': 1,
    'MaxConcurrentCount': 10
  }
)

operation_id=response['OperationId']
print("Create Stack Instances Operation Id is {}".format((operation_id)))

waiter.wait(
    StackSetName=StackSetName,
    OperationId=operation_id
)

