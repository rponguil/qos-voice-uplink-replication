#!/bin/bash
# Host CPU power state for the QoS measurements (needs root).
#   sudo bash host_perf.sh on      governor=performance, EPP=performance, idle states deeper than C1 disabled
#   sudo bash host_perf.sh off     back to powersave / balance_performance, all idle states enabled
#   bash host_perf.sh status       (no root needed)
set -e
mode=${1:-status}
status() {
  echo "governor: $(sort -u /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor | tr '\n' ' ')"
  echo "epp:      $(sort -u /sys/devices/system/cpu/cpu*/cpufreq/energy_performance_preference 2>/dev/null | tr '\n' ' ')"
  for s in /sys/devices/system/cpu/cpu0/cpuidle/state*; do
    echo "idle $(cat $s/name) latency=$(cat $s/latency)us disabled(cpu0)=$(cat $s/disable)"
  done
}
case $mode in
  on)
    command -v powerprofilesctl >/dev/null && powerprofilesctl set performance || true   # else PPD can re-apply 'balanced' (12-10: governor fell to powersave at 11:48)
    for c in /sys/devices/system/cpu/cpu*/cpufreq; do
      echo performance > $c/scaling_governor
      [ -w $c/energy_performance_preference ] && echo performance > $c/energy_performance_preference || true
    done
    for s in /sys/devices/system/cpu/cpu*/cpuidle/state*; do
      [ "$(cat $s/latency)" -gt 2 ] && echo 1 > $s/disable || echo 0 > $s/disable
    done ;;
  off)
    command -v powerprofilesctl >/dev/null && powerprofilesctl set balanced || true
    for c in /sys/devices/system/cpu/cpu*/cpufreq; do
      echo powersave > $c/scaling_governor
      [ -w $c/energy_performance_preference ] && echo balance_performance > $c/energy_performance_preference || true
    done
    for s in /sys/devices/system/cpu/cpu*/cpuidle/state*; do echo 0 > $s/disable; done ;;
esac
status
