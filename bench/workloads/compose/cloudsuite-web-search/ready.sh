#!/bin/bash
# Ready when Solr answers on the published port (index loaded enough to serve).
set -u
curl -sf -o /dev/null "http://127.0.0.1:8983/solr/"
