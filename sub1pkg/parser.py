#!/usr/bin/env python3
"""
sub1/parser.py
解析 VLESS 订阅文件，支持明文 URI、整体 Base64、逐行 Base64。
"""
from __future__ import annotations

import base64
import urllib.parse
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Node:
    raw: str           # 原始 vless:// URI，写入结果文件
    uuid: str
    host: str
    port: int
    security: str      # none | tls | reality
    sni: str
    fp: str            # TLS fingerprint
    insecure: bool
    pbk: str           # reality publicKey
    sid: str           # reality shortId
    network: str       # tcp | ws | grpc | http | quic | httpupgrade
    ws_host: str
    ws_path: str
    grpc_service: str
    http_path: str
    http_host: str
    flow: str
    remark: str

    @property
    def use_tls(self) -> bool:
        return self.security in ("tls", "reality")

    def __hash__(self):
        # 使用参与比较的不可变字段来计算哈希值
        return hash((self.uuid, self.host, self.port))

    def __eq__(self, other):
        # 确保两个对象类型一致且关键字段完全相同
        if isinstance(other, Node):
            return (self.uuid, self.host, self.port) == (other.uuid, other.host, other.port)
        return False


def _b64(s: str) -> str:
    s = s.strip().replace("-", "+").replace("_", "/")
    pad = (-len(s)) % 4
    try:
        return base64.b64decode(s + "=" * pad).decode("utf-8", errors="ignore")
    except Exception:
        return ""


def parse_uri(raw: str) -> Node | None:
    raw = raw.strip()
    if not raw.lower().startswith("vless://"):
        return None
    try:
        remark = ""
        uri = raw
        if "#" in uri:
            uri, remark = uri.rsplit("#", 1)
            remark = urllib.parse.unquote(remark)

        body = uri[len("vless://"):]
        at = body.rfind("@")
        if at == -1:
            return None

        uuid_str = body[:at]
        rest = body[at + 1:]
        addr_part, _, param_str = rest.partition("?")

        if addr_part.startswith("["):           # IPv6
            end = addr_part.index("]")
            host = addr_part[1:end]
            port_s = addr_part[end + 2:]
        else:
            host, _, port_s = addr_part.rpartition(":")

        port = int(port_s)
        if not 1 <= port <= 65535:
            return None

        p = dict(urllib.parse.parse_qsl(param_str, keep_blank_values=True))
        security = p.get("security", "none").lower()
        network  = p.get("type", p.get("network", "tcp")).lower()
        sni      = p.get("sni") or p.get("serverName") or host

        return Node(
            raw=raw, uuid=uuid_str, host=host, port=port,
            security=security, sni=sni,
            fp=p.get("fp", p.get("fingerprint", "chrome")),
            insecure=p.get("allowInsecure", "0") in ("1", "true"),
            pbk=p.get("pbk", p.get("publicKey", "")),
            sid=p.get("sid", p.get("shortId", "")),
            network=network,
            ws_host=p.get("host", ""),
            ws_path=urllib.parse.unquote(p.get("path", "/")),
            grpc_service=p.get("serviceName", ""),
            http_path=urllib.parse.unquote(p.get("path", "/")),
            http_host=p.get("host", ""),
            flow=p.get("flow", ""),
            remark=remark,
        )
    except Exception:
        return None


def _extract_uris(text: str) -> list[str]:
    uris: list[str] = []

    def _scan(t: str):
        for line in t.splitlines():
            s = line.strip()
            if s.lower().startswith("vless://"):
                uris.append(s)

    _scan(text)
    if not uris:
        decoded = _b64(text)
        if "vless://" in decoded.lower():
            _scan(decoded)
    if not uris:
        for line in text.splitlines():
            d = _b64(line.strip())
            if d.lower().startswith("vless://"):
                uris.append(d.strip())
    return uris


def load_file(path: str | Path) -> list[Node]:
    try:
        text = Path(path).read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    return [n for uri in _extract_uris(text) if (n := parse_uri(uri))]


def load_dir(directory: str | Path) -> list[Node]:
    seen: set[Node] = set()
    result: list[Node] = []
    
    for fp in sorted(Path(directory).rglob("*")):
        if not fp.is_file():
            continue
            
        for node in load_file(fp):
            # 直接利用 Node 对象的 __hash__ 和 __eq__ 进行去重判断
            if node not in seen:
                seen.add(node)
                result.append(node)
                
    return result