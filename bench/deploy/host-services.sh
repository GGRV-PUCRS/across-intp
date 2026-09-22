#!/usr/bin/env bash
# host-services.sh — Pause / resume host-side services that conflict with
# full-container or full-VM deployments.
#
# When BENCH_ENVS includes container-full or vm-full, the entire experimental
# stack (HDFS + Spark + workloads + profiler) runs INSIDE the deployment unit.
# Any host-side HDFS / YARN / Spark daemons would compete for the same TCP
# ports (9000, 8030-8033, 8042, 8088) AND inject background CPU/IO/network
# noise that biases the measurement.
#
# This script pauses such services before a full-* campaign and restores
# them after, so the same machine can run bare campaigns later without
# manual intervention.
#
# Usage:
#   bash host-services.sh pause   # snapshot running services and stop HDFS/YARN
#   bash host-services.sh resume  # restart only what we paused
#   bash host-services.sh status  # show current state
#
# State file: $HOSTSVC_STATE (default /var/lib/intp/host-services.state)
# Lists, one per line, the daemons we paused so resume only touches those.

set -u -o pipefail

STATE_FILE="${HOSTSVC_STATE:-/var/lib/intp/host-services.state}"
HADOOP_HOME="${HADOOP_HOME:-/opt/hadoop}"
# Separate state for the container-runtime quiesce so it composes with (and is
# restored independently of) the HDFS/YARN/Spark pause above.
RUNTIME_STATE="${HOSTSVC_RUNTIME_STATE:-${STATE_FILE%.state}.runtimes.state}"

log()  { printf '[host-services] %s\n' "$*"; }
warn() { log "WARN: $*" >&2; }

ensure_state_dir() {
    local d; d="$(dirname "$STATE_FILE")"
    [ -d "$d" ] || mkdir -p "$d"
}

# Detect HDFS NameNode/DataNode/SecondaryNameNode running via jps.
_hdfs_running() {
    command -v jps >/dev/null 2>&1 || return 1
    jps 2>/dev/null | grep -qE 'NameNode|DataNode|SecondaryNameNode'
}

# Detect YARN ResourceManager/NodeManager via jps.
_yarn_running() {
    command -v jps >/dev/null 2>&1 || return 1
    jps 2>/dev/null | grep -qE 'ResourceManager|NodeManager'
}

cmd_pause() {
    ensure_state_dir
    : > "$STATE_FILE"

    if _yarn_running; then
        log "stopping host YARN (was running)"
        if [ -x "$HADOOP_HOME/sbin/stop-yarn.sh" ]; then
            "$HADOOP_HOME/sbin/stop-yarn.sh" >/dev/null 2>&1 || warn "stop-yarn.sh failed"
        fi
        echo "yarn" >> "$STATE_FILE"
    else
        log "host YARN: not running"
    fi

    if _hdfs_running; then
        log "stopping host HDFS (was running)"
        if [ -x "$HADOOP_HOME/sbin/stop-dfs.sh" ]; then
            "$HADOOP_HOME/sbin/stop-dfs.sh" >/dev/null 2>&1 || warn "stop-dfs.sh failed"
        fi
        echo "hdfs" >> "$STATE_FILE"
    else
        log "host HDFS: not running"
    fi

    # Spark stand-alone master/worker (if present)
    if pgrep -f 'org.apache.spark.deploy.master.Master' >/dev/null 2>&1; then
        log "stopping host Spark master"
        pkill -f 'org.apache.spark.deploy.master.Master' || true
        echo "spark-master" >> "$STATE_FILE"
    fi
    if pgrep -f 'org.apache.spark.deploy.worker.Worker' >/dev/null 2>&1; then
        log "stopping host Spark worker"
        pkill -f 'org.apache.spark.deploy.worker.Worker' || true
        echo "spark-worker" >> "$STATE_FILE"
    fi

    sleep 2
    log "paused services recorded in $STATE_FILE"
    if [ -s "$STATE_FILE" ]; then
        sed 's/^/  /' "$STATE_FILE"
    else
        log "  (none — host had no services running)"
    fi
}

cmd_resume() {
    if [ ! -f "$STATE_FILE" ]; then
        log "no state file at $STATE_FILE — nothing to resume"
        return 0
    fi
    while IFS= read -r svc; do
        case "$svc" in
            hdfs)
                log "starting host HDFS"
                if [ -x "$HADOOP_HOME/sbin/start-dfs.sh" ]; then
                    "$HADOOP_HOME/sbin/start-dfs.sh" >/dev/null 2>&1 || warn "start-dfs.sh failed"
                fi
                ;;
            yarn)
                log "starting host YARN"
                if [ -x "$HADOOP_HOME/sbin/start-yarn.sh" ]; then
                    "$HADOOP_HOME/sbin/start-yarn.sh" >/dev/null 2>&1 || warn "start-yarn.sh failed"
                fi
                ;;
            spark-master|spark-worker)
                # Spark standalone is host-specific; document but don't auto-restart.
                log "$svc was paused — restart manually if needed (we don't track its launch script)"
                ;;
        esac
    done < "$STATE_FILE"
    rm -f "$STATE_FILE"
    sleep 2
    log "resume complete"
}

cmd_status() {
    log "HDFS:  $(_hdfs_running && echo running || echo stopped)"
    log "YARN:  $(_yarn_running && echo running || echo stopped)"
    if [ -f "$STATE_FILE" ]; then
        log "paused services tracked:"
        sed 's/^/  /' "$STATE_FILE"
    else
        log "no paused state on record"
    fi
    local rt unit
    for rt in docker lxd incus k3s; do
        local st="stopped"
        for unit in $(_runtime_units "$rt"); do
            _unit_active "$unit" && { st="running"; break; }
        done
        log "$rt:  $st"
    done
    if [ -f "$RUNTIME_STATE" ]; then
        log "quiesced runtimes tracked:"; sed 's/^/  /' "$RUNTIME_STATE"
    fi
    command -v jps >/dev/null 2>&1 && jps 2>/dev/null | sed 's/^/  jps: /'
}

# --- container runtime daemons (docker / lxd / incus / k3s) -----------------
# Idle container-runtime daemons inject background CPU / cache / IO / network
# noise that biases an interference measurement, exactly like idle HDFS/YARN.
# When a campaign does not need a runtime (bare / vm runs, or a docker-only run
# w.r.t. lxd), pause it and restore afterwards -- the daemon equivalent of the
# HiBench pause for stress-ng campaigns. Socket units are stopped too so
# socket-activation does not silently relaunch the service mid-measurement.
# Podman is intentionally absent: it is DAEMONLESS, so a container-podman
# campaign has no persistent runtime daemon to stop or restore -- there is
# nothing to quiesce or keep. (The container-podman env therefore matches no
# keep-set entry in run-big-batch.sh, so docker/lxd/incus all get quiesced,
# which is correct.)
# k3s is the STRONGEST quiesce case: k3s.service is DAEMON-FUL (kubelet +
# embedded containerd + control plane, plus k3s-agent.service on agent nodes),
# so its idle interference is the heaviest of any runtime here. A non-k8s
# campaign (bare / vm / podman / docker / lxc) must stop it; only an
# env=container-k8s campaign keeps it (run-big-batch.sh keep-set).
_runtime_units() {
    case "$1" in
        docker) echo "docker.service docker.socket" ;;
        lxd)    echo "snap.lxd.daemon.service snap.lxd.daemon.unix.socket lxd.service lxd.socket" ;;
        incus)  echo "incus.service incus.socket incus-user.service incus-user.socket" ;;
        k3s)    echo "k3s.service k3s-agent.service" ;;
        *)      echo "" ;;
    esac
}

_unit_active() { systemctl is-active --quiet "$1" 2>/dev/null; }

# quiesce-runtimes [keep ...]  -- stop every docker/lxd/incus/k3s daemon that is
# running and NOT listed in the keep-set; record only what we actually stopped.
cmd_quiesce_runtimes() {
    command -v systemctl >/dev/null 2>&1 || { warn "systemctl absent -- cannot quiesce runtimes"; return 0; }
    ensure_state_dir
    : > "$RUNTIME_STATE"
    local keep=" $* " rt unit
    for rt in docker lxd incus k3s; do
        case "$keep" in *" $rt "*) log "keeping $rt (needed by this campaign)"; continue ;; esac
        for unit in $(_runtime_units "$rt"); do
            if _unit_active "$unit"; then
                log "stopping $unit (interference quiesce; $rt not needed)"
                systemctl stop "$unit" >/dev/null 2>&1 || warn "stop $unit failed"
                echo "$unit" >> "$RUNTIME_STATE"
            fi
        done
    done
    if [ -s "$RUNTIME_STATE" ]; then sed 's/^/  paused: /' "$RUNTIME_STATE"; else log "  (no idle runtimes to pause)"; fi
}

# restore-runtimes -- restart only the units quiesce-runtimes stopped.
cmd_restore_runtimes() {
    [ -f "$RUNTIME_STATE" ] || { log "no runtime quiesce state -- nothing to restore"; return 0; }
    local unit
    while IFS= read -r unit; do
        [ -n "$unit" ] || continue
        log "restarting $unit"
        systemctl start "$unit" >/dev/null 2>&1 || warn "start $unit failed"
    done < "$RUNTIME_STATE"
    rm -f "$RUNTIME_STATE"
    log "runtime restore complete"
}

case "${1:-}" in
    pause)             cmd_pause ;;
    resume)            cmd_resume ;;
    quiesce-runtimes)  shift; cmd_quiesce_runtimes "$@" ;;
    restore-runtimes)  cmd_restore_runtimes ;;
    status)            cmd_status ;;
    *) cat <<EOF >&2
Usage: $0 {pause|resume|quiesce-runtimes [keep...]|restore-runtimes|status}

  pause              Stop HDFS/YARN/Spark daemons currently running on the host
                     and record them so we know what to bring back.
  resume             Start the services we paused (only those, not arbitrary).
  quiesce-runtimes   Stop idle container-runtime daemons (docker / lxd / incus /
     [keep...]       k3s) that bias the interference measurement, EXCEPT the
                     runtimes named as args (the ones this campaign needs).
                     Records only what it stopped. e.g. 'quiesce-runtimes docker'
                     for an env=container campaign, 'quiesce-runtimes k3s' for an
                     env=container-k8s campaign; no args for bare/vm campaigns.
  restore-runtimes   Restart only the runtime daemons quiesce-runtimes stopped.
  status             Show what's running and what we paused.

State files: $STATE_FILE
             $RUNTIME_STATE
HADOOP_HOME: $HADOOP_HOME
EOF
        exit 1 ;;
esac
