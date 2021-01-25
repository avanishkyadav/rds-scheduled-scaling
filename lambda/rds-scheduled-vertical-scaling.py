import boto3
import botocore
import os
import json
from queue import Queue
import time

sns_enabled = os.getenv('ENABLE_SNS').lower()
sns_arn = os.getenv('SNS_ARN')

def lambda_handler(event, context):
   strtime = time.time()
   sns_notification_message = ''
   rule_name = event['resources'][0].split('/')[1]
   print('Lambda triggred for ' + rule_name)
   sns_notification_message += '\n Scheduled Scaling Event Triggred - ' + rule_name
   rds = boto3.client('rds')
   sns=boto3.client('sns')

   #Creating a queue to store rds instance list which are in unavailable state initially.
   q = Queue()
   response = rds.describe_db_instances()
   for instance in response['DBInstances']:
      print('================================================================================================================================')   
      print('Checking if Scheduled Scaling enabled on - '+ instance['DBInstanceIdentifier'])
      taglist = rds.list_tags_for_resource(
         ResourceName=instance['DBInstanceArn']
      )['TagList']
      tags={}
      for tag in taglist:
         tags[tag['Key']]=tag['Value']
      if tags.get('SCHEDULED_SCALING')=='ENABLED':
         sns_notification_message += '\n================================================================================================================================'
         sns_notification_message += '\n Scaling enabled on database: '+ instance['DBInstanceIdentifier'] 
         print('Scaling enabled on '+ instance['DBInstanceIdentifier'])
         print('Checking Scale Down and Scale Up Instance Types')
         target_instance_class=''
         scale_down_instance_class=''
         scale_up_instance_class=''
         scale_down_instance_class = tags.get('SCALE_DOWN_INSTANCE_CLASS')
         scale_up_instance_class = tags.get('SCALE_UP_INSTANCE_CLASS')
         if rule_name=='rds-scheduled-scale-up-rule':
            target_instance_class = scale_up_instance_class
         else:
            target_instance_class = scale_down_instance_class
         
         print('Target Instance Class')
         print(target_instance_class)
         print('Scale Down Instance Class')
         print(scale_down_instance_class)
         print('Scale Up Instance Class')
         print(scale_up_instance_class)
         
         if class_validity(target_instance_class):
            if instance['DBInstanceStatus'] in 'modifying/configuring-enhanced-monitoring':
               print("Currently database is not in available state. Skipping '"+instance['DBInstanceIdentifier']+"' for now and adding it to queue.")
               sns_notification_message += "\nCurrently database is not in available state.Skipping '"+instance['DBInstanceIdentifier']+"' for now and adding it to queue."
               q.put(
                  {
                     'db':instance['DBInstanceIdentifier'],
                     'target_class':target_instance_class
                  }   
               )
               continue   
            try:
               print('Starting scheduled scaling of - '+ instance['DBInstanceIdentifier'])
               sns_notification_message += '\n Triggering scaling of - '+ instance['DBInstanceIdentifier'] + ' to ' + target_instance_class
               response = rds.modify_db_instance(
                  DBInstanceIdentifier=instance['DBInstanceIdentifier'],
                  DBInstanceClass=target_instance_class,
                  ApplyImmediately=True
               )
               print('Scaling triggred.')
               sns_notification_message +=  '\n Scaling of RDS instance ' + instance['DBInstanceIdentifier'] + ' triggred successfully.'
                 
            except botocore.exceptions.ClientError as e:
               if e.response['Error']['Code']=='InvalidParameterValue':
                  print('Invalid class type. Skipping...')
                  sns_notification_message += '\n ERROR OCCURED :: Invalid class type for dbinstance '+ instance['DBInstanceIdentifier'] + ' database.'
               else:
                  print('ERROR OCCURED :: ' + e.response['Error']['Message'])
                  sns_notification_message += '\n ERROR OCCURED :: ' + e.response['Error']['Message']
         else:
            print('Target class type is an invalid class type for database - '+instance['DBInstanceIdentifier'])
            sns_notification_message += '\n ' + target_instance_class + ' is an invalid class type for database - '+instance['DBInstanceIdentifier']
         
      else:
         print('Scheduled scaling not enabled for DB Instance - '+instance['DBInstanceIdentifier'])
   
   if q.qsize()!=0:
      print('================================================================================================================================')   
      sns_notification_message += '\n================================================================================================================================'
      print('Scaling databases in queue...')
      sns_notification_message += '\nScaling databases in queue...'
   while int(time.time()-strtime)<=750 and q.qsize()!=0 :
      time.sleep(30)
      print(q.qsize())
      db = q.get()
      instance = rds.describe_db_instances(DBInstanceIdentifier=db['db'])['DBInstances'][0]
      if instance['DBInstanceStatus']=='available':
         try:
            print('Starting scheduled scaling of - '+ instance['DBInstanceIdentifier'])
            sns_notification_message += '\n Triggering scaling of - '+ instance['DBInstanceIdentifier'] + ' to ' + target_instance_class
            response = rds.modify_db_instance(
               DBInstanceIdentifier=instance['DBInstanceIdentifier'],
               DBInstanceClass=target_instance_class,
               ApplyImmediately=True
            )
            print('Scaling triggred.')
            sns_notification_message +  '\n Scaling of RDS instance ' + instance['DBInstanceIdentifier'] + ' triggred successfully.'
              
         except botocore.exceptions.ClientError as e:
            if e.response['Error']['Code']=='InvalidParameterValue':
               print('Invalid class type. Skipping...')
               sns_notification_message += '\n ERROR OCCURED :: Invalid class type for dbinstance '+ instance['DBInstanceIdentifier'] + ' database.'
            else:
               print('ERROR OCCURED :: ' + e.response['Error']['Message'])
               sns_notification_message += '\n ERROR OCCURED :: ' + e.response['Error']['Message']
         print('================================================================================================================================')   
         sns_notification_message += '\n================================================================================================================================'
      elif instance['DBInstanceStatus'] in 'modifying/configuring-enhanced-monitoring':
         q.put(db)
         
   if q.qsize()!=0:
      print('Failed to scale following databases:')
      sns_notification_message += "\nFailed to scale following databases:"
      l = []
      while q.qsize() > 0:
        l.append(q.get())
      print(l)
      sns_notification_message += "\n" + l
      
   sns_notification_message += "\nScaling operation completed!"   
   print("Scaling operation completed!")
         
   if sns_enabled=='yes':
      sns.publish(
         TopicArn=sns_arn,
         Message= sns_notification_message
      )
         
def class_validity(_class):
   if _class == None:
      return False
   _class_p = _class.split('.')
   if len(_class_p)!=3:
      return False
   if _class_p[0]!='db':
      return False
   if _class_p[2] not in ['small','micro','medium','large','xlarge','2xlarge','4xlarge','8xlarge','10xlarge','12xlarge','16xlarge','24xlarge','32xlarge']:
      return False
   if _class_p[1] not in ['t2','t3','m2','r3','r4','r5','r5b','r6g','x1','x1e','z1d','m1','m3','m4','m5','m6g']:
      return False
   print('Returning true as ['+ _class +'] a valid instance class')
   return True