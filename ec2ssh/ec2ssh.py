#!/usr/bin/env python3

"""
ec2ssh - SSH *securely* to an EC2 instance without known_hosts hassles

Synopsis

    ec2ssh <instance_name> [args to pass to ssh]

Features

    - No "trust on first use" problem or "host key changed" alerts
    - Does not modify your main known_hosts file
    - Creates and caches per-instance minimal known_hosts files in ~/.ec2ssh/
    - Instance redeploys and elastic IP reassignments are no problem
    - Supports rsync tunneling.  This is your one stop shop for file transfers!

Requirements

    - Instance must have a "Name" tag
    - There are two options for getting the instance's public keys:
        a. Use the EC2 GetConsoleOutput API to get the cloud-init output
        b. Have the instance write them to an S3 bucket during boot

    Option a) is standard but the delay before GetConsoleOutput can be called
    is 6 minutes.  That's annoying to wait that long for a fresh instance.

    Option b) has no delay, but takes more scripting with cloud-init.
    It also requires an S3 bucket, IAM policy setup, cross account access etc.
    But the bucket is very secure, using the ec2:SourceInstanceARN IAM policy
    variable so each EC2 instance can only write its own file.

    In the future, I wish AWS would allow option c), which is an instance
    setting a "SSHFingerprint" tag on itself during boot.  As of Oct 2017,
    however, AWS can't do that securely (an instance can change other tags and
    other instances).  Sigh.

Environment Variables

    - EC2SSH_PUBLIC_IP=1 
        Use public IP of instance.  Default: private
    - EC2SSH_PUBKEY_DIR=<dir>  
        Directory that caches custom known hosts files.  Default: ~/.ec2ssh
    - EC2SSH_PUBKEY_BUCKET
        S3 bucket from which we lookup instance pubkeys.
        The file we look for is ${bucket}/${instance_arn}/sshkeys, which
        should have been already uploaded by cloud-init during boot.
        If this var is not set, we fall back to using the console output.
    - EC2SSH_DEBUG=1 
        Enable debugging messages to stderr

Examples

    # Interactive login using public / external IP
    export EC2SSH_PUBLIC_IP=1
    ec2ssh mydev                                   

    # Specify the user and ssh verboseness
    ec2ssh mydev -l ubuntu -v

    # Alternative syntax
    ec2ssh ubuntu@mydev

    # Run command
    ec2ssh mydev echo "Hello Secure Cloud World"   

    # Upload file to instance
    rsync --rsh=ec2ssh /tmp/local.txt user@mydev:/tmp/file2.txt 

    # Download file from instance
    rsync --rsh=ec2ssh user@mydev:/tmp/file2.txt /tmp/copy.txt

    # Upload file to instance with root perms
    rsync --rsh=ec2ssh --rsync-path="sudo rsync" \
            /tmp/local.txt user@mydev:/tmp/root.txt 

    # Show this help
    ec2ssh

Bugs

    - This script works best when the SSH options are AFTER the hostname.
      However, certain options like -l work in front, to support rsync.

(C) 2017 Karl Pickett
"""

import os
import os.path
import re
import sys
import tempfile

import boto3


PUBKEY_DIR = os.getenv("EC2SSH_PUBKEY_DIR")
if not PUBKEY_DIR:
    PUBKEY_DIR = os.path.expanduser("~/.ec2ssh")


def get_instance_by_tag_name(client, name):
    tagfilter = dict(Name='tag:Name', Values=[name])
    response = client.describe_instances(Filters=[tagfilter])
    owner = None
    ret = []
    for reservation in response["Reservations"]:
        instances = reservation["Instances"]
        ret += instances
        owner = reservation["OwnerId"]
    if not ret:
        raise Exception("No instances found", name)
    if len(ret) > 1:
        raise Exception("Multiple instances found", name)
    return ret[0], owner


def get_host_pubkeys_from_console(client, instance_id):
    """
    Get instance's public keys from cloud-init output, via the EC2 console API.
    This method works and is "standard" but unfortunately takes 6 minutes for
    EC2 to post the initial boot data.  
    """
    debug("Getting console output: {}".format(instance_id))
    response = client.get_console_output(InstanceId=instance_id)
    if "Output" not in response:
        raise Exception("No console output yet - this may take a few minutes", 
                instance_id)
    regex = ("-----BEGIN SSH HOST KEY KEYS-----(.*)"
            "-----END SSH HOST KEY KEYS-----")
    output = response["Output"]
    mo = re.search(regex, output, re.DOTALL)
    if mo:
        keys = mo.group(1).strip().split("\n")
        return keys
    else:
        raise Exception("No SSH HOST KEY KEYS found", instance_id)


def get_host_pubkeys_from_s3(bucket, instance_arn):
    """
    Get instance's public keys from an S3 bucket.
    This works immediately after boot, but requires more non-standard setup
    and scripting via cloud-init.
    """
    object_name = instance_arn + "/sshkeys"
    client = boto3.client('s3')
    debug("Downloading S3 file: {}".format(object_name))
    res = client.get_object(Bucket=bucket, Key=object_name)
    data = res["Body"].read()
    return str(data, "utf-8").strip().split("\n")


def get_known_hosts_name(instance_id, ssh_hostname):
    file_name = "pubkey-%s-%s" % (instance_id, ssh_hostname)
    return os.path.join(PUBKEY_DIR, file_name)


def write_custom_known_hosts_file(file_name, keys, ssh_hostname):
    data = ""
    for key in keys:
        data += (ssh_hostname + " " + key + "\n")
    
    # Atomically write/rename a temp file to be concurrent-safe
    temp = tempfile.NamedTemporaryFile("w", 
            dir=PUBKEY_DIR, delete=False)
    temp.write(data)
    debug("Wrote temp file {}".format(temp.name))
    os.rename(temp.name, file_name)


def debug(message):
    if os.getenv("EC2SSH_DEBUG") != "1":
        return
    sys.stderr.write(str(message).strip() + "\n")
    sys.stderr.flush()


def find_hostname_arg(args):
    """
    The first non-option argument to ssh is the "hostname".
    It may be prefixed by "user@".
    Return (user_prefix, instance_name, arg_index)
    """
    # We need to have some knowledge of how ssh parses options
    # Options that take values need to have their values skipped
    options_to_skip = ["-l", "-o", "-i"]
    for i, v in enumerate(args):
        if i > 0 and args[i-1] in options_to_skip:
            continue
        if not v.startswith("-"):
            parts = v.split("@", 1)
            if len(parts) == 1:
                return ("", parts[0], i)
            else:
                return (parts[0], parts[1], i)

    raise Exception("Instance name is required")


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(2)

    debug("Args: {}".format(args))
    user_prefix, instance_name, arg_index = find_hostname_arg(args)

    os.makedirs(PUBKEY_DIR, exist_ok=True)

    client = boto3.client('ec2')
    instance, account = get_instance_by_tag_name(client, instance_name)

    instance_id = instance["InstanceId"]
    if os.getenv("EC2SSH_PUBLIC_IP") == "1":
        ssh_hostname = instance["PublicIpAddress"]
    else:
        ssh_hostname = instance["PrivateIpAddress"]

    instance_arn = "arn:aws:ec2:{region}:{acct}:instance/{id}".format(
            region=boto3.DEFAULT_SESSION.region_name,
            acct=account,
            id=instance_id)
    bucket = os.getenv("EC2SSH_PUBKEY_BUCKET")

    file_name = get_known_hosts_name(instance_id, ssh_hostname)
    if not os.path.exists(file_name):
        if bucket:
            keys = get_host_pubkeys_from_s3(bucket, instance_arn)
        else:
            keys = get_host_pubkeys_from_console(client, instance_id)
        write_custom_known_hosts_file(file_name, keys, ssh_hostname)
        debug("Created new file: {}".format(file_name))
    else:
        debug("Using cached file: {}".format(file_name))

    # Replace the instance name with the IP 
    args[arg_index:arg_index+1] = [ssh_hostname]

    # Add our extra options to the front
    extra_args = ["-o", "UserKnownHostsFile " + file_name]
    if user_prefix:
        extra_args += ["-l", user_prefix]
    args = ["ssh"] + extra_args + args
    debug("Running: {}".format(args))

    # Just exec to save memory
    os.execvp(args[0], args)


if __name__ == "__main__":
    main()
