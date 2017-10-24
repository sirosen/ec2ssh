#!/usr/bin/env python3

"""
Print ec2 instance name(s) matching a prefix, for bash tab completion
If prefix starts with user@, it is parsed as an ssh user, to be nice to people
who use that instead of ssh -l.
"""

import os
import sys

import boto3


def main():
    name_prefix = sys.argv[1]
    user_prefix = ""

    # Accept user@host, for full ssh syntax
    parts = name_prefix.split("@", 1)
    if len(parts) == 2:
        user_prefix = parts[0] + "@"
        name_prefix = parts[1]

    pattern = name_prefix + "*"

    client = boto3.client("ec2")
    tagfilter = dict(Name='tag:Name', Values=[pattern])
    response = client.describe_instances(Filters=[tagfilter])

    for reservation in response["Reservations"]:
        instances = reservation["Instances"]
        for instance in instances:
            for tag in instance["Tags"]:
                if (tag["Key"] == "Name" and 
                        tag["Value"].startswith(name_prefix)): 
                    print(user_prefix + tag["Value"])


if __name__ == "__main__":
    main()
