import os
import re
import sys
import base64
import binascii
import requests


def is_base64(s: str) -> bool:
    """粗略判断字符串是否可能是合法的 base64 编码"""
    s = s.strip()
    if not s:
        return False
    # base64 只应包含这些字符
    if not re.fullmatch(r'[A-Za-z0-9+/=\s]+', s):
        return False
    compact = re.sub(r'\s+', '', s)
    # 长度必须是 4 的倍数
    if len(compact) % 4 != 0:
        return False
    return True


def try_decode_base64(content: str) -> str:
    """
    尝试对内容进行 base64 解码。
    如果解码成功且结果是合法的 UTF-8 文本，返回解码后的内容；
    否则原样返回原始内容（说明本身就是明文订阅内容）。
    """
    compact = re.sub(r'\s+', '', content)
    if not is_base64(compact):
        return content
    try:
        decoded_bytes = base64.b64decode(compact, validate=True)
        decoded_str = decoded_bytes.decode('utf-8')
        return decoded_str
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return content


def fetch_link(url: str, timeout: int = 15) -> str:
    headers = {
        'User-Agent': 'Mozilla/5.0 (compatible; sub6-fetcher/1.0)'
    }
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    resp.encoding = resp.encoding or 'utf-8'
    return resp.text


def main():
    links_env = os.environ.get('SUB6_LINKS', '')
    links = [l.strip() for l in links_env.split(';') if l.strip()]

    if not links:
        print('未在环境变量 SUB6_LINKS 中找到任何链接', file=sys.stderr)
        sys.exit(1)

    all_contents = []
    for idx, link in enumerate(links, 1):
        print(f'[{idx}/{len(links)}] 正在抓取: {link}')
        try:
            raw_content = fetch_link(link)
        except Exception as e:
            print(f'  抓取失败: {e}', file=sys.stderr)
            continue

        decoded_content = try_decode_base64(raw_content).strip()

        if decoded_content:
            all_contents.append(decoded_content)
            print(f'  成功获取内容，长度: {len(decoded_content)} 字符')
        else:
            print('  内容为空，已跳过')

    if not all_contents:
        print('未能从任何链接获取到有效内容', file=sys.stderr)
        sys.exit(1)

    output_text = '\n'.join(all_contents) + '\n'

    with open('sub6.txt', 'w', encoding='utf-8') as f:
        f.write(output_text)

    print(f'已写入 sub6.txt，共 {len(all_contents)} 个来源，总长度 {len(output_text)} 字符')


if __name__ == '__main__':
    main()