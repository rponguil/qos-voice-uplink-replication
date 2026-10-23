# Endpoint / Linux-router image for the F2 platform-viability tests.
FROM debian:bookworm-slim
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      iperf3 tcpdump iproute2 iputils-ping python3 snmp ethtool procps net-tools irtt \
    && rm -rf /var/lib/apt/lists/*
COPY udpprobe.py /usr/local/bin/udpprobe.py
CMD ["/bin/sh"]
