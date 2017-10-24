#!/bin/bash

# Also recommend:
#    bind 'set show-all-if-ambiguous on'
# or add that to inputrc.  Yuck.
# Otherwise, it takes two tab presses...

_complete_ec2ssh()
{
    local IFS=$' \t\n'    # normalize IFS
    local currentcommand="$1"
    local currentword="$2"
    local previousword="$3"
    # prints paths one per line; could also use while loop
    IFS=$'\n'
    COMPREPLY=( $(_ec2ssh_complete_py "$currentword") )
    IFS=$' \t\n'

    return 0
}

# Use a bash completion function (-F) for the "ec2ssh" command
complete -F _complete_ec2ssh ec2ssh
