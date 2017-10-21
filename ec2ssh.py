#!/usr/bin/env python3

"""
ec2ssh - SSH *securely* to an EC2 instance without known_hosts hassles

Synopsis

    ec2ssh <instance_name> [args to pass to ssh]

Features

    - No "trust on first use" problem or "host key changed" alerts.
    - Does not modify your real known_hosts file
    - Grabs instance public keys using standard cloud-init console output
    - Creates and caches per-instance custom known_hosts files in ~/.ec2ssh/
    - Instance redeploys and elastic IP reassignments are no problem
    - Supports rsync tunneling.  This is your one stop shop for file transfers!

Requirements

    - A Linux EC2 instance running cloud-init (the default for Ubuntu)
    - Instance must have a "Name" tag

Environment Variables

    - EC2SSH_PUBLIC_IP=1 
        Use public IP of instance.  Default: private
    - EC2SSH_PUBKEY_DIR=<dir>  
        Directory that caches custom known hosts files.  Default: ~/.ec2ssh
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

    - AWS doc / guarantee on how long GetConsoleOutput is retained is horrible!
    - AWS should have a standard pubkey API and not use this hack!
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
    ret = []
    for reservation in response["Reservations"]:
        instances = reservation["Instances"]
        ret += instances
    if not ret:
        raise Exception("No instances found", name)
    if len(ret) > 1:
        raise Exception("Multiple instances found", name)
    return ret[0]


def get_ssh_host_keys_from_console_output(client, instance_id):
    response = client.get_console_output(InstanceId=instance_id)
    regex = ("-----BEGIN SSH HOST KEY KEYS-----(.*)"
            "-----END SSH HOST KEY KEYS-----")
    output = response["Output"]
    mo = re.search(regex, output, re.DOTALL)
    if mo:
        keys = mo.group(1).strip().split("\n")
        return keys
    else:
        raise Exception("No SSH HOST KEY KEYS found", instance_id)


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
    sys.stderr.write(message.strip() + "\n")
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
    instance = get_instance_by_tag_name(client, instance_name)

    instance_id = instance["InstanceId"]
    if os.getenv("EC2SSH_PUBLIC_IP") == "1":
        ssh_hostname = instance["PublicIpAddress"]
    else:
        ssh_hostname = instance["PrivateIpAddress"]

    file_name = get_known_hosts_name(instance_id, ssh_hostname)
    if not os.path.exists(file_name):
        keys = get_ssh_host_keys_from_console_output(client, instance_id)
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
