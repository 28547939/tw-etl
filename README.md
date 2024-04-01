
# tw-etl

This readme left blank except for the following notes.

### Notes

* Required environment variables for `s3-sync.sh` and `convert.sh`:
  * `TW_BASE`, `AWS_PROFILE`, `AWS_BUCKET`, `CONVERT_IN`, `CONVERT_PENDING`, `OPENSSL_ARGS`
  * `OPENSSL_ARGS` gives the arguments used to encrypt filenames in S3 (see `convert.sh`)
* On S3, files will be copied to keys (paths) starting with `tw/`
