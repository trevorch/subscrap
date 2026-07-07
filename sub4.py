#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将 Clash 订阅 (yaml) 转换为通用代理 URI 列表。

用法:
    python3 clash2uri.py [订阅URL或本地文件路径] [-o 输出文件]

支持类型: http/https, socks5, ss, ssr, vmess, vless, trojan,
         hysteria, hysteria2, tuic, mieru(按题目给定示例格式转换)
"""

import argparse
import base64
import json
import sys
from urllib.parse import quote, urlencode

import requests
import yaml


def b64(s: str) -> str:
    """标准 base64 编码（不加 padding 的 = 也可以，这里保留 = 以兼容大多数客户端）"""
    return base64.b64encode(s.encode("utf-8")).decode("utf-8")


def qs(params: dict) -> str:
    """把 dict 转成 query string，过滤掉空值，并做 url 编码"""
    clean = {k: v for k, v in params.items() if v not in (None, "", [])}
    return urlencode(clean, quote_via=quote)


# --------------------------------------------------------------------------
# 各协议转换函数：每个函数接收 clash 的单个 proxy 字典，返回 URI 字符串
# --------------------------------------------------------------------------

def conv_http(p: dict) -> str:
    scheme = "https" if p.get("tls") else "http"
    userinfo = ""
    if p.get("username") or p.get("password"):
        userinfo = f"{quote(str(p.get('username', '')))}:{quote(str(p.get('password', '')))}@"
    name = quote(p.get("name", ""))
    return f"{scheme}://{userinfo}{p['server']}:{p['port']}#{name}"


def conv_socks5(p: dict) -> str:
    userinfo = ""
    if p.get("username") or p.get("password"):
        userinfo = f"{quote(str(p.get('username', '')))}:{quote(str(p.get('password', '')))}@"
    name = quote(p.get("name", ""))
    return f"socks5://{userinfo}{p['server']}:{p['port']}#{name}"


def conv_ss(p: dict) -> str:
    method = p.get("cipher", "")
    password = p.get("password", "")
    userinfo = b64(f"{method}:{password}").rstrip("=")
    name = quote(p.get("name", ""))
    params = {}
    if p.get("plugin"):
        plugin_opts = p.get("plugin-opts", {}) or {}
        opts_str = ";".join(f"{k}={v}" for k, v in plugin_opts.items() if v not in (None, ""))
        params["plugin"] = f"{p['plugin']};{opts_str}" if opts_str else p["plugin"]
    query = qs(params)
    query = f"?{query}" if query else ""
    return f"ss://{userinfo}@{p['server']}:{p['port']}{query}#{name}"


def conv_ssr(p: dict) -> str:
    # SSR: ssr://base64(server:port:protocol:method:obfs:base64pass/?params)
    params = qs({
        "obfsparam": b64(p.get("obfs-param", "")),
        "protoparam": b64(p.get("protocol-param", "")),
        "remarks": b64(p.get("name", "")),
    })
    password_b64 = b64(p.get("password", ""))
    main = (
        f"{p['server']}:{p['port']}:{p.get('protocol', 'origin')}:"
        f"{p.get('cipher', 'none')}:{p.get('obfs', 'plain')}:{password_b64}/?{params}"
    )
    return "ssr://" + b64(main).rstrip("=")


def conv_vmess(p: dict) -> str:
    ws_opts = p.get("ws-opts", {}) or {}
    grpc_opts = p.get("grpc-opts", {}) or {}
    network = p.get("network", "tcp")
    payload = {
        "v": "2",
        "ps": p.get("name", ""),
        "add": p.get("server", ""),
        "port": str(p.get("port", "")),
        "id": p.get("uuid", ""),
        "aid": str(p.get("alterId", 0)),
        "scy": p.get("cipher", "auto"),
        "net": network,
        "type": "none",
        "host": ws_opts.get("headers", {}).get("Host", p.get("servername", "")) if network == "ws" else p.get("servername", ""),
        "path": ws_opts.get("path", "") if network == "ws" else grpc_opts.get("grpc-service-name", ""),
        "tls": "tls" if p.get("tls") else "",
        "sni": p.get("servername", ""),
    }
    return "vmess://" + b64(json.dumps(payload, ensure_ascii=False))


def conv_vless(p: dict) -> str:
    reality_opts = p.get("reality-opts", {}) or {}
    ws_opts = p.get("ws-opts", {}) or {}
    grpc_opts = p.get("grpc-opts", {}) or {}
    network = p.get("network", "tcp")
    params = {
        "encryption": p.get("encryption", "none"),
        "security": "reality" if reality_opts else ("tls" if p.get("tls") else "none"),
        "sni": p.get("servername", ""),
        "fp": p.get("client-fingerprint", ""),
        "pbk": reality_opts.get("public-key", ""),
        "sid": reality_opts.get("short-id", ""),
        "type": network,
        "flow": p.get("flow", ""),
        "host": ws_opts.get("headers", {}).get("Host", ""),
        "path": ws_opts.get("path", "") if network == "ws" else grpc_opts.get("grpc-service-name", ""),
    }
    name = quote(p.get("name", ""))
    return f"vless://{p['uuid']}@{p['server']}:{p['port']}?{qs(params)}#{name}"


def conv_trojan(p: dict) -> str:
    ws_opts = p.get("ws-opts", {}) or {}
    network = p.get("network", "tcp")
    params = {
        "sni": p.get("sni", p.get("servername", "")),
        "allowInsecure": 1 if p.get("skip-cert-verify") else 0,
        "type": network,
        "host": ws_opts.get("headers", {}).get("Host", ""),
        "path": ws_opts.get("path", ""),
    }
    name = quote(p.get("name", ""))
    return f"trojan://{quote(p.get('password', ''))}@{p['server']}:{p['port']}?{qs(params)}#{name}"


def conv_hysteria(p: dict) -> str:
    params = {
        "auth": p.get("auth-str", p.get("auth", "")),
        "peer": p.get("sni", ""),
        "insecure": 1 if p.get("skip-cert-verify") else 0,
        "upmbps": p.get("up", ""),
        "downmbps": p.get("down", ""),
        "alpn": ",".join(p.get("alpn", [])) if p.get("alpn") else "",
        "protocol": p.get("protocol", ""),
    }
    name = quote(p.get("name", ""))
    return f"hysteria://{p['server']}:{p['port']}?{qs(params)}#{name}"


def conv_hysteria2(p: dict) -> str:
    params = {
        "sni": p.get("sni", ""),
        "insecure": 1 if p.get("skip-cert-verify") else 0,
        "obfs": p.get("obfs", ""),
        "obfs-password": p.get("obfs-password", ""),
    }
    name = quote(p.get("name", ""))
    return f"hysteria2://{quote(p.get('password', ''))}@{p['server']}:{p['port']}?{qs(params)}#{name}"


def conv_tuic(p: dict) -> str:
    params = {
        "sni": p.get("sni", ""),
        "alpn": ",".join(p.get("alpn", [])) if p.get("alpn") else "",
        "congestion_control": p.get("congestion-controller", ""),
        "udp_relay_mode": p.get("udp-relay-mode", ""),
        "allow_insecure": 1 if p.get("skip-cert-verify") else 0,
    }
    name = quote(p.get("name", ""))
    return f"tuic://{p.get('uuid', '')}:{quote(p.get('password', ''))}@{p['server']}:{p['port']}?{qs(params)}#{name}"


def conv_mieru(p: dict) -> str:
    """
    按题目给出的示例格式转换：
    mierus://username:password@server?multiplexing=...&port=...&profile=...&protocol=...
    示例:
    mierus://dongtaiwang.com:dongtaiwang.com@157.254.223.44?multiplexing=MULTIPLEXING_LOW
        &port=34567&profile=...&protocol=TCP
    """
    username = p.get("username", "")
    password = p.get("password", "")
    server = p.get("server", "")
    port = p.get("port", "")
    name = p.get("name", "")
    multiplexing = p.get("multiplexing", "")
    # clash 配置里对应字段是 transport（如 TCP/UDP），映射到 URI 的 protocol 参数
    protocol = p.get("transport", p.get("protocol", ""))

    params = {
        "multiplexing": multiplexing,
        "port": port,
        "profile": name,
        "protocol": protocol,
    }
    # 按 key 字母序排列，和示例保持一致
    query = urlencode(dict(sorted(params.items())), quote_via=quote)
    return f"mierus://{username}:{password}@{server}?{query}"


CONVERTERS = {
    "http": conv_http,
    "https": conv_http,
    "socks5": conv_socks5,
    "ss": conv_ss,
    "shadowsocks": conv_ss,
    "ssr": conv_ssr,
    "shadowsocksr": conv_ssr,
    "vmess": conv_vmess,
    "vless": conv_vless,
    "trojan": conv_trojan,
    "hysteria": conv_hysteria,
    "hysteria2": conv_hysteria2,
    "tuic": conv_tuic,
    "mieru": conv_mieru,
}


def load_clash_yaml(source: str) -> dict:
    if source.startswith("http://") or source.startswith("https://"):
        resp = requests.get(source, timeout=15)
        resp.raise_for_status()
        text = resp.text
    else:
        with open(source, "r", encoding="utf-8") as f:
            text = f.read()
    return yaml.safe_load(text)


def convert(source: str):
    data = load_clash_yaml(source)
    proxies = data.get("proxies") or []
    uris = []
    for p in proxies:
        ptype = (p.get("type") or "").lower()
        func = CONVERTERS.get(ptype)
        if not func:
            print(f"[跳过] 不支持的类型: {ptype} (name={p.get('name')})", file=sys.stderr)
            continue
        try:
            uris.append(func(p))
        except Exception as e:
            print(f"[错误] 转换失败 name={p.get('name')} type={ptype}: {e}", file=sys.stderr)
    return uris


def main():
    parser = argparse.ArgumentParser(description="Clash 订阅转 URI 列表")
    parser.add_argument(
        "source",
        nargs="?",
        default="https://raw.githubusercontent.com/shaoyouvip/free/refs/heads/main/all.yaml",
        help="Clash 订阅 URL 或本地 yaml 文件路径",
    )
    parser.add_argument("-o", "--output", help="输出文件路径，不指定则打印到标准输出")
    args = parser.parse_args()

    uris = convert(args.source)

    output_text = "\n".join(uris)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output_text + "\n")
        print(f"已写入 {len(uris)} 条 URI 到 {args.output}", file=sys.stderr)
    else:
        print(output_text)


if __name__ == "__main__":
    main()