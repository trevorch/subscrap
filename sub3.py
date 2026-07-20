#!/usr/bin/env python3
"""
自动获取节点订阅脚本
流程：抓取视频链接 -> 下载音频 -> Whisper转文字 -> 提取口令 -> 获取节点
"""

import os
import re
import sys
import json
import glob
import base64
import regex as re
import subprocess
import urllib.request
import urllib.error
from html.parser import HTMLParser

SUB3_HOME = os.environ.get('SUB3_HOME')
SUB3_HOST = os.environ.get('SUB3_HOST')
SUB3_VERIFY = os.environ.get('SUB3_VERIFY')
# ─────────────────────────────────────────────
# 1. 抓取视频链接
# ─────────────────────────────────────────────

class VideoLinkParser(HTMLParser):
    """ 提取"本期视频"后的 <a> href"""

    def __init__(self):
        super().__init__()
        self.video_url = None
        self._in_strong = False
        self._expect_link = False

    def handle_starttag(self, tag, attrs):
        if tag == "strong":
            self._in_strong = True
        if tag == "a" and self._expect_link:
            href = dict(attrs).get("href", "")
            if href:
                self.video_url = href
            self._expect_link = False

    def handle_endtag(self, tag):
        if tag == "strong":
            self._in_strong = False

    def handle_data(self, data):
        if self._in_strong and "本期视频" in data:
            self._expect_link = True


def fetch_video_url(page_url: str) -> str:
    print(f"[1/5] 正在抓取页面...")
    req = urllib.request.Request(page_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        html = resp.read().decode("utf-8", errors="replace")

    parser = VideoLinkParser()
    parser.feed(html)

    if not parser.video_url:
        # 兜底正则：匹配紧跟"本期视频"strong标签后的第一个 <a href="...">
        pattern = r'本期视频[^<]*</strong>[^<]*<a\s+href="([^"]+)"'
        m = re.search(pattern, html)
        if m:
            parser.video_url = m.group(1)

    if not parser.video_url:
        raise RuntimeError("未能从页面提取到视频链接，请检查页面结构是否变化。")

    print(f"    已取得视频链接")
    return parser.video_url


# ─────────────────────────────────────────────
# 2. 安装 yt-dlp 并下载音频
# ─────────────────────────────────────────────

def install_yt_dlp():
    print("[2/5] 安装/升级 yt-dlp …")
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-U", "yt-dlp", "-q"],
        check=True
    )


def download_audio(video_url: str) -> str:
    """下载音频并返回 mp3 文件路径"""
    print(f"[3/5] 正在下载音频...")
    output_template = "audio.%(ext)s"
    cmd = [
        "yt-dlp",
        "-x",
        "--audio-format", "mp3",
        "--audio-quality", "5",          # 适中质量，加快速度
        "--no-playlist",
        "--cookies", "/tmp/cookies.txt",
        "-o", output_template,
        video_url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        # yt-dlp 有时以非零退出但实际成功，先检查文件
        print("    yt-dlp stderr:", result.stderr[-500:] if result.stderr else "")

    # 找到生成的 mp3 文件
    mp3_files = glob.glob("audio.mp3") or glob.glob("audio*.mp3")
    if not mp3_files:
        # 可能生成了其他格式，再做转换
        other = glob.glob("audio.*")
        if not other:
            raise RuntimeError(f"yt-dlp 未生成任何音频文件。\nstderr: {result.stderr}")
        audio_path = other[0]
        mp3_path = "audio.mp3"
        subprocess.run(
            ["ffmpeg", "-y", "-i", audio_path, mp3_path],
            check=True, capture_output=True
        )
        return mp3_path

    print(f"    音频文件：{mp3_files[0]}")
    return mp3_files[0]


# ─────────────────────────────────────────────
# 3. Whisper 转文字
# ─────────────────────────────────────────────

def install_whisper():
    print("    安装 openai-whisper …")
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-q", "openai-whisper"],
        check=True
    )


def transcribe_audio(audio_path: str) -> str:
    print(f"[4/5] Whisper 转录：{audio_path}")
    try:
        import whisper
    except ImportError:
        install_whisper()
        import whisper

    # 使用 base 模型，速度与准确率平衡
    model = whisper.load_model("large")
    result = model.transcribe(audio_path, language="zh", fp16=False)
    text = result["text"]
    print(f"    转录内容（前500字）：{text[:500]}")
    return text


def extract_code(transcript: str) -> str:
    """从文字中提取「口令xxxx」"""
    pattern = r"(?<=口令.{0,100})[A-Za-z0-9]+"
    matches = re.findall(pattern, transcript)
    if matches:
        code = max(matches, key=len)
        print(f"    提取口令：{code}")
        return code
    raise RuntimeError(
        f"未能从转录文字中提取口令，请检查 Whisper 输出：\n{transcript[:500]}"
    )


# ─────────────────────────────────────────────
# 4. 调用 API 获取节点
# ─────────────────────────────────────────────

def fetch_nodes(code: str) -> str:
    print(f"[5/5] 使用口令「{code}」请求节点 API …")
    payload = json.dumps({"code": code}).encode("utf-8")
    req = urllib.request.Request(
        SUB3_VERIFY,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"API 请求失败 HTTP {e.code}：{body[:300]}")

    if not data.get("success"):
        raise RuntimeError(f"API 返回失败：{json.dumps(data, ensure_ascii=False)}")

    v2ray_url = data["links"]["proxy"]["v2ray"]
    print(f"    已取得v2ray订阅地址")

    # 获取订阅内容
    req2 = urllib.request.Request(v2ray_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req2, timeout=30) as resp2:
        content = resp2.read().decode("utf-8", errors="replace")

    print(f"    订阅内容长度：{len(content)} 字节")
    return content


# ─────────────────────────────────────────────
# 主流程
# ─────────────────────────────────────────────

def main():
    output_file = "sub3.txt"

    try:
        video_url = fetch_video_url(SUB3_HOME)
        install_yt_dlp()
        audio_path = download_audio(video_url)
        transcript = transcribe_audio(audio_path)
        code = extract_code(transcript)
        encoded_str = fetch_nodes(code)
        
        # 补齐 Base64 填充字符 '=' (如果缺失)
        missing_padding = len(encoded_str) % 4
        if missing_padding:
            encoded_str += '=' * (4 - missing_padding)
      
        # 尝试解码并写入
        try:
            decoded_bytes = base64.b64decode(encoded_str, validate=True)
            decoded_str = decoded_bytes.decode('utf-8')
            content_to_write = decoded_str
            print("✅ Base64 解码成功！")
        except Exception as decode_err:
            # 核心修改：解码失败时，打印警告并写入原始内容
            print(f"⚠️ 解码失败，错误原因: {decode_err}")
            print("🔄 将写入原始 Base64 内容...")
            content_to_write = encoded_str

        # 统一写入文件
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(content_to_write)
        print(f"\n✅ 完成！内容已写入 {output_file}")

    except Exception as e:
        print(f"\n❌ 出错：{e}", file=sys.stderr)
        sys.exit(1)



if __name__ == "__main__":
    main()    