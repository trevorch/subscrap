#!/usr/bin/env python3

import os
import requests
import re
import base64

SUB5_REPO = os.environ.get('SUB5_REPO')

def main():
    # 目标URL
    url = f"{SUB5_REPO}/refs/heads/main/README.md"
    
    try:
        # 1. 抓取文件内容
        print(f"正在获取源文件: refs/heads/main/README.md")
        response = requests.get(url, timeout=10)
        response.raise_for_status() # 检查HTTP请求是否成功
        content = response.text
        
        # 2. 使用正则提取以 https://fn 开头的链接
        pattern = r'https://fn[^\s`)]+'
        links = re.findall(pattern, content)
        
        if not links:
            print("未找到以 'https://fn' 开头的链接。")
            return

        print(f"找到 {len(links)} 个链接，开始处理...")

        decoded_results = []

        # 3. 遍历链接并处理
        for link in links:
            try:
                # 访问链接内容
                node_response = requests.get(link, timeout=10)
                node_response.raise_for_status()
                
                # 获取内容并尝试 Base64 解码
                encoded_str = node_response.text.strip()
                
                # 补齐 Base64 填充字符 '=' (如果缺失)
                missing_padding = len(encoded_str) % 4
                if missing_padding:
                    encoded_str += '=' * (4 - missing_padding)
                
                # 核心修改：如果解码失败，直接跳过，不写入结果列表
                try:
                    decoded_bytes = base64.b64decode(encoded_str, validate=True)
                    decoded_str = decoded_bytes.decode('utf-8')
                except Exception as decode_err:
                    print(f"⚠️ 解码失败，已跳过: {link} | 错误原因: {decode_err}")
                    continue  # 解码失败，跳过当前循环，不加入 decoded_results
                
                # 只有成功解码的内容才会被加入列表
                decoded_results.append(decoded_str)
                print(f"✅ 成功解码: {link}")
                
            except requests.exceptions.RequestException as req_err:
                print(f"❌ 网络请求失败，已跳过: {link} | 错误原因: {req_err}")
            except Exception as e:
                print(f"❌ 处理过程中发生未知错误，已跳过: {link} | 错误原因: {e}")

        # 4. 写入文件
        if decoded_results:
            output_file = "sub5.txt"
            with open(output_file, "w", encoding="utf-8") as f:
                f.write("\n".join(decoded_results))
            print(f"\n所有操作完成，成功解码 {len(decoded_results)} 条数据，已写入 {output_file}")
        else:
            print("\n没有成功解码的数据，未生成文件。")

    except requests.exceptions.RequestException as e:
        print(f"网络请求错误: {e}")
    except Exception as e:
        print(f"发生未知错误: {e}")

if __name__ == "__main__":
    main()
