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
SUB7_REPLACE_IP = os.environ.get('SUB7_REPLACE_IP')

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


def replace_host_with_ip(link: str, ip: str) -> str:
    """用 IP 替换链接中的域名部分"""
    parsed = urlparse(link)
    host = parsed.hostname
    new_netloc = parsed.netloc.replace(host, ip)
    new_link = link.replace(parsed.netloc, new_netloc, 1)
    return new_link


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


def fetch_content(new_link: str, host: str, ip: str) -> str:
    """
    访问链接对应的内容。通过 DNS 劫持强制连接到指定 ip，
    同时保留原域名用于 SNI/Host，避免直接用 ip 拼接 URL 导致的 SNI 失配问题。
    """
    try:
        resp = requests.get(new_link, timeout=15)
        return resp.text
    except Exception as e:
        print(f"[错误] 访问 {new_link} 时发生异常: {e}", file=sys.stderr)
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
        
        new_link = replace_host_with_ip(link, SUB7_REPLACE_IP)
        print(f"  新链接: {new_link}")

        print(f"正在访问新链接...")
        body = fetch_content(new_link, host, SUB7_REPLACE_IP)
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