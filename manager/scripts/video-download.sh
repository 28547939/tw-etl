#!/bin/sh
#

set -o nounset


# stream qlist outpath logpath
streamlink -4 -o $3 \
    --logfile $4 \
    --default-stream $2 \
    --twitch-disable-ads \
    --twitch-disable-reruns \
    --retry-max 5 \
    --stream-timeout 45 \
    --retry-open 5 \
    --loglevel all \
    https://www.twitch.tv/$1
