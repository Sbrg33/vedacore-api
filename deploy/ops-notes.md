Ops Notes: DO droplet running compose + Caddy

- ulimit: Increase file descriptors for SSE connections
  - Edit /etc/security/limits.conf and set: `* soft nofile 100000` and `* hard nofile 100000`
  - For systemd services, set `DefaultLimitNOFILE=100000` in `/etc/systemd/system.conf` then `systemctl daemon-reexec`

- sysctl: Basic tuning for many concurrent sockets
  - /etc/sysctl.d/99-vedacore.conf:
    - net.core.somaxconn = 4096
    - net.ipv4.ip_local_port_range = 2000 65000
    - net.ipv4.tcp_tw_reuse = 1
    - net.ipv4.tcp_fin_timeout = 15
  - Apply with `sysctl --system`

- UFW: minimal open ports
  - Allow SSH from your IP(s): `ufw allow from <YOUR_IP> to any port 22 proto tcp`
  - Allow Caddy origin port: `ufw allow 8081/tcp`
  - Deny all else: `ufw default deny incoming; ufw enable`
  - Optionally restrict 8081 to Cloudflare IPs only (long list; maintain periodically)

- Autostart on reboot
  - Use a systemd unit to run `docker compose up -d` in `/opt/vedacore/deploy`
  - Example unit: `/etc/systemd/system/vedacore-compose.service`
    - [Unit]\nDescription=VedaCore Compose Stack\nAfter=docker.service\nRequires=docker.service
    - [Service]\nType=oneshot\nWorkingDirectory=/opt/vedacore/deploy\nRemainAfterExit=yes\nExecStart=/usr/bin/docker compose up -d\nExecStop=/usr/bin/docker compose down
    - [Install]\nWantedBy=multi-user.target
  - `systemctl enable vedacore-compose && systemctl start vedacore-compose`

