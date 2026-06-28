import time
import datetime
import urllib.request

SUB4_PREFIX = os.environ.get('SUB4_PREFIX')

# 1. 生成订阅链接
current_hour = datetime.datetime.now().replace(minute=0, second=0, microsecond=0)
current_hour_timestamp = int(current_hour.timestamp())
sublink = f'{SUB4_PREFIX}{current_hour_timestamp}'

print(f'生成订阅链接: https://***/v1/sub/hysteria/{current_hour_timestamp}')

# 2. 获取订阅链接的数据并写入 sub4.txt
try:
    req = urllib.request.Request(sublink)
    with urllib.request.urlopen(req) as response:
        data = response.read().decode('utf-8')
        
    with open('sub4.txt', 'w', encoding='utf-8') as f:
        f.write(data)
        
    print('Successfully wrote data to sub4.txt')
except Exception as e:
    print(f'Error occurred: {e}')
    exit(1) # 发生错误时让 Action 步骤标记为失败
