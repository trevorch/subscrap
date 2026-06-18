#!/usr/bin/env python3
"""
自动获取免费节点
流程：
  1. 抓取页面，提取视频链接
  2. 用 yt-dlp + cookies 下载音频（绕过 YouTube bot 检测）
  3. 用 Whisper 转录，提取口令
  4. POST 口令到 API，获取 v2ray 订阅链接
  5. 下载订阅内容写入 sub3.txt

GitHub Actions 使用说明：
  - 将 YouTube cookies（Netscape 格式）存入 Secret: YOUTUBE_COOKIES
  - workflow 会自动写入 /tmp/yt_cookies.txt 供 yt-dlp 使用
"""

import os
import re
import subprocess
import sys
import tempfile

import requests
from bs4 import BeautifulSoup

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

SUB3_HOME = os.environ.get('SUB3_HOME')
SUB3_HOST = os.environ.get('SUB3_HOST')
SUB3_VERIFY = os.environ.get('SUB3_VERIFY')
# ──────────────────────────────────────────────
# 步骤 1：抓取页面，提取视频链接
# ──────────────────────────────────────────────
def fetch_video_url(page_url: str) -> str:
    print(f"\n[1] 正在访问页面：{page_url}")
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }
    resp = requests.get(page_url, headers=headers, timeout=30)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    # 查找 <strong>本期视频（含今日口令）</strong> 后面的 <a>
    for strong in soup.find_all("strong"):
        if "本期视频" in strong.get_text() and "口令" in strong.get_text():
            parent = strong.parent
            a_tag = parent.find("a")
            if a_tag and a_tag.get("href"):
                video_url = a_tag["href"]
                print(f"[1] ✅ 找到视频链接：{video_url}")
                return video_url

    # 兜底：全页查找 YouTube 链接
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "youtu.be" in href or "youtube.com/watch" in href:
            print(f"[1] ✅ (兜底) 找到视频链接：{href}")
            return href

    raise RuntimeError("❌ 未能从页面找到视频链接，页面结构可能已变化。")


# ──────────────────────────────────────────────
# 步骤 2：下载视频音频（支持 cookies）
# ──────────────────────────────────────────────
def get_cookies_file() -> str | None:
    """
    优先级：
      1. 环境变量 YOUTUBE_COOKIES_FILE（直接指定路径）
      2. 环境变量 YOUTUBE_COOKIES（cookies 文本内容，写入临时文件）
      3. 默认路径 /tmp/yt_cookies.txt（由 workflow 写入）
    """
    # 方式 1：直接指定文件路径
    path = os.environ.get("YOUTUBE_COOKIES_FILE", "")
    if path and os.path.exists(path):
        print(f"[2] 使用 cookies 文件：{path}")
        return path

    # 方式 2：环境变量内容 → 写入临时文件
    content = os.environ.get("YOUTUBE_COOKIES", "")
    if content.strip():
        tmp = "/tmp/yt_cookies.txt"
        with open(tmp, "w") as f:
            f.write(content)
        print(f"[2] 已从环境变量写入 cookies 到：{tmp}")
        return tmp

    # 方式 3：workflow 预写的默认路径
    default = "/tmp/yt_cookies.txt"
    if os.path.exists(default):
        print(f"[2] 使用默认 cookies 文件：{default}")
        return default

    print("[2] ⚠️  未找到 cookies，将尝试无 cookies 下载（可能被 YouTube 拦截）")
    return None


def build_ytdlp_cmd(video_url: str, output_path: str, cookies_file: str | None) -> list:
    cmd = [
        "yt-dlp",
        "--no-playlist",
        "-x",
        "--audio-format", "mp3",
        "--audio-quality", "5",
        "-o", f"{output_path}.%(ext)s",
        # 重试与超时
        "--retries", "5",
        "--fragment-retries", "5",
        "--socket-timeout", "30",
        # 使用 Android 客户端绕过部分限制（不需要登录）
        "--extractor-args", "youtube:player_client=android,web",
        "--no-warnings",
    ]
    if cookies_file:
        cmd += ["--cookies", cookies_file]
    cmd.append(video_url)
    return cmd


def download_audio(video_url: str, output_path: str = "/tmp/jcnode_audio") -> str:
    print(f"\n[2] 正在下载音频：{video_url}")

    cookies_file = get_cookies_file()
    cmd = build_ytdlp_cmd(video_url, output_path, cookies_file)

    print(f"[2] 执行命令：{' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

    if result.returncode != 0:
        print(f"[2] yt-dlp stdout:\n{result.stdout[-500:]}")
        print(f"[2] yt-dlp stderr:\n{result.stderr[-800:]}")

        # 如果是 bot 检测错误，给出明确提示
        if "Sign in to confirm" in result.stderr or "bot" in result.stderr.lower():
            raise RuntimeError(
                "❌ YouTube bot 检测拦截！\n"
                "解决方法：在本地浏览器登录 YouTube 后，导出 cookies 存入\n"
                "GitHub Secret: YOUTUBE_COOKIES（Netscape 格式）\n"
                "详见 README.md 中的 '配置 YouTube Cookies' 章节。"
            )
        raise RuntimeError(f"❌ yt-dlp 下载失败（exit code {result.returncode}）")

    for ext in ["mp3", "m4a", "webm", "opus", "ogg"]:
        candidate = f"{output_path}.{ext}"
        if os.path.exists(candidate):
            size_kb = os.path.getsize(candidate) // 1024
            print(f"[2] ✅ 音频文件：{candidate}（{size_kb} KB）")
            return candidate

    raise RuntimeError("❌ yt-dlp 完成但找不到音频文件。")


# ──────────────────────────────────────────────
# 步骤 3：语音转文字 → 提取口令
# ──────────────────────────────────────────────
def transcribe_audio(audio_path: str) -> str:
    print(f"\n[3] 正在转录音频（首次运行会下载 Whisper 模型 ~460 MB）…")
    import whisper

    model = whisper.load_model("small")
    result = model.transcribe(audio_path, language="zh", verbose=False)
    text = result["text"]
    print(f"[3] ✅ 转录完成，前300字：\n{text[:300]!r}")
    return text


def extract_code(text: str) -> str:
    patterns = [
        r"口令[：:\s「]?\s*([A-Za-z0-9\u4e00-\u9fff@#$%^&*!]{2,20})",
        r"密码[：:\s「]?\s*([A-Za-z0-9\u4e00-\u9fff@#$%^&*!]{2,20})",
        r"暗号[：:\s「]?\s*([A-Za-z0-9\u4e00-\u9fff@#$%^&*!]{2,20})",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            code = m.group(1).strip()
            print(f"[3] ✅ 识别到口令：{code!r}")
            return code

    raise RuntimeError(
        f"❌ 未能从转录文字中识别口令。\n"
        f"完整转录内容：\n{text}"
    )


# ──────────────────────────────────────────────
# 步骤 4：提交口令，解析节点链接
# ──────────────────────────────────────────────
def verify_code(code: str) -> dict:
    print(f"\n[4] 正在提交口令…")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0",
        "Referer": SUB3_HOST,
    }
    resp = requests.post(SUB3_VERIFY, json={"code": code}, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    print(f"[4] 接口响应：{data}")
    if not data.get("success"):
        raise RuntimeError(f"❌ 口令验证失败：{data}")
    return data


def get_v2ray_url(api_data: dict) -> str:
    try:
        url = api_data["links"]["proxy"]["v2ray"]
        print(f"[4] ✅ v2ray 订阅链接：{url}")
        return url
    except KeyError as e:
        raise RuntimeError(
            f"❌ 响应结构异常，找不到 proxy.v2ray 字段：{e}\n数据：{api_data}"
        )


# ──────────────────────────────────────────────
# 步骤 5：下载订阅内容，写入 sub3.txt
# ──────────────────────────────────────────────
def download_sub(v2ray_url: str, output_file: str = "sub3.txt") -> None:
    print(f"\n[5] 正在下载订阅内容：{v2ray_url}")
    headers = {"User-Agent": "ClashMeta/1.0"}
    resp = requests.get(v2ray_url, headers=headers, timeout=30)
    resp.raise_for_status()
    content = resp.text

    out_path = os.path.join(SCRIPT_DIR, output_file)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)

    lines = content.strip().splitlines()
    print(f"[5] ✅ 已写入 {out_path}（{len(lines)} 行，{len(content)} 字节）")


# ──────────────────────────────────────────────
# 主流程
# ──────────────────────────────────────────────
def main():

    video_url = fetch_video_url(SUB3_HOME)
    audio_path = download_audio(video_url)
    text       = transcribe_audio(audio_path)
    code       = extract_code(text)
    api_data   = verify_code(code)
    v2ray_url  = get_v2ray_url(api_data)
    download_sub(v2ray_url)

    print("\n✅ 全部完成！订阅内容已保存到 sub3.txt")


if __name__ == "__main__":
    main()    