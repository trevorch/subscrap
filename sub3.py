#!/usr/bin/env python3
"""
自动获取免费节点
流程：
  1. 抓取页面，提取视频链接
  2. 用 yt-dlp 下载音频
  3. 用 Whisper 转录，提取口令
  4. POST 口令到 API，获取 v2ray 订阅链接
  5. 下载订阅内容写入 sub3.txt
"""

import os
import re
import subprocess
import sys

import requests
from bs4 import BeautifulSoup

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

    # 查找 <strong>本期视频（含今日口令）</strong> 后面紧跟的 <a>
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
# 步骤 2：下载视频音频
# ──────────────────────────────────────────────
def download_audio(video_url: str, output_path: str = "/tmp/jcnode_audio") -> str:
    print(f"\n[2] 正在下载音频：{video_url}")
    cmd = [
        "yt-dlp",
        "--no-playlist",
        "-x",
        "--audio-format", "mp3",
        "--audio-quality", "5",
        "-o", f"{output_path}.%(ext)s",
        "--no-warnings",
        video_url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        print(f"[2] yt-dlp stderr:\n{result.stderr[:800]}")
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
    import whisper  # 延迟导入，避免未安装时报错

    model = whisper.load_model("small")
    result = model.transcribe(audio_path, language="zh", verbose=False)
    text = result["text"]
    print(f"[3] ✅ 转录完成，前1000字：\n{text[:1000]!r}")
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
        f"转录内容（前500字）：\n{text[:500]}"
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

    # 写入脚本所在目录（即仓库根目录），方便 git commit
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), output_file)
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