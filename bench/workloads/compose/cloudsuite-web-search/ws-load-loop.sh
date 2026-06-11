#!/bin/bash
# Continuous Faban load from inside the CloudSuite web-search client image:
# loop the client's own entrypoint (one bounded run per iteration: 20 s ramp-up
# + FABAN_STEADY s steady + 10 s ramp-down) against the `server` service until
# the stack is torn down. The entrypoint generates SearchDriver.java with
# open(..., "x") which fails if the file exists (verified), so it is removed
# between iterations.
set -u
WORKERS="${FABAN_WORKERS:-8}"
STEADY="${FABAN_STEADY:-120}"

# Wait for Solr to answer before the first Faban run (its own retry handling
# is poor while the server is still loading the index).
until curl -sf -o /dev/null "http://server:8983/solr/"; do
    sleep 3
done

while true; do
    rm -f "${FABAN_HOME:?image must set FABAN_HOME}/search/src/sample/searchdriver/SearchDriver.java"
    /docker-entrypoint.py server "$WORKERS" --steady "$STEADY" || sleep 5
done
