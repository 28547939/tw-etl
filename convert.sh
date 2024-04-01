#!/bin/sh
#

set -o nounset

base=$TW_BASE/data
ffmpeg=$(which ffmpeg)
ffprobe=$(which ffprobe)
jq=$(which jq)
ret=0

log () {
    ds=$(date -Iseconds)
    echo $ds $@ >> $TW_BASE/convert.log
}

LOCK=$TW_BASE/convert.lock

if [ -f $LOCK ] ; then
    echo lock exists
    exit 0
fi

touch $LOCK

q720p="1280x720"
q360p="640x360"
q160p="284x160"

for f in $(ls -Sr $CONVERT_IN/*.mkv); do

    if [ ! -f $f ]; then
        log file \'$f\' disappeared
        log ""
        continue
    fi

    # currently, assuming a filename in the format: ${STREAM}_${QUALITY}_${DATETIME}_${RETRY_ID}.mkv
    # where $QUALITY is a stream (quality) identifier as presented in the stream playlist 
    # (such as audio_only, 160p, 720p, 720p30, etc)
    q=$(echo "$f" | sed -Ee 's/^(.+\/)?.+_(audio_only|[^_]+p)_[[:digit:]]{4}-[[:digit:]]{2}-[[:digit:]]{2}T.+\.mkv/\2/')
    stream=$(echo "$f" | sed -Ee 's/^(.+\/)?([^_]+).+/\2/')

    height=$(ffprobe -hide_banner -v error -i "$f" \
            -show_streams -print_format json | $jq '.streams[1].height')

    width=$(ffprobe -hide_banner -v error -i "$f" \
            -show_streams -print_format json | $jq '.streams[1].width')

    ffmpeg_scale="${width}x${height}"


    dst=$CONVERT_PENDING/$(basename "$f")
    dst2=$CONVERT_OUT/$(basename "$f")

    # save the original metadata for the stream in case anything is lost; also shows this file's starting time
    # relative to the start of the stream (from which we can determine absolute wallclock time if needed)
    $ffprobe -hide_banner -v warning -i "$f" -show_streams -print_format json > $dst.json 2>>$TW_BASE/convert.log

    # generate full dump of stream 'packet' metadata to ensure that absolute wallclock time can be determined for
    # any moment of the stream within the file, e.g. to protect against effects of corruption or lost time due to 
    # advertising segments (which streamlink skips over)
    $ffprobe -hide_banner -v warning -i "$f" -of json -select_streams a:0 -show_entries \
        packet=pts_time,dts_time,size,pos,duration_time | \
        gzip -c9 > ${dst}_packets.json.gz 2>>$TW_BASE/convert.log


    if [ ! -f $dst.json ]; then
        log json was not generated for $dst, skipping 
        continue
    fi

    if [ $q == "audio_only" ]; then
        log "converting $f to $dst (audio_only)"
        $ffmpeg -y -hide_banner -loglevel error -i "$f"  -acodec libopus -b:a 24k -vbr on -application voip \
            $dst >/dev/null 2>>$TW_BASE/convert.log
    else


        fps_path=$TW_BASE/convert/fps/$stream
        if [ -f $fps_path ] ; then
            fps=$(cat $fps_path)

            if [ -z $fps ]; then
                fps=$DEFAULT_FPS
            fi
        fi

        log "converting $f to $dst (resolution $q fps $fps)"

        A="-acodec libopus -b:a 64k -vbr on -application voip"
        V="-vcodec libx265 -preset medium -filter:v  fps=$fps,scale=$ffmpeg_scale"

        log $stream: $V $A 

        $ffmpeg -y -hide_banner -loglevel error -i "$f" -x265-params log-level=error  \
            -map_metadata 0 -map_metadata:s:v 0:s:v -map_metadata:s:a 0:s:a \
            $V $A \
            $dst >/dev/null 2>>$TW_BASE/convert.log
    fi
    if [ $? == 0 ]; then
        log "finished $f" 

        oldsize=$(stat -f '%z' "$f")
        oldsize_h=$(ls -lh $f | awk '{print $5;}')
        newsize=$(stat -f '%z' "$dst")
        newsize_h=$(ls -lh $dst | awk '{print $5;}')
        x=$(bc  -e "scale = 3; 100*(1-$newsize/$oldsize)" -e quit)
        log reduced size by ${x}% "($oldsize_h -> $newsize_h)"

        log $(mv -v "$dst" "$dst2")
        log $(mv -v "$dst.json" "$dst2.json")
        log $(mv -v "${dst}_packets.json.gz" "${dst2}_packets.json.gz")

        if [ $? != 0 ]; then
            log "failed moving conversion output files - aborting"
            exit 1
        fi
        
        log deleted $(rm -vf "$f")
    else
        log "error for $f"
        ret=1
    fi
    log ""
    log ""
done

rm $LOCK

exit $ret
