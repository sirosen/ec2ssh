#!/usr/bin/env python3

"""
ec2ssh: SSH *securely* to an EC2 instance without known_hosts hassles

Features

    - No "trust on first use" problem or "host key changed" alerts.
    - Grabs instance public keys using standard cloud-init console output
    - Custom known_hosts files (per-instance) are cached in ~/.ec2ssh/
    - Reassigning elastic IPs is no problem
    - Supports rsync tunneling.  Your one stop shop for file transfers!

Requirements

    - A Linux EC2 instance running cloud-init (the default for ubuntu)
    - Instance must have a "Name" tag

Usage

    ec2ssh <instance_name> [args to pass to ssh]

Examples

    # Interactive login
    ec2ssh mydev                                   

    # Specify the user and ssh verboseness
    ec2ssh mydev -l ubuntu -v

    # Alternative syntax
    ec2ssh ubuntu@mydev

    # Run command
    ec2ssh mydev echo "Hello Secure Cloud World"   

    # Upload file to instance
    rsync --rsh=./ec2ssh.py /tmp/localfile.txt user@mydev:/tmp/file2.txt 

    # Download file from instance
    rsync --rsh=./ec2ssh.py user@mydev:/tmp/file2.txt /tmp/copy.txt

    # Upload file to instance with root perms
    rsync --rsh=./ec2ssh.py --rsync-path="sudo rsync" \
            /tmp/local.txt user@mydev:/tmp/root.txt 

Bugs

    - AWS doc on how long console output is retained is clear as mud!
    - AWS should have a standard pubkey API and not use this hack!
    - Should atomically write/rename the known_hosts files
    - This script works best when the SSH options are AFTER the hostname.
      However, certain options like -l work in front, since rsync does that.

(C) 2017 Karl Pickett
"""

import subprocess
import sys
import re
import os.path

import boto3


SSH_KEY_TMPDIR = os.path.expanduser("~/.ec2ssh")


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
    return os.path.join(SSH_KEY_TMPDIR, file_name)


def write_known_hosts_file(file_name, keys, ssh_hostname):
    data = ""
    for key in keys:
        data += (ssh_hostname + " " + key + "\n")
    # Warning this is not atomic - not concurrent safe
    open(file_name, "w").write(data)


def trace(message):
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
    trace("Args: {}".format(args))
    user_prefix, instance_name, arg_index = find_hostname_arg(args)

    os.makedirs(SSH_KEY_TMPDIR, exist_ok=True)

    client = boto3.client('ec2')
    instance = get_instance_by_tag_name(client, instance_name)

    # Could use private IP, e.g. if you are in VPN/VPC
    ssh_hostname = instance["PublicIpAddress"]
    instance_id = instance["InstanceId"]

    file_name = get_known_hosts_name(instance_id, ssh_hostname)
    if not os.path.exists(file_name):
        keys = get_ssh_host_keys_from_console_output(client, instance_id)
        write_known_hosts_file(file_name, keys, ssh_hostname)
        trace("Created new file: {}".format(file_name))
    else:
        trace("Using cached file: {}".format(file_name))

    # Replace the instance name with the IP 
    args[arg_index:arg_index+1] = [ssh_hostname]

    # Add our extra options to the front
    extra_args = ["-o", "UserKnownHostsFile " + file_name]
    if user_prefix:
        extra_args += ["-l", user_prefix]
    args = ["ssh"] + extra_args + args
    trace("Running: {}".format(args))

    # We probably could just exec this
    p = subprocess.Popen(args)
    rc = p.wait()
    trace("Exit status: {}".format(rc))
    sys.exit(rc)


if __name__ == "__main__":
    main()
