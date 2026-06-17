#!/usr/bin/env python3
"""
sub1.py — VLESS 节点 v2ray-core 完整握手检测

每个节点的流程：
  1. 写临时 v2ray JSON 配置（socks5 入站✗✗ + VLESS 出站）
  2. 启动 v2ray-core 子进程
  3. 轮询等待 socks5 端口就绪（≤3s）
  4. 纯标准库实现 SOCKS5 握手 → HTTP GET 探测地址
  5. 收到 HTTP 响应 → 成功；否则 → 失败
  6. 终止子进程，清理临时目录，归还端口

并发：线程池，默认 30 个并发（v2ray 进程较重）。
输出：sub1.txt，每行一个裸 vless:// URI。
"""
from __future__ import annotations

import argparse
import concurrent.futures
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import re
import requests
from datetime import datetime
from urllib.parse import urlparse, urlunparse
from pathlib import Path

_ROOT = Path(__file__).parent
sys.path.insert(0, str(_ROOT))

from sub1.parser import load_dir, Node
from sub1.v2ray import to_json, PROBE_HOST, PROBE_PORT

# ── 默认参数 ──────────────────────────────────────────────────────────────────
DEFAULT_V2RAY     = shutil.which("v2ray") or "/usr/local/bin/v2ray"
DEFAULT_VLESS_DIR = str(_ROOT / "separated-protocols-chunks" / "vless")
DEFAULT_OUTPUT    = str(_ROOT / "sub1.txt")
DEFAULT_WORKERS   = 80
DEFAULT_TIMEOUT   = 10
PORT_BASE         = 20000
PORT_RANGE        = 5000

# ── 端口池（线程安全） ────────────────────────────────────────────────────────
_port_lock = threading.Lock()
_port_pool: list[int] = list(range(PORT_BASE, PORT_BASE + PORT_RANGE))


def _alloc_port() -> int:
    with _port_lock:
        while not _port_pool:
            time.sleep(0.05)
        return _port_pool.pop()


def _free_port(p: int):
    with _port_lock:
        _port_pool.append(p)


# ── 进度计数器 ────────────────────────────────────────────────────────────────
_print_lock = threading.Lock()
_done = 0
_ok   = 0


def _tick(total: int, success: bool, label: str, reason: str):
    global _done, _ok
    with _print_lock:
        _done += 1
        _ok   += success
        sym    = "🟢" if success else "🔴"
        pct    = _done / total * 100
        print(f"  [{_done:5d}/{total} {pct:5.1f}%] {sym} {label}  →  {reason}", flush=True)


# ── 等待端口就绪 ──────────────────────────────────────────────────────────────

def _wait_port(port: int, deadline: float) -> bool:
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return True
        except OSError:
            time.sleep(0.1)
    return False


# ── SOCKS5 + HTTP 探测（纯标准库） ───────────────────────────────────────────

def _probe_via_socks5(proxy_port: int, host: str, port: int, timeout: float) -> tuple[bool, str]:
    sock = None
    try:
        sock = socket.create_connection(("127.0.0.1", proxy_port), timeout=timeout)
        sock.settimeout(timeout)

        # SOCKS5 协商：无认证
        sock.sendall(b"\x05\x01\x00")
        r = sock.recv(2)
        if len(r) < 2 or r[0] != 5 or r[1] != 0:
            return False, f"SOCKS5协商失败:{r.hex()}"

        # CONNECT 目标
        host_b = host.encode()
        sock.sendall(
            b"\x05\x01\x00\x03"
            + bytes([len(host_b)]) + host_b
            + port.to_bytes(2, "big")
        )

        buf = b""
        while len(buf) < 10:
            chunk = sock.recv(64)
            if not chunk:
                break
            buf += chunk
        if len(buf) < 2 or buf[1] != 0x00:
            rep = buf[1] if len(buf) > 1 else -1
            return False, f"SOCKS5 CONNECT 失败(REP=0x{rep:02x})"

        # HTTP GET
        sock.sendall((
            f"GET / HTTP/1.1\r\n"
            f"Host: {host}\r\n"
            f"User-Agent: curl/8.0\r\n"
            f"Connection: close\r\n\r\n"
        ).encode())

        resp = b""
        deadline2 = time.monotonic() + timeout
        while b"\r\n" not in resp and time.monotonic() < deadline2:
            try:
                chunk = sock.recv(512)
                if not chunk:
                    break
                resp += chunk
            except socket.timeout:
                break

        first = resp.split(b"\r\n")[0].decode(errors="replace")
        if first.startswith("HTTP/"):
            code = first.split(" ", 2)[1] if " " in first else "?"
            return True, f"HTTP {code}"
        return False, f"非HTTP响应:{first[:40]!r}"

    except socket.timeout:
        return False, "超时"
    except ConnectionRefusedError:
        return False, "连接被拒绝"
    except OSError as e:
        return False, f"OS:{e.strerror}"
    except Exception as e:
        return False, f"{type(e).__name__}:{e}"
    finally:
        if sock:
            try:
                sock.close()
            except Exception:
                pass


# ── 单节点测试 ────────────────────────────────────────────────────────────────

def _test_node(node: Node, v2ray_bin: str, timeout: float) -> tuple[Node, bool, str]:
    port    = _alloc_port()
    tmp_dir = tempfile.mkdtemp(prefix="vp_")
    cfg     = os.path.join(tmp_dir, "config.json")
    proc    = None
    try:
        with open(cfg, "w", encoding="utf-8") as f:
            f.write(to_json(node, port))

        proc = subprocess.Popen(
            [v2ray_bin, "run", "-config", cfg],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            preexec_fn=os.setsid if hasattr(os, "setsid") else None,
        )

        deadline = time.monotonic() + timeout
        if not _wait_port(port, min(deadline, time.monotonic() + 3.0)):
            return node, False, "v2ray启动超时"

        remaining = max(1.0, deadline - time.monotonic())
        ok, reason = _probe_via_socks5(port, PROBE_HOST, PROBE_PORT, remaining)
        return node, ok, reason

    except FileNotFoundError:
        return node, False, f"v2ray未找到:{v2ray_bin}"
    except Exception as e:
        return node, False, f"内部错误:{e}"
    finally:
        if proc:
            try:
                if hasattr(os, "killpg"):
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                else:
                    proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        shutil.rmtree(tmp_dir, ignore_errors=True)
        _free_port(port)

def extract_ip_and_port(vless_link):
    """从 VLESS 链接中提取服务器 IP/域名和端口"""
    # 正则匹配 vless://uuid@ip:port 中的 ip 和 port
    match = re.search(r'vless://.*?@(.*?):(\d+)', vless_link)
    if match:
        return match.group(1), match.group(2)
    return None, None

def get_country_name(ip):
    """查询 IP 归属地并返回国家名称"""
    try:
        url = f"http://ip-api.com/json/{ip}?lang=zh-CN"
        resp = requests.get(url, timeout=5)
        data = resp.json()
        
        if data.get('status') == 'success':
            return data.get('country', '未知')
        else:
            return '未知'
    except Exception as e:
        print(f"⚠️ IP查询失败 ({ip}): {e}")
        return '未知'

def rename_vless_node(raw_link):
    """重命名 VLESS 节点，将 # 后的备注改为 【国家(IP:端口)】|当前日期"""
    ip, port = extract_ip_and_port(raw_link)
    
    # 如果无法解析出 IP 或端口，直接返回原链接
    if not ip or not port:
        return raw_link 
        
    country = get_country_name(ip)
    current_date = datetime.now().strftime("%-m月%-d日")
    
    # 构造新的 fragment (即 # 后面的内容)
    new_fragment = f"【{country}({ip}:{port})】{current_date}"
    
    # 解析 URL 的各个组成部分
    parsed_url = urlparse(raw_link)
    
    # 使用 _replace 方法更新 fragment，并重新组合成完整的 URL
    new_parsed_url = parsed_url._replace(fragment=new_fragment)
    new_link = urlunparse(new_parsed_url)
    
    return new_link


# ── 主程序 ────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="VLESS 节点 v2ray-core 握手检测")
    ap.add_argument("--dir",     default=DEFAULT_VLESS_DIR)
    ap.add_argument("--out",     default=DEFAULT_OUTPUT)
    ap.add_argument("--v2ray",   default=DEFAULT_V2RAY)
    ap.add_argument("--workers", type=int,   default=DEFAULT_WORKERS)
    ap.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    args = ap.parse_args()

    vless_dir = Path(args.dir)
    out_file  = Path(args.out)

    if not vless_dir.exists():
        sys.exit(f"[错误] 目录不存在: {vless_dir}")
    if not Path(args.v2ray).exists():
        sys.exit(f"[错误] v2ray 未找到: {args.v2ray}")

    # 清空输出文件（防止旧数据残留）
    out_file.write_text("", encoding="utf-8")
    print(f"[信息] 已清空: {out_file}")

    # 加载节点
    nodes = load_dir(vless_dir)
    total = len(nodes)
    print(f"[信息] 发现节点: {total} 个")
    if not total:
        print("[警告] 无节点，退出。")
        return

    print(f"[信息] 开始检测 (workers={args.workers}, timeout={args.timeout}s)\n")
    
    # 核心改动 1：移除 valid 列表，改用计数器统计成功数量
    success_count = 0
    write_lock = threading.Lock()  # 核心改动 2：初始化线程锁，保障写入安全
    
    t0 = time.monotonic()

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(_test_node, n, args.v2ray, args.timeout): n for n in nodes}
        
        for fut in concurrent.futures.as_completed(futs):
            node, ok, reason = fut.result()
            label = f"{node.host}:{node.port} [{node.security}/{node.network}]"
            _tick(total, ok, label, reason)
            
            if ok:
                success_count += 1
                # 核心改动 3：测通一个，立即加锁追加写入一个
                with write_lock:
                    # 探测并重命名节点
                    renamed_raw = rename_vless_node(node.raw)
                    with open(out_file, "a", encoding="utf-8") as f:
                        f.write(renamed_raw + "\n")
                        f.flush() # 强制刷入磁盘，确保程序中途崩溃也不丢数据

    elapsed = time.monotonic() - t0

    # 打印最终统计报告
    print(f"\n{'═'*60}")
    print(f"  输出文件 : {out_file}")
    print(f"  总节点数 : {total}")
    print(f"  握手成功 : {success_count}  ({success_count/total*100:.1f}%)")
    print(f"  握手失败 : {total - success_count}")
    print(f"  耗时     : {elapsed:.1f}s")
    print(f"{'═'*60}")


if __name__ == "__main__":
    main()
