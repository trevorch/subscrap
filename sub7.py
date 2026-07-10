#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sub7.py

功能：
1. 抓取 README.md 页面内容
2. 提取所有以 https://fn 开头的链接
3. 对每个链接中的域名，调用 zhanchacha.cn 的 DNS 查询接口获取对应 IP
4. 用查询到的 IP 替换掉原链接中的域名
5. 依次访问替换域名后的新链接，把返回内容写入 sub7.txt
"""

import base64
import re
import os
import socket
import sys
from contextlib import contextmanager
from urllib.parse import urlparse

import requests

SUB7_REPO = os.environ.get('SUB7_REPO')

README_URL = f"{SUB7_REPO}/refs/heads/main/README.md"
DNS_API = "https://zhanchacha.cn/api/dns/host2ip/"
OUTPUT_FILE = "sub7.txt"

# 匹配以 https://fn 开头的链接（直到空白字符结束）
LINK_PATTERN = re.compile(r"https://fn\S*")


def fetch_readme(url: str) -> str:
    """抓取 README.md 页面内容"""
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    return resp.text


def extract_fn_links(content: str):
    """提取所有以 https://fn 开头的链接（去重，保持顺序）"""
    links = LINK_PATTERN.findall(content)
    seen = set()
    result = []
    for link in links:
        # 去除末尾可能残留的标点符号（比如反引号、右括号等）
        link = link.rstrip("`)>,.\"'")
        if link not in seen:
            seen.add(link)
            result.append(link)
    return result


def query_ip(host: str) -> str:
    """调用 DNS 查询接口获取域名对应的 IP"""
    try:
        resp = requests.get(DNS_API, params={"host": host}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") == 1:
            ip = data.get("data", {}).get("ip")
            if ip:
                return ip
        print(f"[警告] 查询 {host} 的 IP 失败，返回数据: {data}", file=sys.stderr)
    except Exception as e:
        print(f"[错误] 查询 {host} 的 IP 时发生异常: {e}", file=sys.stderr)
    return None


def replace_host_with_ip(link: str, ip: str) -> str:
    """用 IP 替换链接中的域名部分"""
    parsed = urlparse(link)
    host = parsed.hostname
    new_netloc = parsed.netloc.replace(host, ip)
    new_link = link.replace(parsed.netloc, new_netloc, 1)
    return new_link


@contextmanager
def override_dns(hostname: str, ip: str):
    """
    临时劫持 DNS 解析：让 hostname 在本次请求中直接解析到指定 ip。
    这样可以保证 TLS 握手时的 SNI 以及 HTTP 的 Host 头都仍然是原始域名
    （从而通过服务器/CDN 的证书校验和路由判断），但底层 TCP 连接
    实际连接的是查询到的 ip —— 效果上等价于"用 ip 替换域名后访问"。
    """
    original_getaddrinfo = socket.getaddrinfo

    def patched_getaddrinfo(host, *args, **kwargs):
        if host == hostname:
            return original_getaddrinfo(ip, *args, **kwargs)
        return original_getaddrinfo(host, *args, **kwargs)

    socket.getaddrinfo = patched_getaddrinfo
    try:
        yield
    finally:
        socket.getaddrinfo = original_getaddrinfo


def decode_base64_content(text: str) -> str:
    """
    将获取到的内容做 base64 解码。
    自动去除首尾空白，并补齐缺失的 '=' padding，
    解码失败时返回原始文本并打印警告。
    """
    cleaned = text.strip()
    try:
        # 补齐 padding
        missing_padding = len(cleaned) % 4
        if missing_padding:
            cleaned += "=" * (4 - missing_padding)
        decoded_bytes = base64.b64decode(cleaned)
        return decoded_bytes.decode("utf-8", errors="replace")
    except Exception as e:
        print(f"[警告] base64 解码失败，将写入原始内容。错误: {e}", file=sys.stderr)
        return text


def fetch_content(original_link: str, host: str, ip: str) -> str:
    """
    访问链接对应的内容。通过 DNS 劫持强制连接到指定 ip，
    同时保留原域名用于 SNI/Host，避免直接用 ip 拼接 URL 导致的 SNI 失配问题。
    """
    try:
        with override_dns(host, ip):
            resp = requests.get(original_link, timeout=15)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        print(f"[错误] 访问 {original_link} (强制解析到 {ip}) 时发生异常: {e}", file=sys.stderr)
        return None


def main():
    print(f"正在抓取页面: {README_URL}")
    content = fetch_readme(README_URL)

    links = extract_fn_links(content)
    print(f"共找到 {len(links)} 个以 https://fn 开头的链接")
    for link in links:
        print(f"  - {link}")

    results = []
    for link in links:
        parsed = urlparse(link)
        host = parsed.hostname
        print(f"\n正在查询域名 {host} 的 IP...")
        ip = query_ip(host)
        if not ip:
            print(f"[跳过] 无法获取 {host} 的 IP，跳过该链接")
            continue
        print(f"  {host} -> {ip}")

        new_link = replace_host_with_ip(link, ip)
        print(f"  新链接: {new_link}")

        print(f"正在访问新链接...")
        body = fetch_content(link, host, ip)
        if body is None:
            print(f"[跳过] 访问 {new_link} 失败")
            continue

        decoded_body = decode_base64_content(body)

        results.append(f"# 原链接: {link}\n# 新链接: {new_link}\n{decoded_body}\n")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(results))

    print(f"\n完成！结果已写入 {OUTPUT_FILE}，共写入 {len(results)} 条记录。")


if __name__ == "__main__":
    main()