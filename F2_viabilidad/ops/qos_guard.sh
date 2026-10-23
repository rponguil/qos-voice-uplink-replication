#!/bin/bash
# QoS campaign guard, run by cron every 10 min and after boot. Runs independently of any interactive session.
#   - never acts if ops/GUARD_STOP exists;
#   - session = contents of ops/SESSION (campaign1 | campaign2); done if its log ends with CAMPAIGN_DONE;
#   - campaign alive (PID in logs/<session>.pid) -> nothing;
#   - dead and not done: requires CPU governor 'performance' (else writes ALERT and stops);
#     starts gns3server if the API is down, prepares the lab (prep_session.py) and relaunches the
#     session (resumable run by run). Every action goes to ops/guard.log.
OPS="$(cd "$(dirname "$0")" && pwd)"; F2="$OPS/.."; SC="$F2/scripts"; LOG="$OPS/guard.log"
export PATH="$HOME/.local/bin:$HOME/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
export DISPLAY=:0 XDG_RUNTIME_DIR="/run/user/$(id -u)" DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$(id -u)/bus"
say() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG"; }
[ -f "$OPS/GUARD_STOP" ] && exit 0
mountpoint -q /data || { say "/data not mounted"; exit 0; }
# ops/SESSION: one or more modes in sequence (e.g. "campaign1 campaign1c"); the first one not finished is the current one
SESSION=""
for s_ in $(cat "$OPS/SESSION" 2>/dev/null); do
  tail -1 "$F2/logs/$s_.log" 2>/dev/null | grep -q "^CAMPAIGN_DONE" || { SESSION="$s_"; break; }
done
[ -z "$SESSION" ] && exit 0
# session 2 must run on a different day from session 1 (protocol §7.5; chained after campaign1k)
[ "$SESSION" = "campaign2" ] && [ "$(date +%Y%m%d)" -lt 20261015 ] && exit 0
SLOG="$F2/logs/$SESSION.log"; PIDF="$F2/logs/$SESSION.pid"
P="$(cat "$PIDF" 2>/dev/null)"
if [ -n "$P" ] && kill -0 "$P" 2>/dev/null && [ "$(ps -o args= -p "$P" | awk '{print $NF}')" = "$SESSION" ]; then exit 0; fi
for a_ in /sys/class/power_supply/ADP*/online; do   # never (re)launch on battery
  [ -f "$a_" ] && [ "$(cat "$a_")" != "1" ] && { say "no mains power: $SESSION not relaunched (waiting)"; exit 0; }
done
if [ "$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor)" != "performance" ]; then
  powerprofilesctl set performance 2>/dev/null && sleep 2 && say "governor was not performance: power profile set to performance (PPD)"
fi
if [ "$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor)" != "performance" ]; then
  say "ALERT: $SESSION not running and CPU governor is not 'performance' (needs: sudo bash host_perf.sh on); not relaunched"
  echo "$(date '+%F %T') CPU governor not performance; campaign $SESSION stopped" > "$OPS/ALERT"; exit 0
fi
# crash-loop cap: at most 6 relaunches in 24 h, then ALERT and wait for a person
N24=$(awk -v t="$(date -d '24 hours ago' '+%Y-%m-%d %H:%M:%S')" -v s="relaunched $SESSION," '($1" "$2) >= t && index($0, s)' "$LOG" 2>/dev/null | wc -l)
if [ "$N24" -ge 6 ]; then
  say "ALERT: $N24 relaunches in 24 h; not relaunched (check logs/$SESSION.log)"
  echo "$(date '+%F %T') crash loop: $N24 relaunches in 24 h" > "$OPS/ALERT"; exit 0
fi
[ -n "$GUARD_DRYRUN" ] && { say "DRYRUN: would relaunch $SESSION"; exit 0; }
if ! curl -s -m 3 -o /dev/null http://127.0.0.1:3082/v3/version; then
  nohup "$HOME/.gns3_venv/bin/gns3server" --local --logfile="$HOME/.config/GNS3/3.0/gns3_server.log" --pid="$HOME/.config/GNS3/3.0/gns3_server.pid" >/dev/null 2>&1 &
  say "gns3server started (PID $!)"; sleep 20
fi
cd "$SC" || exit 0
if ! timeout 1200 python3 prep_session.py >> "$OPS/prep.log" 2>&1; then say "prep_session FAILED (see ops/prep.log); not relaunched"; exit 0; fi
nohup gnome-session-inhibit --inhibit suspend:idle --reason "QoS $SESSION" python3 -u campaign.py "$SESSION" >> "$SLOG" 2>&1 &
sleep 5
NP="$(ps -eo pid,args | awk -v s="$SESSION" '$2 ~ /python3/ && $4=="campaign.py" && $5==s {print $1}' | head -1)"
echo "$NP" > "$PIDF"
if [ -n "$NP" ]; then say "relaunched $SESSION, PID $NP"; else say "FAILED to relaunch $SESSION"; fi
