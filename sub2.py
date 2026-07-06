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
    
    # 第二步：根据HTML结构精准定位 <a> 标签
    # 寻找 href 包含 "/free-node/" 的 a 标签
    link_tag = soup.select_one('a[href*="/free-node/"]')
    
    if not link_tag:
        print("⚠️ 未在首页找到有效的免费节点链接，请检查网页结构是否发生变化。")
        return
        
    # 第三步：提取相对路径并拼接为完整的绝对 URL
    relative_href = link_tag.get('href')
    target_url = urljoin(SUB2_HOME, relative_href)
    print(f"✅ 成功获取到最新订阅页面")
    
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
        
    start_tag = detail_soup.find('strong', string='v2ray订阅链接:')
    end_tag = detail_soup.find('strong', string='clash订阅链接')
    
    if not start_tag or not end_tag:
        print("未找到指定的起止标记，请检查详情页结构是否发生变化。")
        return
        
    v2ray_links = []
    current_element = start_tag.parent.next_sibling
    
    while current_element and current_element != end_tag.parent:
        if current_element.name == 'p':
            link_text = current_element.get_text(strip=True)
            if link_text.startswith("http"):  
                v2ray_links.append(link_text)
        current_element = current_element.next_sibling
        
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
