#!/usr/bin/env python3
"""
Proxy Chain Debug — 透明代理链路全栈诊断脚本
通过 Python 执行所有排查命令，输出结构化诊断报告。
"""

import subprocess
import json
import socket
import struct
import sys
import os
import re
from pathlib import Path
from datetime import datetime


def shell(cmd, timeout=15, sudo=False):
    """Run a shell command and return (output, exit_code)."""
    if sudo and os.geteuid() != 0:
        cmd = f"sudo {cmd}"
    try:
        r = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        out = (r.stdout + "\n" + r.stderr).strip()
        return out, r.returncode
    except subprocess.TimeoutExpired:
        return f"[TIMEOUT after {timeout}s]", -1
    except Exception as e:
        return f"[ERROR: {e}]", -1


def section(title):
    """Print a section header."""
    sep = "=" * 60
    print(f"\n{sep}")
    print(f"  {title}")
    print(sep)


def subsection(title):
    print(f"\n--- {title} ---")


# ─────────────────────────────────────────────
# 1. System Info
# ─────────────────────────────────────────────
def check_system():
    section("1. System Info")
    out, _ = shell("uname -a")
    print(f"Kernel: {out.split(chr(10))[0]}")
    out, _ = shell("cat /etc/os-release 2>/dev/null | head -3")
    print(f"OS: {out}")
    out, _ = shell("hostname -I 2>/dev/null || hostname")
    print(f"IPs: {out}")


# ─────────────────────────────────────────────
# 2. DNS Resolution — 对比系统 DNS 与公共 DNS
# ─────────────────────────────────────────────
def check_dns():
    section("2. DNS Resolution")

    # System resolv.conf
    subsection("System DNS Config")
    out, _ = shell("cat /etc/resolv.conf 2>/dev/null")
    print(out or "[no resolv.conf]")

    # Test domains
    domains = ["www.google.com", "www.youtube.com", "github.com", "httpbin.org"]
    dns_servers = {
        "System": None,
        "8.8.8.8": "@8.8.8.8",
        "1.1.1.1": "@1.1.1.1",
    }

    for domain in domains:
        subsection(f"DNS: {domain}")
        for name, server_arg in dns_servers.items():
            cmd = f"dig +short {server_arg} {domain} 2>/dev/null" if server_arg \
                  else f"host {domain} 2>/dev/null | grep 'has address' | head -3"
            out, _ = shell(cmd)
            ips = out.strip() or "[no result]"
            print(f"  {name:>10}: {ips}")

    # Check DNS poisoning via nslookup comparison
    subsection("DNS Comparison (nslookup)")
    for domain in ["www.google.com", "www.youtube.com"]:
        out, _ = shell(f"nslookup {domain} 2>&1 | grep -E '(Address|Name)' | head -5")
        print(f"  {domain}:")
        for line in out.split("\n"):
            print(f"    {line}")


# ─────────────────────────────────────────────
# 3. Network & Routing
# ─────────────────────────────────────────────
def check_routing():
    section("3. Network & Routing")

    subsection("Default Route")
    out, _ = shell("ip route show default")
    print(out or "[no default route]")

    subsection("IP Rules (fwmark)")
    out, _ = shell("ip rule show | head -20")
    print(out or "[no rules]")

    subsection("Route Table 52 (v2raya)")
    out, _ = shell("ip route show table 52")
    print(out or "[empty]")

    # Interface info
    subsection("Network Interfaces")
    out, _ = shell("ip -br addr | grep -v lo")
    print(out)


# ─────────────────────────────────────────────
# 4. nftables — 透明代理规则验证
# ─────────────────────────────────────────────
def check_nftables():
    section("4. nftables Transparent Proxy Rules")

    subsection("table inet v2raya (v2raya transparent proxy)")
    out, _ = shell("nft list table inet v2raya 2>&1")
    if out and "No such file or directory" not in out:
        # Check if whitelist has 192.168.0.0/16
        if "192.168.0.0/16" in out:
            print("  [OK] whitelist includes 192.168.0.0/16 (LAN bypass)")
        else:
            print("  [WARN] 192.168.0.0/16 NOT in whitelist — LAN traffic may be intercepted!")
        if "redirect to :52345" in out:
            print("  [OK] TCP redirect to port 52345 (xray transparent proxy)")
        else:
            print("  [FAIL] No redirect rule to port 52345!")
        # Show rule context
        for line in out.split("\n"):
            if any(kw in line for kw in ["redirect", "whitelist", "return", "mark"]):
                print(f"  {line.strip()}")
    else:
        print("  [FAIL] table inet v2raya not found!")
        print(f"  Raw: {out[:500]}")

    subsection("table ip proxy (alternate proxy redirect)")
    out, _ = shell("nft list table ip proxy 2>&1")
    if out and "No such file" not in out:
        redirect_port = None
        for line in out.split("\n"):
            if "redirect to" in line:
                redirect_port = line.strip()
        print(f"  Found: {redirect_port or 'no redirect rule'}")
        # Check if anything listens on that port
        if redirect_port:
            port_match = re.search(r":(\d+)", redirect_port)
            if port_match:
                port = port_match.group(1)
                listen_check, _ = shell(f"ss -tlnp | grep -w {port}")
                if listen_check:
                    print(f"  [OK] Port {port} has listener")
                else:
                    print(f"  [WARN] Port {port} has NO listener — traffic redirected here will fail!")
    else:
        print("  [not present]")

    # Show all nftables tables (brief)
    subsection("All nftables tables")
    out, _ = shell("nft list tables 2>&1")
    print(out or "[no tables]")


# ─────────────────────────────────────────────
# 5. Listening Ports — v2raya/xray
# ─────────────────────────────────────────────
def check_listeners():
    section("5. Listening Ports (v2raya / xray)")

    subsection("xray listeners")
    out, _ = shell("ss -tlnp | grep xray")
    print(out or "[no xray listeners found]")

    subsection("v2raya listener")
    out, _ = shell("ss -tlnp | grep v2raya")
    print(out or "[no v2raya process found]")


# ─────────────────────────────────────────────
# 6. v2raya Service Status
# ─────────────────────────────────────────────
def check_v2raya_service():
    section("6. v2raya Service Status")

    subsection("Service Status")
    out, _ = shell("systemctl is-active v2raya 2>&1")
    print(f"  Active: {out}")

    out, _ = shell("systemctl is-enabled v2raya 2>&1")
    print(f"  Enabled: {out}")

    subsection("Recent v2raya Access Log (last 20 lines)")
    # Access log is in v2raya's log file
    out, _ = shell("tail -20 /var/log/v2raya/v2raya.log 2>/dev/null || echo '[no log file]'")
    print(out)

    subsection("Journalctl Errors")
    out, _ = shell("journalctl -u v2raya --no-pager -n 50 2>&1 | grep -i -E '(warn|error|fail)' | tail -10")
    print(out or "[no errors]")


# ─────────────────────────────────────────────
# 7. xray Config — 检查关键路由规则
# ─────────────────────────────────────────────
def check_xray_config():
    section("7. xray Routing Config")

    subsection("Outbounds")
    out, _ = shell("cat /etc/v2raya/config.json 2>/dev/null | python3 -c \"import sys,json; c=json.load(sys.stdin); [print(f'  {o.get(chr(116)+chr(97)+chr(103))}: {o.get(chr(112)+chr(114)+chr(111)+chr(116)+chr(111)+chr(99)+chr(111)+chr(108))} -> {json.dumps(o.get(chr(115)+chr(101)+chr(116)+chr(116)+chr(105)+chr(110)+chr(103)+chr(115),{}))}') for o in c.get(chr(111)+chr(117)+chr(116)+chr(98)+chr(111)+chr(117)+chr(110)+chr(100)+chr(115),[])]\" 2>&1")
    if "[Errno" not in out and "Traceback" not in out:
        print(out)
    else:
        out, _ = shell("sudo cat /etc/v2raya/config.json 2>/dev/null | python3 -c \"import sys,json; c=json.load(sys.stdin); [print(f'  {o[chr(116)+chr(97)+chr(103)]}: {o[chr(112)+chr(114)+chr(111)+chr(116)+chr(111)+chr(99)+chr(111)+chr(108)]} -> {json.dumps(o[chr(115)+chr(101)+chr(116)+chr(116)+chr(105)+chr(110)+chr(103)+chr(115)])}') for o in c[chr(111)+chr(117)+chr(116)+chr(98)+chr(111)+chr(117)+chr(110)+chr(100)+chr(115)]]\" 2>&1")
        if "Traceback" in out:
            # Fallback: try without python
            out, _ = shell("sudo cat /etc/v2raya/config.json 2>/dev/null | python3 -c 'import sys,json;c=json.load(sys.stdin);[print(f\"  {o[chr(116)+chr(97)+chr(103)]}: {o[chr(112)+chr(114)+chr(111)+chr(116)+chr(111)+chr(99)+chr(111)+chr(108)]}\") for o in c[chr(111)+chr(117)+chr(116)+chr(98)+chr(111)+chr(117)+chr(110)+chr(100)+chr(115)]]' 2>&1")
        print(out)

    # Check routing rules for google
    subsection("Google routing rule")
    out, _ = shell("sudo grep -o '\"proxy\".*google' /etc/v2raya/config.json 2>/dev/null || grep -o 'geosite:google' /etc/v2raya/config.json 2>/dev/null")
    print(f"  geosite:google -> proxy: {'found' if 'google' in out else 'NOT FOUND'}")


# ─────────────────────────────────────────────
# 8. win-proxy Connectivity — SOCKS5 直测
# ─────────────────────────────────────────────
def test_socks5_proxy(host, port, target_host, target_port, timeout_sec=8):
    """Test SOCKS5 proxy connectivity and return (success, detail)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout_sec)
        s.connect((host, port))

        # SOCKS5 auth negotiation
        s.send(b"\x05\x01\x00")
        resp = s.recv(2)
        if resp[0] != 5 or resp[1] != 0:
            s.close()
            return False, f"Auth failed: {resp.hex()}"

        # SOCKS5 CONNECT
        hostname = target_host.encode()
        req = b"\x05\x01\x00\x03" + bytes([len(hostname)]) + hostname + \
              target_port.to_bytes(2, "big")
        s.send(req)
        resp = s.recv(10)
        if resp[1] != 0:
            s.close()
            return False, f"Connect rejected (status {resp[1]}): {resp.hex()}"

        # Send HTTP GET (for HTTP targets)
        if target_port == 80:
            http_req = f"GET / HTTP/1.0\r\nHost: {target_host}\r\nConnection: close\r\n\r\n"
            s.send(http_req.encode())
            data = b""
            while True:
                try:
                    chunk = s.recv(4096)
                    if not chunk:
                        break
                    data += chunk
                except socket.timeout:
                    break
            s.close()
            if data:
                return True, f"Got {len(data)} bytes of response"
            else:
                return False, "Connected but received 0 bytes"
        elif target_port == 443:
            # For HTTPS, do a TLS handshake test
            import ssl as ssl_mod
            try:
                ctx = ssl_mod.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl_mod.CERT_NONE
                ss = ctx.wrap_socket(s, server_hostname=target_host)
                ss.do_handshake()
                cert = ss.getpeercert()
                ss.close()
                return True, f"TLS handshake OK, cert: {(cert.get('subject', ((('CN', '?'),),)))[0][0][1]}"
            except Exception as e:
                s.close()
                return False, f"TLS handshake failed: {e}"
        else:
            s.close()
            return True, f"TCP connected to {target_host}:{target_port}"
    except socket.timeout:
        return False, f"Connection timed out ({timeout_sec}s)"
    except ConnectionRefusedError:
        return False, "Connection refused"
    except Exception as e:
        return False, str(e)


def check_win_proxy():
    section("8. win-proxy SOCKS5 Proxy Test")

    # Resolve win-proxy
    subsection("win-proxy Resolution")
    try:
        ip = socket.gethostbyname("win-proxy")
        print(f"  win-proxy -> {ip}")
    except socket.gaierror:
        print("  [FAIL] Cannot resolve win-proxy!")
        return

    # Ping test
    subsection("Ping")
    out, _ = shell("ping -c 2 -W 2 win-proxy 2>&1 | tail -1")
    print(f"  {out}")

    # SOCKS5 proxy tests
    test_targets = [
        ("httpbin.org", 80, "HTTP"),
        ("www.google.com", 443, "HTTPS"),
        ("1.1.1.1", 443, "HTTPS (Cloudflare)"),
    ]

    subsection("SOCKS5 Tests (win-proxy:7890)")
    for target_host, target_port, label in test_targets:
        print(f"\n  -> {target_host}:{target_port} ({label})")
        success, detail = test_socks5_proxy("win-proxy", 7890, target_host, target_port)
        status = "OK" if success else "FAIL"
        print(f"     [{status}] {detail}")


# ─────────────────────────────────────────────
# 9. Direct Internet Connectivity
# ─────────────────────────────────────────────
def check_direct_connectivity():
    section("9. Direct Internet Connectivity (Bypass Proxy)")

    # Test 1.1.1.1:443 (non-http port to avoid transparent proxy effects)
    subsection("HTTPS to 1.1.1.1:443")
    try:
        import ssl as ssl_mod
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(8)
        s.connect(("1.1.1.1", 443))
        ctx = ssl_mod.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl_mod.CERT_NONE
        ss = ctx.wrap_socket(s, server_hostname="1.1.1.1")
        ss.do_handshake()
        ss.close()
        print(f"  [OK] TLS handshake successful")
    except socket.timeout:
        print(f"  [FAIL] Connection timed out (8s)")
    except ConnectionRefusedError:
        print(f"  [FAIL] Connection refused")
    except Exception as e:
        print(f"  [FAIL] {e}")

    # Test raw TCP to common ports
    subsection("Raw TCP to known hosts")
    test_hosts = [
        ("1.1.1.1", 80, "Cloudflare HTTP"),
        ("8.8.8.8", 443, "Google DNS HTTPS"),
        ("185.45.5.35", 443, "Google (polluted IP)"),
    ]
    for host, port, label in test_hosts:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(5)
            s.connect((host, port))
            s.close()
            print(f"  [OK] {label} ({host}:{port}) — TCP connected")
        except socket.timeout:
            print(f"  [FAIL] {label} ({host}:{port}) — TIMEOUT")
        except ConnectionRefusedError:
            print(f"  [FAIL] {label} ({host}:{port}) — REFUSED")
        except Exception as e:
            print(f"  [FAIL] {label} ({host}:{port}) — {e}")


# ─────────────────────────────────────────────
# 10. Summary & Diagnosis
# ─────────────────────────────────────────────
def summary():
    section("10. Diagnosis Summary")

    simple_checks = [
        ("v2raya service", "systemctl is-active v2raya", "active"),
        ("nftables v2raya rules", "nft list table inet v2raya 2>&1", "redirect to :52345"),
        ("xray listening on 52345", "ss -tlnp | grep 52345", "LISTEN"),
        ("win-proxy reachable", "ping -c 1 -W 2 win-proxy", "1 received"),
    ]

    passed = 0
    total = len(simple_checks) + 1  # +1 for socks test

    for name, cmd, expect in simple_checks:
        out, _ = shell(cmd)
        ok = expect in out
        if ok:
            passed += 1
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")

    # SOCKS5 test check
    socks_ok, _ = test_socks5_proxy("win-proxy", 7890, "httpbin.org", 80, timeout_sec=6)
    if socks_ok:
        passed += 1
    print(f"  [{'PASS' if socks_ok else 'FAIL'}] SOCKS5 to httpbin.org:80 via win-proxy")
    print(f"\n  Score: {passed}/{total} checks passed")

    if passed < total:
        print("\n  Likely Root Cause:")
        if not socks_ok:
            print("    >> win-proxy (or its Clash/upstream) cannot reach the internet")
        dns_fail, _ = shell("nslookup www.google.com 2>&1 | grep -c '185.45.5.35'")
        if "1" in dns_fail:
            print("    >> DNS is returning polluted IPs (185.45.5.35 for google.com)")
        print("\n  Recommended next steps:")
        print("    1. Check if win-proxy's Clash/Clash Verge proxy nodes are alive")
        print("    2. On win-proxy, run: curl -v https://www.google.com")
        print("    3. Check win-proxy's gateway and internet connectivity")
        print("    4. Restart xray: sudo systemctl restart v2raya")


if __name__ == "__main__":
    print(f"Proxy Chain Diagnostic Report")
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Host: {socket.gethostname()}")

    check_system()
    check_dns()
    check_routing()
    check_nftables()
    check_listeners()
    check_v2raya_service()
    check_xray_config()
    check_win_proxy()
    check_direct_connectivity()
    summary()