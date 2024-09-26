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
    ec2_instance_id = 'instance-name'  # Replace with your instance ID
    sns_topic_arn = 'arn:aws:sns:region:account-id:topic-name'  # Replace with your SNS topic ARN
    ssm_client = boto3.client('ssm')
    ec2_client = boto3.client('ec2')

    # Start the EC2 instance
    try:
        ec2_client.start_instances(InstanceIds=[ec2_instance_id])
        print(f'Starting instance: {ec2_instance_id}')
    except Exception as e:
        error_message = f'Error starting instance: {e}'
        print(error_message)
        send_sns_notification(sns_topic_arn, 'EC2 Start Error', error_message)
        return

    # Wait for the instance to be in the running state
    waiter = ec2_client.get_waiter('instance_running')
    try:
        waiter.wait(InstanceIds=[ec2_instance_id])
        print(f'Instance {ec2_instance_id} is now running.')
    except Exception as e:
        error_message = f'Error waiting for instance to start: {e}'
        print(error_message)
        send_sns_notification(sns_topic_arn, 'Instance Start Wait Error', error_message)
        return
    
    # Wait for the instance to pass 2/2 status checks
    while True:
        statuses = ec2_client.describe_instance_status(InstanceIds=[ec2_instance_id])
        instance_statuses = statuses['InstanceStatuses']
        if len(instance_statuses) > 0:
            instance_status = instance_statuses[0]
            if instance_status['InstanceStatus']['Status'] == 'ok' and instance_status['SystemStatus']['Status'] == 'ok':
                print(f'Instance {ec2_instance_id} passed 2/2 status checks.')
                break
        print(f'Waiting for instance {ec2_instance_id} to pass 2/2 status checks...')
        time.sleep(30)  # Wait for 30 seconds before checking again

    # Define the commands to run on the EC2 instance
    commands = [
        'su - hdbadm -c "cleanipc 02 remove all"',
        'su - root -c "/usr/sap/HDB/HDB02/exe/sapcontrol -nr 02 -function StartService HDB"',
        'su - root -c "/usr/sap/HDB/HDB02/exe/sapcontrol -nr 02 -function StartSystem HDB"',
        'su - s4hadm -c "/usr/sap/HDB/HDB02/exe/sapcontrol -nr 00 -function StartService S4H"',
        'su - s4hadm -c "/usr/sap/HDB/HDB02/exe/sapcontrol -nr 00 -function StartSystem ALL"',
        'su - s4hadm -c "/usr/sap/HDB/HDB02/exe/sapcontrol -nr 01 -function StartService S4H"',
        'su - s4hadm -c "/usr/sap/HDB/HDB02/exe/sapcontrol -nr 01 -function StartSystem ALL"',
    ]

    process_checks = [
        '/usr/sap/hostctrl/exe/sapcontrol -nr 00 -function GetProcessList',
        '/usr/sap/hostctrl/exe/sapcontrol -nr 02 -function GetProcessList',
        '/usr/sap/hostctrl/exe/sapcontrol -nr 01 -function GetProcessList',
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
            time.sleep(10)  # Wait for a short period to allow the command to execute
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

    # Check the process lists to ensure they are in the green state
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
            time.sleep(10)  # Wait for a short period to allow the command to execute
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
                if 'GREEN' not in output['StandardOutputContent']:
                    error_message = f"One or more processes are not in GREEN state: {process_check}"
                    print(error_message)
                    send_sns_notification(sns_topic_arn, 'Process Check Warning', error_message)
                    return

        except Exception as e:
            error_message = f"Error executing process check: {e}"
            print(error_message)
            send_sns_notification(sns_topic_arn, 'Process Check Error', error_message)
            return

    print("All commands executed successfully and all processes are in GREEN state.")
    send_sns_notification(sns_topic_arn, 'All Processes Green', "All commands executed successfully and all processes are in GREEN state.")


