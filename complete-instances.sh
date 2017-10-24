#!/bin/sh

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
    COMPREPLY=( $(complete-instances.py "$currentword") )
    IFS=$' \t\n'

    return 0
}

# Make sure to add these to your PATH
# A two letter, super short alias.
alias es=ec2ssh.py

# Use a bash completion function (-F) for the "es" command
complete -F _complete_ec2ssh es

# If you're annoyed by hitting hit tab twice before anything happens...
# This makes the first tab press always show the options
bind 'set show-all-if-ambiguous on'
