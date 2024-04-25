#!/bin/sh
#

set -o nounset

# underlying online status of the stream is indicated by the existence of $FILE:
# we check for existence of $FILE instead of trying to download a real stream.
#
# so testing is carried out by `touch`ing or `rm`ing $FILE as appropriate

BASE=.

FILE=$BASE/manager/test/online/$1

while true; do
    sleep 1;
    stat $FILE >/dev/null 2>/dev/null
        
    if [ $? == 1 ]; then
        exit 1
    fi
done
