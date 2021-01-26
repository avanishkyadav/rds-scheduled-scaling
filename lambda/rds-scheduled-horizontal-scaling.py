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
   sns_notification_message += '\nScheduled Scaling Event Triggred - ' + rule_name
   rds = boto3.client('rds')
   sns=boto3.client('sns')

   #Creating a queue to store rds instance list which are in unavailable state initially.
   q = Queue()
   response = rds.describe_db_instances()
   for instance in response['DBInstances']:
      if instance.get('ReadReplicaSourceDBInstanceIdentifier') != None:
         continue
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
         sns_notification_message += '\nScaling enabled on database: '+ instance['DBInstanceIdentifier'] 
         print('Scaling enabled on '+ instance['DBInstanceIdentifier'])
         print('Checking Scale In and Scale Out Replica count')
         current_replicas = instance['ReadReplicaDBInstanceIdentifiers']
         current_replica_count=len(current_replicas)
         scale_in_replica_count=0
         scale_out_replica_count=0
         try:
            scale_in_replica_count = int(tags.get('SCALE_IN_REPLICA_COUNT'))
            scale_out_replica_count = int(tags.get('SCALE_OUT_REPLICA_COUNT'))
         except:
             print("Invalid value for tags 'SCALE_IN_REPLICA_COUNT' and 'SCALE_OUT_REPLICA_COUNT'. Must be an integer.")
             sns_notification_message += "\nInvalid value for tags 'SCALE_IN_REPLICA_COUNT' and 'SCALE_OUT_REPLICA_COUNT'. Must be an integer."
             continue
         print('Scale In Replica Count')
         print(scale_in_replica_count)
         print('Scale Out Replica Count')
         print(scale_out_replica_count)
         
         if scale_in_replica_count<0 or scale_out_replica_count>5 or scale_in_replica_count >= scale_out_replica_count:
             print("Invalid value for tags 'SCALE_IN_REPLICA_COUNT' and 'SCALE_OUT_REPLICA_COUNT'. Check to make sure following condition are met.")
             print("'SCALE_IN_REPLICA_COUNT' >= 0")
             print("'SCALE_OUT_REPLICA_COUNT' < 6")
             print("'SCALE_IN_REPLICA_COUNT' < 'SCALE_OUT_REPLICA_COUNT'")
             sns_notification_message += "\nInvalid value for tags 'SCALE_IN_REPLICA_COUNT' and 'SCALE_OUT_REPLICA_COUNT'. Check to make sure following condition are met."
             sns_notification_message += "\n'SCALE_IN_REPLICA_COUNT' >= 0"
             sns_notification_message += "\n'SCALE_OUT_REPLICA_COUNT' <= 5"
             sns_notification_message += "\n'SCALE_IN_REPLICA_COUNT' < 'SCALE_OUT_REPLICA_COUNT'"
             continue
         
         print("Current replica count - " + str(current_replica_count))
         print("Target replica count  - " + str(scale_out_replica_count))
         
         if rule_name=='rds-scheduled-scale-out-rule':
            if current_replica_count>scale_out_replica_count:
               print("Current replica count is greater than target scale-out replica count. Deleting aditional replicas.")
               sns_notification_message += "\nCurrent replica count is greater than target scale-out replica count. Deleting aditional replicas."
               while len(current_replicas)>scale_out_replica_count:
                  print("Deleting '"+ current_replicas[0]+"'...")
                  sns_notification_message += "\nDeleting '"+ current_replicas[0]+"'..."
                  try:
                     response = rds.delete_db_instance(
                        DBInstanceIdentifier=current_replicas.pop(0),
                        SkipFinalSnapshot=True
                     )
                     print("Successfully Deleted '"+ current_replicas[0]+"'.")
                     sns_notification_message += "\nSuccessfully Deleted '"+ current_replicas[0]+"'."
                  except botocore.exceptions.ClientError as e:
                     print('ERROR OCCURED :: ' + e.response['Error']['Message'])
                     sns_notification_message += '\n ERROR OCCURED :: ' + e.response['Error']['Message']
                     break
               continue
               
            print("Starting scale out. Creating additional " + str(scale_out_replica_count-current_replica_count) + " read replicas.")
            
            sns_notification_message += "\nStarting scale out. Creating additional " + str(scale_out_replica_count-current_replica_count) + " read replicas."
            if instance['DBInstanceStatus'] in 'modifying/configuring-enhanced-monitoring':
               print("Currently database is not in available state. Skipping '"+instance['DBInstanceIdentifier']+"' for now and adding it to queue.")
               sns_notification_message += "\nCurrently database is not in available state. Skipping '"+instance['DBInstanceIdentifier']+"' for now and adding it to queue."
               q.put(
                  {
                     'db':instance['DBInstanceIdentifier'],
                     'current_count':current_replica_count,
                     'target_count':scale_out_replica_count
                  }   
               )
               continue 
            i=current_replica_count + 1
            while i<=scale_out_replica_count:
               print('Creating replica - '+instance['DBInstanceIdentifier'] + '-replica-' + str(i))
               sns_notification_message += '\nCreating replica - '+instance['DBInstanceIdentifier'] + '-replica-' + str(i)
               try:
                  response = rds.create_db_instance_read_replica(
                     DBInstanceIdentifier=instance['DBInstanceIdentifier'] + '-replica-' + str(i),
                     SourceDBInstanceIdentifier=instance['DBInstanceIdentifier']
                  )
                  print("Successfully created replica.")
                  sns_notification_message += "\nSuccessfully created replica."
               except botocore.exceptions.ClientError as e:
                  print('ERROR OCCURED :: ' + e.response['Error']['Message'])
                  sns_notification_message += '\nERROR OCCURED :: ' + e.response['Error']['Message']
                  break
               i+=1
            
         else:
            if current_replica_count<scale_in_replica_count:
               print("Current replica count is less than target scale-in replica count. Creating aditional replicas.")
               sns_notification_message += "\nCurrent replica count is less than target scale-out replica count. Creating aditional replicas."
               if instance['DBInstanceStatus'] in 'modifying/configuring-enhanced-monitoring':
                  print("Currently database is not in available state. Skipping '"+instance['DBInstanceIdentifier']+"' for now and adding it to queue.")
                  sns_notification_message += "\nCurrently database is not in available state. Skipping '"+instance['DBInstanceIdentifier']+"' for now and adding it to queue."
                  q.put(
                     {
                        'db':instance['DBInstanceIdentifier'],
                        'current_count':current_replica_count,
                        'target_count':scale_in_replica_count
                     }   
                  )
                  continue
               while len(current_replicas) < scale_in_replica_count:
                  rep_name = instance['DBInstanceIdentifier'] + '-replica-' + str(len(current_replicas)+1) 
                  print("Creating replica '"+ rep_name +"'...")
                  sns_notification_message += "\nCreating replica '"+ rep_name +"'..."
                  try:
                     response = rds.create_db_instance_read_replica(
                        DBInstanceIdentifier=rep_name,
                        SourceDBInstanceIdentifier=instance['DBInstanceIdentifier']
                     )  
                     print("Successfully Created '"+ rep_name +"'.")
                     sns_notification_message += "\nSuccessfully Created '"+ rep_name +"'."
                     current_replicas.push(rep_name)
                  except botocore.exceptions.ClientError as e:
                     print('ERROR OCCURED :: ' + e.response['Error']['Message'])
                     sns_notification_message += '\nERROR OCCURED :: ' + e.response['Error']['Message']
                     break
               continue
               
            print("Starting scale-in. Deleting additional " + str(current_replica_count-scale_in_replica_count) + " read replicas.")
            
            sns_notification_message += "\nStarting scale in. Deleting additional " + str(current_replica_count-scale_in_replica_count) + " read replicas."
            
            i=current_replica_count
            while i>scale_in_replica_count:
               rep_name = instance['DBInstanceIdentifier'] + '-replica-' + str(i)
               print("Deleting replica '"+ rep_name +"'...")
               sns_notification_message += "\nDeleting replica '"+ rep_name +"'..."
               try:
                  response = rds.delete_db_instance(
                     DBInstanceIdentifier=rep_name,
                     SkipFinalSnapshot=True
                  )
                  print("Successfully Deleted '"+ rep_name +"'.")
                  sns_notification_message += "\nSuccessfully Deleted '"+ rep_name +"'."
               except botocore.exceptions.ClientError as e:
                  print(e.response['Error']['Message'])
                  print('ERROR OCCURED :: ' + e.response['Error']['Message'])
                  sns_notification_message += '\nERROR OCCURED :: ' + e.response['Error']['Message']
                  break
               i-=1
   
      else:
         print('Scheduled scaling not enabled for DB Instance - '+instance['DBInstanceIdentifier'])
   if q.qsize()!=0:  
      print('================================================================================================================================')   
      sns_notification_message += '\n================================================================================================================================'
      print('Scaling databases in queue...')
   while int(time.time()-strtime)<=750 and q.qsize()!=0 :
      time.sleep(30)
      db = q.get()
      instance = rds.describe_db_instances(DBInstanceIdentifier=db['db'])['DBInstances'][0]
      if instance['DBInstanceStatus']=='available':
         i=db['current_count'] + 1
         while i<=db['target_count']:
            print('Creating replica - '+instance['DBInstanceIdentifier'] + '-replica-' + str(i))
            sns_notification_message += '\nCreating replica - '+instance['DBInstanceIdentifier'] + '-replica-' + str(i)
            try:
               response = rds.create_db_instance_read_replica(
                  DBInstanceIdentifier=instance['DBInstanceIdentifier'] + '-replica-' + str(i),
                  SourceDBInstanceIdentifier=instance['DBInstanceIdentifier']
               )
               print('Replica creation triggered.')
               sns_notification_message += '\nReplica creation triggered.'
            except botocore.exceptions.ClientError as e:
               print('ERROR OCCURED :: ' + e.response['Error']['Message'])
               sns_notification_message += '\nERROR OCCURED :: ' + e.response['Error']['Message']
            i+=1
         print('================================================================================================================================')   
         sns_notification_message += '\n================================================================================================================================'
      elif instance['DBInstanceStatus'] in 'modifying/configuring-enhanced-monitoring':
         q.put(db)
         
   if(q.qsize()!=0):
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
      try:
         sns.publish(
            TopicArn=sns_arn,
             Message= sns_notification_message
         )
         print("Notification sent")
      except botocore.exceptions.ClientError as e:
         print("Failed to sent notification")
         print('ERROR OCCURED :: ' + e.response['Error']['Message'])
