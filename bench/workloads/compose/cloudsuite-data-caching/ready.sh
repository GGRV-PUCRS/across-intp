#!/bin/bash
# Ready when memcached answers `version` over the project network (probed from
# the load-client container; the server publishes no host port).
set -u
docker compose -p "$PROJECT" exec -T load-client bash -c \
    'exec 3<>/dev/tcp/server/11211 && printf "version\r\n" >&3 && head -c 7 <&3 | grep -q VERSION'
