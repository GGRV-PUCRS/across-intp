#!/bin/bash
# Ready when the nginx-thrift frontend answers HTTP on the published port
# (any HTTP status counts: nginx + the thrift upstreams are up; an empty
# social graph is expected at this point — load.sh seeds it).
set -u
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 "http://127.0.0.1:8080/" 2>/dev/null)
case "$code" in
    2*|3*|4*|5*) exit 0 ;;
    *)           exit 1 ;;
esac
