#!/bin/bash
# Batch workload: ready as soon as the job container is Running (the Spark
# driver starts computing immediately; there is no serving endpoint to probe).
set -u
cid=$(docker compose -p "$PROJECT" ps -q analytics 2>/dev/null | head -1)
[ -n "$cid" ] && docker inspect -f '{{.State.Running}}' "$cid" 2>/dev/null | grep -q true
