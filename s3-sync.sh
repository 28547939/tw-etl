#!/bin/sh
#

set -o nounset

LOCK=$TW_BASE/sync/lock

#openssl_args_path=$TW_BASE/sync/openssl-args.txt
#if [ -f $openssl_args_path ]; then
#	openssl_args=$(cat $openssl_args_path)
#else
#	echo $openssl_args_path empty
#	exit 1
#fi

if [ -f $LOCK ] && [ -z $LOCK ]; then
    echo $LOCK exists
    exit 0
fi

touch $LOCK


# for now, encrypt and decrypt filenames only
#
#
encrypt () {
    echo $1 | openssl enc $OPENSSL_ARGS | \
       xxd -p | tr -d \\n
}

decrypt () {
    echo $1 | fold -w 2 | \
        perl -ne 'print chr(hex($_))' | \
        openssl enc -d $OPENSSL_ARGS
               
}


# 2023-11-03 transferred robcdee without any conversion due to lack of space


# sync_s3 filename
sync_s3 () {
    name=$(basename $1)
    name_enc=$(encrypt $name)
    key="tw/$name_enc"

    echo uploading $1
    aws s3 mv --region us-east-2 --profile $AWS_PROFILE --storage-class $2 \
        $1 \
        s3://$AWS_BUCKET/$key >/dev/null

	# just a nice confirmation that the object is successfully stored (but this does waste a few seconds)
    aws s3api head-object --region us-east-2 --profile $AWS_PROFILE --bucket $AWS_BUCKET --key $key
}

cat $TW_BASE/sync/readydir-list.txt | while read readydir ; do
    if [ $(ls $readydir/*.mkv | wc -l) -gt 0 ]; then 

        for f in $TW_BASE/$readydir/*.mkv ; do 
            sync_s3 "$f"  DEEP_ARCHIVE
        done

        for f in $TW_BASE/$readydir/*.json ; do 
            sync_s3 "$f"  STANDARD_IA
        done

        for f in $TW_BASE/$readydir/*.json.gz ; do 
            sync_s3 "$f"  DEEP_ARCHIVE
        done
    else
        echo no mkv files found
    fi
done


rm $LOCK
