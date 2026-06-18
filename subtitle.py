import re
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter

def get_youtube_transcript(video_url):
    # 1. 提取视频ID
    video_id_match = re.search(r'(?:v=|\.be/)(\w+)', video_url)
    if not video_id_match:
        print("❌ 无法从URL中提取视频ID")
        return
    
    video_id = video_id_match.group(1)
    print(f"🎬 正在获取视频 ID: '{video_id}' 的中文字幕...")

    try:
        # 2. 实例化 API 对象，并传入 cookies 文件路径
        ytt_api = YouTubeTranscriptApi(cookies="cookies.txt")
        
        # 3. 获取字幕
        transcript_list = ytt_api.fetch(
            video_id, 
            languages=['zh-Hans', 'zh-CN', 'zh-Hant', 'zh-TW', 'zh']
        )
        
        # 4. 格式化并保存
        formatter = TextFormatter()
        text_formatted = formatter.format_transcript(transcript_list)
        
        filename = f"{video_id}_zh.txt"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(text_formatted)
            
        print(f"✅ 字幕已成功保存为: {filename}")

    except Exception as e:
        print(f"\n❌ 获取字幕时出错: {e}")

if __name__ == "__main__":
    url = "https://m.youtube.com/watch?v=gfd80OYwhHA"
    get_youtube_transcript(url)
