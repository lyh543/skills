---
name: proxy-chain-debug
description: >
  Diagnose why transparent proxy (v2raya/xray + upstream SOCKS5 proxy) cannot
  reach external internet. Runs all checks via a single Python script that
  tests DNS resolution, nftables rules, xray listeners, SOCKS5 proxy
  connectivity, and direct internet access. No manual CLI commands needed.
category: devops
---

# Proxy Chain Debug

Debug a broken v2raya transparent proxy chain. The single Python script at
`scripts/diagnose.py` automates all checks — run it and read the structured
report to pinpoint the failure point.

## When to Use

- "我上不了谷歌" / "curl 不了 Google"
- v2raya 透明代理异常，网页打不开
- 通过 win-proxy 代理失败，Empty reply from server
- 需要快速定位透明代理链路中哪个环节断了

## How to Use

Run the diagnostic script directly:

```bash
sudo python3 scripts/diagnose.py
```

The script requires `sudo` access to read nftables rules, xray config, and
systemctl status. It will produce a structured report with all findings and a
summary.

## What It Checks

| # | Check | Method |
|---|-------|--------|
| 1 | System info | `uname -a`, `/etc/os-release` |
| 2 | DNS resolution | `dig` to 8.8.8.8, 1.1.1.1, system DNS — compares IPs |
| 3 | Routing & fwmark rules | `ip route`, `ip rule`, table 52 |
| 4 | nftables transparent proxy | `table inet v2raya` — verifies redirect to :52345 |
| 5 | Listening ports | `ss` — checks xray/v2raya listeners |
| 6 | v2raya service | systemctl status + log tail |
| 7 | xray routing config | Reads /etc/v2raya/config.json for proxy outbound |
| 8 | SOCKS5 proxy test | Raw Python SOCKS5 client — tests win-proxy:7890 |
| 9 | Direct connectivity | Raw TCP to 1.1.1.1, 8.8.8.8 etc. |
| 10 | Diagnosis summary | Pass/fail tally + root cause suggestion |

## Typical Failure Patterns

**Pattern 1: Everything works except SOCKS5 → "Connected but received 0 bytes"**
→ win-proxy (Clash/Clash Verge) has no working proxy nodes
→ Fix: restart Clash / update subscription / check node status on win-proxy

**Pattern 2: Direct TCP tests time out**
→ Server's default gateway or ISP is blocking outbound TCP
→ Check: `ip route show default`, try different port / protocol

**Pattern 3: DNS resolves to 185.45.5.35 for google.com**
→ DNS pollution (normal in China) — not a problem IF the proxy works
→ If SOCKS5 also fails, see Pattern 1

**Pattern 4: nftables has `table ip proxy` but no listener on port 12345**
→ Stale redsocks rules; the v2raya table takes priority so this is usually harmless

## Dependencies

- Python 3 standard library only (socket, subprocess, json, re)
- `sudo` access for reading configs and nftables
- `dig` and `nslookup` for DNS checks (fallback: Python socket)
- `nft` for nftables inspection
- `ss` for socket statistics

## File Structure

```
proxy-chain-debug/
├── SKILL.md
└── scripts/
    └── diagnose.py    # everything runs from here
```