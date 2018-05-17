#!/usr/pkg/bin/python3.6


"""
TODO - module docstring
"""


import argparse
import os
import datetime
import math
import time
import boto3
import subprocess


context = {}


def load_context():
    arguments = parse_arguments()

    context = {
        "arguments": arguments,
        "environment": load_environment(),
        "directory": directory_information(arguments.directory)
    }

    return context


def parse_arguments():
    """ Parse command line arguments and return a Namespace object. """
    parser = argparse.ArgumentParser(
        description="The ec2-backup tool performs a backup of the given "
        "directory into Amazon Elastic Block Storage (EBS).  This is "
        "achieved by creating a volume of the appropriate size, attaching "
        "it to an EC2 instance and finally copying the files from the given "
        "directory onto this volume."
    )

    parser.add_argument(metavar="dir", dest="directory")

    parser.add_argument(
        "-l", metavar="filter", dest="local_filter", help="Pass data "
        "through the given filter command on the localhost before copying "
        "the data to the remote system.")

    parser.add_argument(
        "-r", metavar="filter", dest="remote_filter", help="Pass data "
        "through the given filter command on the remote host before writing "
        "the data to the volume.")

    parser.add_argument(
        "-v", metavar="volume-id", dest="volume_id", help="Use the given "
        "volume instead of creating a new one.")

    arguments = parser.parse_args()

    return arguments


def load_environment():
    """ Parse environment variables and return a dictionary object. """
    environment = {
        "VERBOSE": os.getenv("EC2_BACKUP_VERBOSE", False),
        "AWS_FLAGS": os.getenv("EC2_BACKUP_FLAGS_AWS", ""),
        "SSH_FLAGS": os.getenv("EC2_BACKUP_FLAGS_SSH", "")
    }

    return environment


def directory_information(target: str):
    """ Returns the size of a target to the nearst gigabyte. """
    information = {
        "path": os.path.abspath(target),
        "size": {
            "GB": 0,
            "B": 0
        }
    }

    for relative_path, _, filenames in os.walk(target):
        for filename in filenames:
            filepath = os.path.join(relative_path, filename)
            information["size"]["B"] += os.path.getsize(filepath)

    # Nearest GB
    information["size"]["GB"] = math.ceil(information["size"]["B"] / (2 ** 30))

    return information


def verbose(message: str):
    """ Prints verbose trace messages to STDOUT. """
    if context["environment"]["VERBOSE"]:
        print("ec2-backup: [{}]: {}".format(datetime.datetime.now(), message))

    return


class Volume:
    @staticmethod
    def query(identifier: str):
        print("".format())
        ec2_connection = boto3.resource("ec2")
        return ec2_connection.volume(identifier)


class Instance:
    def __init__(self):
        """ Initialize instance default launch configuration. """
        self.image_id = "ami-0dc82b70"
        self.instance_type = "t1.micro"
        self.wait_delay = 5.000

        self.identifier = None

        verbose("Initialized instance launch configuration:")
        verbose("AMI = {}".format(self.image_id))
        verbose("TYPE = {}".format(self.instance_type))

        return

    def create(self):
        """ Create an AWS EC2 instance with an attached EBS volume. """
        verbose("Opening connection with AWS API...")
        ec2_connection = boto3.resource("ec2")

        verbose("Attempting to create AWS EC2 security group...")
        try:
            ec2_connection.create_security_group(
                GroupName="ec2-backup",
                Description="Allow SSH ingress traffic."
            )
        except:
            verbose("Security group already exists.")

        verbose("Opening raw-connection with boto3 API...")
        client = boto3.client("ec2")

        verbose("Attempting to configure security group ingress policy...")
        try:
            client.authorize_security_group_ingress(
                GroupName="ec2-backup",
                IpPermissions=[
                    {
                        "FromPort": 22,
                        "ToPort": 22,
                        "IpProtocol": "TCP",
                        "IpRanges": [
                            {
                                "CidrIp": "0.0.0.0/0",
                                "Description": "Allow all hosts."
                            }
                        ]
                    }
                ]
            )
        except:
            verbose("Policy already exists.")

        verbose("Describing EC2 key pair...")
        keypairs = list(ec2_connection.key_pairs.all())

        if len(keypairs) <= 0:
            raise Error("No key-pairs present on AWS EC2 console.")

        keypair = keypairs.pop()
        verbose("Selected key-pair: {}".format(keypair))

        verbose("Creating EC2 instance with EBS...")
        response = ec2_connection.create_instances(
            KeyName=keypair.name,
            BlockDeviceMappings=[
                {
                    'DeviceName': 'sdb',
                    'Ebs': {
                        'Encrypted': False,
                        'DeleteOnTermination': False,
                        'VolumeSize': 2 * context["directory"]["size"]["GB"],
                        'VolumeType': 'standard'
                    },
                },
            ],
            ImageId=self.image_id,
            InstanceType=self.instance_type,
            # Region=None,
            # Placement={
            #    "AvailabilityZone": None
            #},
            MinCount=1,
            MaxCount=1,
            SecurityGroups=[
                'ec2-backup'
            ],
            InstanceInitiatedShutdownBehavior="terminate"
        )

        instance = response[0]
        self.identifier = instance.id

        # Provide time for the instance to be created
        time.sleep(self.wait_delay)

        # Wait for the instance to enter a healthy state

        verbose("Waiting for EC2 instance to enter healthy state...")
        while not self.is_healthy():
            time.sleep(self.wait_delay)

        thisInst = ec2_connection.Instance(instance.id)

        return thisInst.public_dns_name

    def is_healthy(self):
        """ Queries the status of the current EC2 instance and checks if it's
        healthy. """
        verbose("Openning raw-connection to boto3 API...")
        client = boto3.client("ec2")

        verbose("Querying instance status...")
        response = client.describe_instance_status(
            InstanceIds=[
                self.identifier
            ]
        )

        # Not my proudest line of code, but AWS' response schema was
        # unpredictable :(
        if "'ok'" in str(response):
            return True

        return False

    def terminate(self):
        """ Terminate the provided AWS EC2 instance. """
        if self.identifier is None:
            return

        verbose("Opening a connection to the AWS API...")
        ec2_connection = boto3.resource("ec2")

        verbose("Filtering instance by identifier...")
        results = ec2_connection.instances.filter(
            InstanceIds=[
                self.identifier
            ]
        )

        verbose("Terminating instance...")
        results.terminate()

        return


def main():
    """ Main run-time function. """
    global context
    context = load_context()

    verbose("Evaluated runtime context: {}".format(context))

    i = Instance()
    result = i.create()

    tar = subprocess.Popen(['tar', 'cf', '-', context['directory']['path']],
                           stdout=subprocess.PIPE,)
    ssh = subprocess.Popen(['ssh',
                            'admin@' + result, 'sudo dd of=/dev/xvdb'],
                           stdin=tar.stdout,
                           stdout=subprocess.PIPE,
                           )
    ssh.wait()

    return


if __name__ == "__main__":
    main()
