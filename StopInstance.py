import boto3
import time

def send_sns_notification(topic_arn, subject, message):
    sns_client = boto3.client('sns')
    sns_client.publish(
        TopicArn=topic_arn,
        Subject=subject,
        Message=message
    )

def lambda_handler(event, context):
    ec2_instance_id = 'instance-id'  # Replace with your instance ID
    sns_topic_arn = 'arn:aws:sns:region:account-id:topic-name'  # Replace with your SNS topic ARN
    ssm_client = boto3.client('ssm')
    ec2_client = boto3.client('ec2')

    # Define the commands to stop the application server and database
    commands = [
        'su - s4hadm -c "/usr/sap/hostctrl/exe/sapcontrol -nr 00 -function StopSystem ALL"',
        'su - s4hadm -c "/usr/sap/hostctrl/exe/sapcontrol -nr 00 -function StopService"',
        'su - s4hadm -c "/usr/sap/hostctrl/exe/sapcontrol -nr 01 -function StopSystem ALL"',
        'su - s4hadm -c "/usr/sap/hostctrl/exe/sapcontrol -nr 01 -function StopService"',
        'su - root -c "/usr/sap/HDB/HDB02/exe/sapcontrol -nr 02 -function StopSystem HDB"'
    ]

    process_checks = [
        '/usr/sap/hostctrl/exe/sapcontrol -nr 00 -function GetProcessList',
        '/usr/sap/hostctrl/exe/sapcontrol -nr 01 -function GetProcessList',
        '/usr/sap/hostctrl/exe/sapcontrol -nr 02 -function GetProcessList'
    ]

    # Send the commands to the EC2 instance using SSM
    for command in commands:
        try:
            response = ssm_client.send_command(
                InstanceIds=[ec2_instance_id],
                DocumentName="AWS-RunShellScript",
                Parameters={'commands': [command]},
            )

            command_id = response['Command']['CommandId']
            print(f'Command ID: {command_id}')

            # Wait for the command to complete
            time.sleep(20)  # Wait for a short period to allow the command to execute
            output = ssm_client.get_command_invocation(
                CommandId=command_id,
                InstanceId=ec2_instance_id
            )

            if output['Status'] != 'Success':
                error_message = f"Command failed: {command}\nError: {output['StandardErrorContent']}"
                print(error_message)
                send_sns_notification(sns_topic_arn, 'Command Execution Error', error_message)
                return
            else:
                print(f"Command succeeded: {command}")
                print(f"Output: {output['StandardOutputContent']}")

        except Exception as e:
            error_message = f"Error executing command: {e}"
            print(error_message)
            send_sns_notification(sns_topic_arn, 'Command Execution Error', error_message)
            return

    # Check the process lists to ensure all services are stopped
    for process_check in process_checks:
        try:
            response = ssm_client.send_command(
                InstanceIds=[ec2_instance_id],
                DocumentName="AWS-RunShellScript",
                Parameters={'commands': [process_check]},
            )

            command_id = response['Command']['CommandId']
            print(f'Process check command ID: {command_id}')

            # Wait for the command to complete
            time.sleep(20)  # Wait for a short period to allow the command to execute
            output = ssm_client.get_command_invocation(
                CommandId=command_id,
                InstanceId=ec2_instance_id
            )

            if output['Status'] != 'Success':
                error_message = f"Process check failed: {process_check}\nError: {output['StandardErrorContent']}"
                print(error_message)
                send_sns_notification(sns_topic_arn, 'Process Check Error', error_message)
                return
            else:
                print(f"Process check succeeded: {process_check}")
                print(f"Output: {output['StandardOutputContent']}")
                if 'Stopped' not in output['StandardOutputContent']:
                    error_message = f"One or more processes are not stopped: {process_check}"
                    print(error_message)
                    send_sns_notification(sns_topic_arn, 'Process Check Error', error_message)
                    return

        except Exception as e:
            error_message = f"Error executing process check: {e}"
            print(error_message)
            send_sns_notification(sns_topic_arn, 'Process Check Error', error_message)
            return

    # Stop the EC2 instance
    try:
        ec2_client.stop_instances(InstanceIds=[ec2_instance_id])
        print(f'Stopping instance: {ec2_instance_id}')
    except Exception as e:
        error_message = f'Error stopping instance: {e}'
        print(error_message)
        send_sns_notification(sns_topic_arn, 'EC2 Stop Error', error_message)
        return

    # Wait for the instance to be in the stopped state
    waiter = ec2_client.get_waiter('instance_stopped')
    try:
        waiter.wait(InstanceIds=[ec2_instance_id])
        print(f'Instance {ec2_instance_id} is now stopped.')
        send_sns_notification(sns_topic_arn, 'Instance Stopped', f'Instance {ec2_instance_id} has been successfully stopped.')
    except Exception as e:
        error_message = f'Error waiting for instance to stop: {e}'
        print(error_message)
        send_sns_notification(sns_topic_arn, 'Instance Stop Wait Error', error_message)

 