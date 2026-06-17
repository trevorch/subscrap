#!/usr/bin/env python3
"""
sub1/v2ray.py
为单个 VLESS 节点生成完整的 v2ray-core JSON 配置。

本地架构：
  socks5 入站 (127.0.0.1:<socks_port>)  ──▶  VLESS 出站  ──▶  远端节点
"""
from __future__ import annotations

import json
from .parser import Node

PROBE_HOST = "connectivitycheck.gstatic.com"
PROBE_PORT = 80


def build(node: Node, socks_port: int) -> dict:
    vless_user: dict = {"id": node.uuid, "encryption": "none"}
    if node.flow:
        vless_user["flow"] = node.flow

    net = node.network
    stream: dict = {"network": net}

    if net == "ws":
        stream["wsSettings"] = {
            "path": node.ws_path or "/",
            "headers": {"Host": node.ws_host or node.sni or node.host},
        }
    elif net == "grpc":
        stream["grpcSettings"] = {
            "serviceName": node.grpc_service or "",
            "multiMode": False,
        }
    elif net in ("http", "h2"):
        stream["network"] = "http"
        stream["httpSettings"] = {
            "path": node.http_path or "/",
            "host": [node.http_host or node.sni or node.host],
        }
    elif net == "httpupgrade":
        stream["httpupgradeSettings"] = {
            "path": node.ws_path or "/",
            "host": node.ws_host or node.sni or node.host,
        }
    elif net == "quic":
        stream["quicSettings"] = {
            "security": "none", "key": "",
            "header": {"type": "none"},
        }

    if node.security == "tls":
        stream["security"] = "tls"
        stream["tlsSettings"] = {
            "serverName": node.sni or node.host,
            "allowInsecure": node.insecure,
            "fingerprint": node.fp or "chrome",
            "alpn": ["h2", "http/1.1"],
        }
    elif node.security == "reality":
        stream["security"] = "reality"
        stream["realitySettings"] = {
            "serverName": node.sni or node.host,
            "fingerprint": node.fp or "chrome",
            "publicKey": node.pbk,
            "shortId": node.sid,
            "spiderX": "",
        }
    else:
        stream["security"] = "none"

    return {
        "log": {"loglevel": "error"},
        "inbounds": [{
            "tag": "socks-in",
            "port": socks_port,
            "listen": "127.0.0.1",
            "protocol": "socks",
            "settings": {"auth": "noauth", "udp": False},
        }],
        "outbounds": [
            {
                "tag": "proxy",
                "protocol": "vless",
                "settings": {
                    "vnext": [{
                        "address": node.host,
                        "port": node.port,
                        "users": [vless_user],
                    }]
                },
                "streamSettings": stream,
            },
            {"tag": "direct", "protocol": "freedom"},
            {"tag": "block",  "protocol": "blackhole"},
        ],
        "routing": {
            "domainStrategy": "AsIs",
            "rules": [{"type": "field", "outboundTag": "proxy", "port": "0-65535"}],
        },
    }


def to_json(node: Node, socks_port: int) -> str:
    return json.dumps(build(node, socks_port), ensure_ascii=False)
