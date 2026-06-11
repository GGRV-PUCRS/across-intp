#!/bin/bash
# Continuous Faban load from inside the CloudSuite web-search client image:
# loop the client's own entrypoint against the `server` service until the
# stack is torn down.
#
# Pressure model (C33): the CloudSuite defaults are think-time driven
# (8 workers x 1 s ThinkTime ~ 6-8 req/s -> sub-1% server CPU; verified in
# the app20 micro), which is too light to exercise interference. We drive
# CycleTime mode with a worker pool + bounded cycle interval, both sized by
# the installer-written .env. FABAN_STEADY is long (default 600 s) so one
# steady phase covers a whole measure window -- the driver REBUILDS between
# iterations (~40 s gap; SearchDriver.java is generated with open(...,"x"),
# verified, hence the rm).
set -u
WORKERS="${FABAN_WORKERS:-16}"
STEADY="${FABAN_STEADY:-600}"
IMIN="${FABAN_INTERVAL_MIN:-200}"
IMAX="${FABAN_INTERVAL_MAX:-400}"

# Wait for Solr to answer before the first Faban run (its own retry handling
# is poor while the server is still loading the index).
until curl -sf -o /dev/null "http://server:8983/solr/"; do
    sleep 3
done

while true; do
    rm -f "${FABAN_HOME:?image must set FABAN_HOME}/search/src/sample/searchdriver/SearchDriver.java"
    /docker-entrypoint.py server "$WORKERS" \
        --steady "$STEADY" \
        --interval-min "$IMIN" --interval-max "$IMAX" \
        --interval-type CycleTime --interval-distribution Uniform \
        || sleep 5
done
