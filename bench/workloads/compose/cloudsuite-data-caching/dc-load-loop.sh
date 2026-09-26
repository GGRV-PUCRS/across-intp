#!/bin/bash
# Continuous memcached load via the CloudSuite client's OWN entrypoint
# (verified modes: S&W = scale+warm, TH = max-throughput): scale the twitter
# dataset 2x and preload once, then loop the throughput run until the stack is
# torn down. Scale 2 (~600 MB, seconds to build) keeps the per-rep path fast —
# request pressure (workers/connections), not dataset bytes, drives the
# interference fingerprint; D=4096 matches the server's -m 4096.
set -u
SCALE="${DC_SCALE:-2}"

# Scale + warm; retry until memcached accepts connections.
until /entrypoint.sh --m='S&W' --S="$SCALE" --w=4 --D=4096 --T=1; do
    sleep 2
done

while true; do
    /entrypoint.sh --m=TH --S="$SCALE" --g=0.8 --w=4 --c=100 --T=1 || sleep 2
done
