import subprocess
import re
import os

def get_youtube_transcript(video_url):
    # 1. 提取视频ID
    video_id_match = re.search(r'(?:v=|\.be/)(\w+)', video_url)
    if not video_id_match:
        print("❌ 无法从URL中提取视频ID")
        return
    
    video_id = video_id_match.group(1)
    print(f"🎬 正在使用 yt-dlp 获取视频 ID: '{video_id}' 的中文字幕...")

    # 2. 构建 yt-dlp 命令
    # --write-sub: 下载手动上传的字幕
    # --write-auto-sub: 下载自动生成的字幕（如果手动字幕不存在）
    # --sub-lang: 指定语言优先级
    # --skip-download: 仅下载字幕，不下载视频和音频
    # --cookies: 指定 Cookies 文件路径
    # -o: 输出文件命名格式
    cmd = [
        "yt-dlp",
        "--write-sub",
        "--write-auto-sub",
        "--sub-lang", "zh-Hans,zh-CN,zh-Hant,zh-TW,zh",
        "--skip-download",
        "--cookies", "cookies.txt",
        "-o", f"{video_id}_zh.%(ext)s",
        video_url
    ]

    try:
        # 3. 执行命令
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ yt-dlp 执行成功！")
            # 检查是否生成了文件
            if os.path.exists(f"{video_id}_zh.vtt") or os.path.exists(f"{video_id}_zh.srt"):
                print(f"📄 字幕文件已保存在当前目录。")
            else:
                print("⚠️ 命令执行成功，但未找到生成的字幕文件。该视频可能确实没有中文字幕。")
        else:
            print(f"❌ yt-dlp 执行失败 (返回码: {result.returncode})")
            print("错误输出:", result.stderr)

    except Exception as e:
        print(f"\n❌ 发生异常: {e}")

if __name__ == "__main__":
    url = "https://m.youtube.com/watch?v=gfd80OYwhHA"
    get_youtube_transcript(url)
