import boto3

def lambda_handler(event, context):
    ec2 = boto3.client('ec2')

    response = ec2.describe_snapshots(OwnerIds=['self'])

    instances_response = client.describe_instances(Filters=[{'Name': 'instance-state-name','Values': ['running']}])
    active_instance_ids=set()
    for reservation in instances_response['Reservations']:
        for instance in reservation['Instances']:
            active_instance_ids.add(instance['InstanceId'])


    for snapshot in response['Snapshots']:
        snapshot_id = snapshot['SnapshotId']
        volume_id = snapshot.get('VolumeId')

        if not volume_id:
            ec2.delete_snapshots(SnapshotId=snapshot_id)
            print(f"Snapshot {snapshot_id} deleted since it is not attached to any volume ")
        else:
            try:
                volume_response = ec2.describe_volumes(VolumeIds=['volume_id'])
                if not volume_response['Volumes'][0]['Attachments']:
                    ec2.delete_snapshots(SnapshotId=snapshot_id)
                    print(f"Deleted {snapshot_id} snapshot as it is taken from a volume that is not attached to any instance")
            except ec2.exceptions.ClientError as e:
                if e.response['Error']['Code'] == 'InvalidVolume.NotFound':
                    ec2.delete_snapshots(SnapshotId=snapshot_id)
                    print(f"Deleted {snapshot_id} snapshot as assciated volume is not found")
