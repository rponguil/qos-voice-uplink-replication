#!/bin/sh
# Sample MODEM eth2 queue every 20 ms: "<epoch> <backlog_pkts> <backlog_bytes>"
end=$(( $(date +%s) + $1 ))
while [ $(date +%s) -lt $end ]; do
  echo "$(date +%s.%N) $(tc -s qdisc show dev eth2 | sed -n 's/.*backlog \([0-9]*\)b \([0-9]*\)p.*/\2 \1/p')"
  sleep 0.02
done
