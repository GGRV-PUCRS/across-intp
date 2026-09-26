#!/bin/bash
# Ready when Solr serves AND the Faban load is actually flowing: the client
# image generates + compiles its driver on first start (~1 min), so "Solr up"
# alone lets the measure window open on an idle server (verified: the first
# app20 micro captured cpu<1%). The gate requires the select-handler request
# count to be strictly increasing between two consecutive readiness polls.
set -u
STATE="/tmp/intp-ws-ready-${PROJECT}.count"
curl -sf -o /dev/null "http://127.0.0.1:8983/solr/" || exit 1
# The Faban driver hits the /query handler (verified live: /select stays 0);
# sum both so a CloudSuite client change cannot silently idle the gate again.
cnt=$(curl -sf "http://127.0.0.1:8983/solr/admin/metrics?group=core&prefix=QUERY./query.requestTimes,QUERY./select.requestTimes" 2>/dev/null \
      | grep -o '"count":[0-9]*' | cut -d: -f2 | paste -sd+ | bc)
[ -n "$cnt" ] || exit 1
prev=$(cat "$STATE" 2>/dev/null || echo "")
echo "$cnt" > "$STATE"
[ -n "$prev" ] && [ "$cnt" -gt "$prev" ] && exit 0
exit 1
