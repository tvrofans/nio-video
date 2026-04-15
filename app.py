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
MAX_ITEMS = 20  
BATCH_SIZE = 1  

# --- 核心配置：分类 ID 映射表 ---
TARGET_TYPES = [13, 16, 15, 6, 9, 7, 8, 20]

# 黑名单
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
        # 极速超时配置：连接 2 秒，读取 4 秒
        r = requests.get(url, headers=HEADERS, timeout=(2, 4), verify=False)
        if r.status_code == 200:
            try: return r.json()
            except: return json.loads(r.text)
    except Exception as e:
        pass # 静默处理错误，直接返回 None 让轮询机制接手
    return None

def is_valid_content(item):
    name = item.get('vod_name', '')
    type_name = item.get('type_name', '')
    
    if not name: return False
    for kw in BANNED_KEYWORDS:
        if kw in name: return False
        if kw in type_name: return False
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
    try:
        action = request.args.get('ac', 'list')
        key = request.args.get('key')
        try: client_pg = int(request.args.get('pg', '1'))
        except: client_pg = 1
        wd = request.args.get('wd', '')
        ids = request.args.get('ids', '')
        sources = get_sources()
        
        # 详情获取
        if key and key in sources:
            base_url = sources[key]['api']
            if action == 'detail': url = f"{base_url}?ac=detail&ids={ids}"
            else: url = f"{base_url}?ac=detail&pg={client_pg}&wd={wd}"
            res_data = fetch_data(url)
            return jsonify(res_data if res_data else {"list": []})
        
        if wd: return jsonify([])

        # 首页缓存
        cache_key = f"page_{client_pg}"
        if cache_key in CACHE_HOME and time.time() - CACHE_HOME[cache_key]['timestamp'] < 60:
            return jsonify({"list": CACHE_HOME[cache_key]['data']})

        # --- 核心修复：多源轮询兜底机制 ---
        active_keys = list(sources.keys())
        random.shuffle(active_keys) # 打乱顺序，保证每次进去首选的源不同

        final_list = []
        
        # 遍历所有可用的源，如果第一个挂了就立刻试第二个
        for src_key in active_keys:
            prime_source = sources[src_key]
            selected_types = random.sample(TARGET_TYPES, 4) 
            source_pg = client_pg
            urls = [f"{prime_source['api']}?ac=detail&t={tid}&pg={source_pg}" for tid in selected_types]

            raw_items = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
                futures = [ex.submit(fetch_data, u) for u in urls]
                for f in concurrent.futures.as_completed(futures):
                    d = f.result()
                    if d and isinstance(d, dict) and 'list' in d: 
                        raw_items.extend(d['list'])

            for item in raw_items:
                if isinstance(item, dict) and is_valid_content(item):
                    item['source_key'] = prime_source['key']
                    item['source_name'] = prime_source['name']
                    final_list.append(item)

            # 只要拿到足够的数据，立刻停止尝试其他源，跳出循环
            if len(final_list) >= 8:
                break
                
            # 如果当前源数据不够，清空列表，在下一个循环试下一个源
            final_list = []

        # 数据去重与打乱
        seen = set()
        unique_list = []
        for item in final_list:
            v_name = item.get('vod_name')
            if not v_name or v_name in seen: continue
            seen.add(v_name)
            unique_list.append(item)
        
        random.shuffle(unique_list)
        data_slice = unique_list[:MAX_ITEMS]
        
        if len(data_slice) > 0:
            CACHE_HOME[cache_key] = {"data": data_slice, "timestamp": time.time()}
        
        return jsonify({"list": data_slice})
        
    except Exception as e:
        print(f"API Error: {e}")
        return jsonify({"list": []})

@app.route('/api/search')
def search():
    wd = request.args.get('wd')
    if not wd: return jsonify([])
    sources = get_sources()
    results = []
    def task(s_key):
        try:
            s = sources[s_key]
            url = f"{s['api']}?ac=detail&wd={wd}"
            data = fetch_data(url)
            if data and isinstance(data, dict) and 'list' in data:
                for item in data['list']:
                    if isinstance(item, dict):
                        item['source_key'] = s_key
                        item['source_name'] = s['name']
                        results.append(item)
        except: pass
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(sources)) as ex:
        ex.map(task, sources.keys())
    return jsonify(results)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
