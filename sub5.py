# extract_links.py

import requests
from bs4 import BeautifulSoup
import re

def main():
    url = "https://www.v2raya.net/free-nodes/free-v2ray-node-subscriptions.html"
    
    try:
        # 设置请求头，模拟浏览器访问，避免被简单的反爬虫机制拦截
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        # 发送 GET 请求
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status() # 如果响应状态码不是 200，则抛出异常
        
        # 使用 BeautifulSoup 解析网页内容
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 根据网页结构，订阅链接位于 id 为 "free_subscription_list" 的元素下的 li 标签中
        # 查找所有符合条件的 li 元素
        li_elements = soup.select('#free_subscription_list ul li')
        
        print("提取到的订阅链接如下：")
        for li in li_elements:
            # 获取 li 标签内的纯文本
            text = li.get_text(strip=True)
            # 使用正则表达式从文本中提取以 http 或 https 开头的 URL
            urls = re.findall(r'https?://[^\s]+', text)
            for found_url in urls:
                print(found_url)
                
    except requests.exceptions.RequestException as e:
        print(f"网络请求错误: {e}")
    except Exception as e:
        print(f"发生未知错误: {e}")

if __name__ == "__main__":
    main()
