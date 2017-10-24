#!/bin/sh

# Also recommend: 
#    bind 'set show-all-if-ambiguous on'
# or add that to inputrc.  Yuck.
# Otherwise, it takes two tab presses...

_comp_ec2ssh()
{
    local IFS=$' \t\n'    # normalize IFS
    local cur="$2"
    # prints paths one per line; could also use while loop
    IFS=$'\n'
    COMPREPLY=( $(complete-instances.py "$cur") )
    IFS=$' \t\n'

    return 0
}

# Make sure to add these to your PATH
# A two letter, super short alias.
alias es=ec2ssh.py
complete -F _comp_ec2ssh es
