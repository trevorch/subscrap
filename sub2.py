import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# 目标网站首页及伪装浏览器请求头
SUB2_HOME = os.environ.get('SUB2_HOME')
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
}

def fetch_clash_nodes():
    # 第一步：访问首页获取最新订阅链接
    print(f"正在访问首页")
    try:
        resp = requests.get(SUB2_HOME, headers=HEADERS, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        print(f"❌ 首页访问失败: {e}")
        return

    soup = BeautifulSoup(resp.text, 'html.parser')
    

    # 使用 CSS 选择器获取指定路径下的所有 a 标签
    links = soup.select('div.panel-body > div.row > div.col-md-3 > a')
   
    target_href = None
    # 遍历找到的 a 标签，寻找 title 属性包含【免费节点分享】的标签
    for link in links:
       # 使用 get() 方法获取 title 属性，避免属性不存在时报错
       title = link.get('title', '')
       if '免费节点分享' in title:
          target_href = link.get('href')
          break  # 找到第一个符合条件的标签后，立即退出循环
   
    # 打印或使用获取到的链接
    if target_href:
       print("获取到的链接:", target_href)
    else:
       print("未找到符合条件的链接")
       return

    target_url = urljoin(SUB2_HOME, target_href)
    print(f"✅ 成功获取到最新订阅页面：{target_href}")
    
    # 第四步：访问订阅详情页并提取 V2ray 链接
    try:
        detail_resp = requests.get(target_url, headers=HEADERS, timeout=10)
        detail_resp.raise_for_status()
    except Exception as e:
        print(f"❌ 详情页访问失败: {e}")
        return

    detail_soup = BeautifulSoup(detail_resp.text, 'html.parser')
    
    # 容错处理：检查是否有系统错误提示
    if detail_soup.find('div', class_='system-message error'):
        print("⚠️ 检测到系统错误提示，今日可能暂无更新或页面异常，程序终止。")
        return
        
    # 使用 lambda 函数进行模糊匹配：
    # 找到所有 <p> 标签，且标签内的文本同时包含指定的开头和结尾字符串
    target_tags = detail_soup.find_all('p', string=lambda t: t and 'https://node.openclash.wiki/uploads/' in t and '.txt' in t)
   
    v2ray_links = []
    for tag in target_tags:
       # 获取并清理标签内的文本内容（去除首尾空格）
       link_text = tag.get_text(strip=True)
       v2ray_links.append(link_text)
   
    # 打印结果（可选）
    if v2ray_links:
       print("提取到的链接:", v2ray_links)
    else:
       print("未找到符合条件的链接，请检查页面内容。")

        
    if not v2ray_links:
        print("未在指定区域内找到有效的 V2ray 链接。")
        return
        
    print(f"🎯 成功提取到 {len(v2ray_links)} 个订阅地址，开始抓取内容...")
    
    success_count = 0
    with open("sub2.txt", "w", encoding="utf-8") as f:
        for link in v2ray_links:
            try:
                sub_resp = requests.get(link, headers=HEADERS, timeout=15)
                sub_resp.raise_for_status()
                content = sub_resp.text.strip()
                
                if content:
                    f.write(content + "\n")  
                    success_count += 1
                    print(f"   ✔️ 成功写入")
                else:
                    print(f"   ⚠️ 内容为空")
                    
            except Exception as e:
                print(f"   ❌ 抓取失败: {e}")
                
    print(f"\n🎉 抓取完成！共成功处理 {success_count}/{len(v2ray_links)} 个订阅源，结果已保存至 sub2.txt")

if __name__ == "__main__":
    fetch_clash_nodes()
