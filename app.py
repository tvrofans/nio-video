from flask import Flask, render_template, request, jsonify
import json
import requests
import concurrent.futures
import urllib3
import random
import time

# 禁用安全警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

CACHE_HOME = {}

# --- 配置区 ---
MAX_ITEMS = 20  # 严格限制 20 个
BATCH_SIZE = 1  # 极速模式：每次只抓 1 页 (因为是最新更新，命中率很高，无需深挖)

# --- 核心配置：分类 ID 映射表 ---
# 针对 量子(liangzi)、红牛(hongniu)、速播(subo) 的分类ID
# 这些ID通常是通用的：
# 13=国产剧, 14=港台剧(可选), 15=日韩剧, 16=欧美剧
# 6=动作片, 7=喜剧片, 8=爱情片, 9=科幻片 (统称电影)
# 为了精准匹配您的需求：[国产电影, 美国电影, 国产剧, 美剧, 韩剧]
# 我们主要抓取以下分类：
TARGET_TYPES = [
    13, # 国产剧
    16, # 欧美剧 (涵盖美剧)
    15, # 日韩剧 (涵盖韩剧)
    6,  # 动作片 (涵盖大部分美影/国影)
    9,  # 科幻片 (涵盖大部分美影)
    7,  # 喜剧片
    8,  # 爱情片
    20  # 战争片 (可选)
]

# 依然保留黑名单，防止"解说"混入电影分类
BANNED_KEYWORDS = [
    "解说", "短剧", "讲电影", "速看", "预告", "花絮", "特辑", 
    "体育", "NBA", "赛事", "足球", "篮球", "比赛", "集锦", "CBA", "录像",
    "综艺", "动漫", "动画", "伦理", "三级", "福利"
]

def get_sources():
    try:
        with open('db.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        return {s['key']: s for s in data['sites'] if s.get('active')}
    except:
        return {}

def fetch_data(url):
    try:
        if '?' in url: url += '&at=json'
        else: url += '?at=json'
        # 极速超时设置 3秒
        r = requests.get(url, headers=HEADERS, timeout=3, verify=False)
        if r.status_code == 200:
            try: return r.json()
            except: return json.loads(r.text)
    except:
        pass
    return None

def is_valid_content(item):
    name = item.get('vod_name', '')
    type_name = item.get('type_name', '')
    
    # 1. 黑名单过滤
    for kw in BANNED_KEYWORDS:
        if kw in name: return False
        if kw in type_name: return False

    # 2. 地区/分类二次校验 (确保是美/国/韩)
    # 这一步是可选的，为了速度可以不做太细，靠TypeID已经过滤了大部分
    
    # 3. 必须有图
    if not item.get('vod_pic'): return False
    
    return True

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/play')
def play():
    return render_template('play.html')

@app.route('/api')
def api():
    action = request.args.get('ac', 'list')
    key = request.args.get('key')
    try: client_pg = int(request.args.get('pg', '1'))
    except: client_pg = 1
    wd = request.args.get('wd', '')
    ids = request.args.get('ids', '')
    sources = get_sources()
    
    if key and key in sources:
        base_url = sources[key]['api']
        if action == 'detail': url = f"{base_url}?ac=detail&ids={ids}"
        else: url = f"{base_url}?ac=detail&pg={client_pg}&wd={wd}"
        return jsonify(fetch_data(url))
    
    if wd: return jsonify([])

    # --- 首页推荐 (最新更新模式) ---
    cache_key = f"page_{client_pg}"
    # 缓存时间缩短为 60秒，保证能看到最新的
    if cache_key in CACHE_HOME and time.time() - CACHE_HOME[cache_key]['timestamp'] < 60:
        return jsonify({"list": CACHE_HOME[cache_key]['data']})

    prime_source = None
    for k in ['liangzi', 'hongniu', 'subo']:
        if k in sources:
            prime_source = sources[k]; break
    if not prime_source and sources: prime_source = list(sources.values())[0]

    final_list = []
    if prime_source:
        # 为了速度，我们随机挑选 3 个分类ID进行请求，而不是全部
        # 这样每次刷新都能看到不同类目的更新，且请求量很少
        selected_types = random.sample(TARGET_TYPES, 4) 
        
        # 映射页码
        # 前端翻1页，我们还是去源站对应翻页，但带上 t=分类ID
        source_pg = client_pg
        
        urls = []
        for tid in selected_types:
            urls.append(f"{prime_source['api']}?ac=detail&t={tid}&pg={source_pg}")

        raw_items = []
        # 4个并发，非常快
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
            futures = [ex.submit(fetch_data, u) for u in urls]
            for f in concurrent.futures.as_completed(futures):
                d = f.result()
                if d and 'list' in d: raw_items.extend(d['list'])

        # 过滤
        for item in raw_items:
            if is_valid_content(item):
                item['source_key'] = prime_source['key']
                item['source_name'] = prime_source['name']
                final_list.append(item)

        # 如果数量不够20个，再去补充抓取 "国产剧(13)" 和 "电影(6)" 兜底
        if len(final_list) < MAX_ITEMS:
            backup_urls = [
                f"{prime_source['api']}?ac=detail&t=13&pg={source_pg}",
                f"{prime_source['api']}?ac=detail&t=6&pg={source_pg}"
            ]
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
                futures = [ex.submit(fetch_data, u) for u in backup_urls]
                for f in concurrent.futures.as_completed(futures):
                    d = f.result()
                    if d and 'list' in d:
                        for item in d['list']:
                            if is_valid_content(item):
                                item['source_key'] = prime_source['key']
                                item['source_name'] = prime_source['name']
                                if not any(x['vod_name'] == item['vod_name'] for x in final_list):
                                    final_list.append(item)

    seen = set()
    unique_list = []
    for item in final_list:
        if item['vod_name'] in seen: continue
        seen.add(item['vod_name'])
        unique_list.append(item)
    
    # 按更新时间排序 (vod_time 倒序) 通常API返回就是倒序，这里做随机打乱可能更好看
    random.shuffle(unique_list)
    
    # 截取 20 个
    data_slice = unique_list[:MAX_ITEMS]
    
    if len(data_slice) > 0:
        CACHE_HOME[cache_key] = {"data": data_slice, "timestamp": time.time()}
    
    return jsonify({"list": data_slice})

@app.route('/api/search')
def search():
    wd = request.args.get('wd')
    if not wd: return jsonify([])
    sources = get_sources()
    results = []
    def task(s_key):
        s = sources[s_key]
        url = f"{s['api']}?ac=detail&wd={wd}"
        data = fetch_data(url)
        if data and 'list' in data:
            for item in data['list']:
                item['source_key'] = s_key
                item['source_name'] = s['name']
                results.append(item)
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(sources)) as ex:
        ex.map(task, sources.keys())
    return jsonify(results)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)