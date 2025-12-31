# --- START OF FILE app.py ---

import time
import mss
import numpy as np
from PIL import Image
import requests
import json
import os
import io
import google.generativeai as genai
import collections
from thefuzz import fuzz
import threading
import datetime
import re
from flask import Flask, jsonify, request, send_file, render_template_string

# --- 1. 設定檔管理系統 ---
CONFIG_FILE = 'config.json'

# 預設設定
DEFAULT_CONFIG = {
    "api_keys": [], 
    "model_name": "gemini-2.0-flash", # 預設改為 2.0
    "monitor_area": {"top": 100, "left": 0, "width": 800, "height": 600},
    "check_interval": 4.0, 
    "similarity_threshold": 85,
    "discord_webhook": "" 
}

def load_config():
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return DEFAULT_CONFIG

def save_config(new_config):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(new_config, f, indent=4, ensure_ascii=False)

app_config = load_config()

# --- 2. 狀態變數 ---
app_status = {
    "state": "STOPPED",
    "last_update": "N/A",
    "last_error": None,
    "processed_count": 0,
    "current_image_diff": 0,
    "current_key_index": 0
}
monitor_thread = None
stop_event = threading.Event()

# --- 3. 核心監控邏輯 ---
class ScreenMonitor:
    def __init__(self, stop_event_ref):
        self.stop_event = stop_event_ref
        self.recent_originals = collections.deque(maxlen=20)
        self.current_key_index = 0

    def compare_images(self, img1, img2):
        if img1.size != img2.size or img1.mode != img2.mode: return float('inf')
        img1_small = img1.resize((100, 100))
        img2_small = img2.resize((100, 100))
        img1_gray = np.array(img1_small.convert('L'))
        img2_gray = np.array(img2_small.convert('L'))
        diff = np.sum(np.abs(img1_gray.astype('float') - img2_gray.astype('float')))
        return diff * 10 

    def extract_json_from_text(self, text):
        text = text.strip()
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match: return json.loads(match.group())
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match: return [json.loads(match.group())]
        return json.loads(text)

    def get_translation(self, image_obj):
        keys = app_config.get("api_keys", [])
        if not keys:
            raise Exception("未設定 API 金鑰！請至設定頁面新增。")

        attempts = 0
        max_attempts = len(keys)

        while attempts < max_attempts:
            if self.current_key_index >= len(keys):
                self.current_key_index = 0
            
            api_key = keys[self.current_key_index]
            masked_key = f"{api_key[:4]}...{api_key[-4:]}"
            model_name = app_config.get("model_name", "gemini-2.0-flash")

            try:
                print(f"正在使用金鑰 ({masked_key}) 模型: {model_name}...")
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel(model_name)
                
                prompt = "你是一個翻譯程式。請將圖片中的韓文翻譯成繁體中文。輸出格式必須是純 JSON 陣列，例如：[{\"original\": \"韓文原文\", \"translated\": \"中文翻譯\"}]。不要輸出 markdown 代碼。"
                
                response = model.generate_content([prompt, image_obj], request_options={"timeout": 30})
                result = self.extract_json_from_text(response.text)
                return result

            except Exception as e:
                err_str = str(e).lower()
                if "429" in err_str or "quota" in err_str:
                    print(f"金鑰 {masked_key} 額度已滿或請求過快，切換下一個...")
                    self.current_key_index += 1
                    time.sleep(2) 
                else:
                    print(f"API 錯誤: {e}")
                    raise e 
            
            attempts += 1
        
        raise Exception("所有 API 金鑰皆暫時無法使用 (429/Quota) 或發生錯誤。")

    def run(self):
        global app_status
        app_status["state"] = "RUNNING"
        app_status["last_error"] = None
        last_image = None
        
        print("監控執行緒啟動...")

        with mss.mss() as sct:
            while not self.stop_event.is_set():
                try:
                    area = app_config["monitor_area"]
                    interval = float(app_config.get("check_interval", 4.0))
                    
                    monitor = {
                        "top": int(area["top"]),
                        "left": int(area["left"]),
                        "width": int(area["width"]),
                        "height": int(area["height"])
                    }
                    
                    sct_img = sct.grab(monitor)
                    current_image = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                    
                    app_status["last_update"] = datetime.datetime.now().strftime("%H:%M:%S")

                    if last_image is None:
                        last_image = current_image
                        time.sleep(interval)
                        continue

                    diff = self.compare_images(last_image, current_image)
                    app_status["current_image_diff"] = diff
                    
                    if diff > 10000: 
                        print(f"偵測到畫面變動 (Diff: {diff})，開始翻譯...")
                        last_image = current_image
                        translations = self.get_translation(current_image)
                        
                        if translations:
                            for item in translations:
                                original = item.get('original', '').strip()
                                translated = item.get('translated', '').strip()
                                
                                is_duplicate = False
                                for old in self.recent_originals:
                                    if fuzz.ratio(original, old) > app_config.get("similarity_threshold", 85):
                                        is_duplicate = True
                                        break
                                
                                if not is_duplicate and original:
                                    webhook = app_config.get("discord_webhook")
                                    msg = f"**原文:** {original}\n**翻譯:** {translated}"
                                    print(f"翻譯結果: {original} -> {translated}")
                                    if webhook:
                                        try:
                                            requests.post(webhook, json={"content": msg})
                                        except: pass
                                    
                                    self.recent_originals.append(original)
                                    app_status["processed_count"] += 1

                    app_status["last_error"] = None
                    time.sleep(interval)

                except Exception as e:
                    error_msg = str(e)
                    print(f"錯誤: {error_msg}")
                    app_status["last_error"] = error_msg
                    time.sleep(5)

        app_status["state"] = "STOPPED"
        print("監控執行緒停止。")

# --- 4. Flask 網頁伺服器 ---
app = Flask(__name__)

HTML_TEMPLATE = """
<!doctype html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>泡泡自動翻譯器</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f4f6f9; margin: 0; padding: 0; color: #333; }
        .navbar { background: #212529; color: white; padding: 1rem; display: flex; justify-content: space-between; align-items: center; }
        .navbar h1 { margin: 0; font-size: 1.2rem; }
        .nav-links button { background: none; border: none; color: #aaa; font-size: 1rem; cursor: pointer; padding: 0.5rem 1rem; margin-left: 10px; transition: 0.3s; }
        .nav-links button:hover { color: white; }
        .nav-links button.active { color: #fff; font-weight: bold; border-bottom: 3px solid #0d6efd; }
        
        .container { max-width: 900px; margin: 2rem auto; padding: 0 1rem; }
        .card { background: white; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.08); padding: 2rem; margin-bottom: 2rem; }
        
        .status-box { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1.5rem; text-align: center; margin-bottom: 2rem; }
        .stat-item { background: #f8f9fa; padding: 1.5rem; border-radius: 8px; border: 1px solid #e9ecef; }
        .stat-value { font-size: 2rem; font-weight: bold; color: #0d6efd; }
        .stat-label { font-size: 0.9rem; color: #666; margin-top: 5px; }

        .control-panel { display: flex; gap: 15px; justify-content: center; }
        .btn { padding: 0.8rem 2rem; border: none; border-radius: 6px; cursor: pointer; font-size: 1.1rem; font-weight: 600; transition: 0.2s; color: white; display: flex; align-items: center; gap: 8px; }
        .btn-start { background: #198754; } .btn-start:hover { background: #157347; box-shadow: 0 4px 12px rgba(25, 135, 84, 0.3); }
        .btn-stop { background: #dc3545; } .btn-stop:hover { background: #bb2d3b; box-shadow: 0 4px 12px rgba(220, 53, 69, 0.3); }
        .btn-restart { background: #ffc107; color: #000; } .btn-restart:hover { background: #ffca2c; box-shadow: 0 4px 12px rgba(255, 193, 7, 0.3); }
        .btn-save { background: #0d6efd; width: 100%; justify-content: center; } .btn-save:hover { background: #0b5ed7; }
        .btn-refresh { background: #6c757d; font-size: 0.9rem; padding: 0.5rem 1rem; }

        .form-group { margin-bottom: 1.5rem; }
        .form-group label { display: block; margin-bottom: 0.5rem; font-weight: 600; color: #495057; }
        .form-group input, .form-group select, .form-group textarea { width: 100%; padding: 0.8rem; border: 1px solid #ced4da; border-radius: 6px; box-sizing: border-box; font-size: 1rem; }
        .form-group textarea { font-family: monospace; font-size: 0.9rem; }
        
        .coord-inputs { display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; }
        .coord-inputs input { text-align: center; }
        
        .preview-area { text-align: center; background: #212529; padding: 20px; border-radius: 8px; min-height: 250px; display: flex; align-items: center; justify-content: center; overflow: hidden; margin-top: 1rem; }
        .preview-area img { max-width: 100%; max-height: 450px; border: 2px solid #555; box-shadow: 0 0 20px rgba(0,0,0,0.5); }
        
        .hidden { display: none; }
        .error-msg { color: #842029; background: #f8d7da; border: 1px solid #f5c2c7; padding: 1rem; border-radius: 8px; margin-bottom: 1.5rem; display: none; }
        
        /* 狀態指示燈 */
        .status-indicator { display: inline-block; width: 12px; height: 12px; border-radius: 50%; margin-right: 8px; }
        .status-running .status-indicator { background-color: #198754; box-shadow: 0 0 8px #198754; }
        .status-stopped .status-indicator { background-color: #dc3545; }
    </style>
</head>
<body>

<div class="navbar">
    <div style="display: flex; align-items: center;">
        <span style="font-size: 1.5rem; margin-right: 10px;"></span>
        <h1>泡泡自動翻譯器</h1>
    </div>
    <div class="nav-links">
        <button onclick="switchTab('dashboard')" id="tab-dashboard" class="active">儀表板</button>
        <button onclick="switchTab('settings')" id="tab-settings">系統設定</button>
    </div>
</div>

<div class="container">
    <!-- 錯誤訊息區 -->
    <div id="global-error" class="error-msg"></div>

    <!-- 儀表板頁面 -->
    <div id="view-dashboard">
        <div class="card">
            <h2 id="status-header" class="status-stopped">
                <span class="status-indicator"></span>
                系統狀態: <span id="status-text">已停止</span>
            </h2>
            
            <div class="status-box">
                <div class="stat-item"><div class="stat-value" id="processed-count">0</div><div class="stat-label">已翻譯句數</div></div>
                <div class="stat-item"><div class="stat-value" id="image-diff">0</div><div class="stat-label">畫面變動值</div></div>
                <div class="stat-item"><div class="stat-value" id="key-usage">0</div><div class="stat-label">當前金鑰 ID</div></div>
            </div>

            <div class="control-panel">
                <button class="btn btn-start" onclick="control('start')">▶ 啟動</button>
                <button class="btn btn-restart" onclick="control('restart')"> 重啟</button>
                <button class="btn btn-stop" onclick="control('stop')">⏹ 停止</button>
            </div>
            
            <p style="text-align: center; margin-top: 1.5rem; color: #999; font-size: 0.9rem;">
                最後更新: <span id="last-update">--:--:--</span>
            </p>
        </div>
    </div>

    <!-- 設定頁面 -->
    <div id="view-settings" class="hidden">
        <div class="card">
            <h2>⚙️ 參數設定</h2>
            
            <div class="form-group">
                <label>API 金鑰列表 (每行一組)</label>
                <textarea id="setting-keys" rows="5" placeholder="AIzaSy..."></textarea>
            </div>

            <div class="form-group">
                <label>AI 模型選擇</label>
                <select id="setting-model">
                    <option value="gemini-2.0-flash">Gemini 2.0 Flash (推薦：速度最快)</option>
                    <option value="gemini-2.5-flash">Gemini 2.5 Flash (平衡)</option>
                    <option value="gemini-2.5-pro">Gemini 2.5 Pro (高精度)</option>
                    <option value="gemini-3-flash-preview">Gemini 3.0 Flash Preview (搶先體驗)</option>
                    <option value="gemini-3-pro-preview">Gemini 3.0 Pro Preview (最強大)</option>
                </select>
            </div>

            <div class="form-group">
                <label>檢查間隔 (秒)</label>
                <input type="number" id="setting-interval" step="0.5" min="1.0">
                <small style="color:#666">建議值: 2.0 ~ 5.0 秒。過快可能導致 429 錯誤。</small>
            </div>

            <div class="form-group">
                <label>Discord Webhook 網址 (選填)</label>
                <input type="text" id="setting-webhook">
            </div>

            <hr style="margin: 2rem 0; border-top: 1px solid #eee;">

            <div class="form-group">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 10px;">
                    <label style="margin:0">監控區域設定 (截圖座標)</label>
                    <button class="btn btn-refresh" onclick="updatePreview()">更新預覽圖</button>
                </div>
                
                <div class="coord-inputs">
                    <div><small>Top (Y)</small><input type="number" id="area-top" onchange="updatePreview()"></div>
                    <div><small>Left (X)</small><input type="number" id="area-left" onchange="updatePreview()"></div>
                    <div><small>Width</small><input type="number" id="area-width" onchange="updatePreview()"></div>
                    <div><small>Height</small><input type="number" id="area-height" onchange="updatePreview()"></div>
                </div>

                <div class="preview-area">
                    <img id="preview-img" src="" alt="預覽載入中...">
                </div>
                <p style="text-align: center; color: #999; font-size: 0.8rem; margin-top: 5px;">* 請調整座標直到您能完整看到對話框</p>
            </div>

            <button class="btn btn-save" onclick="saveSettings()">儲存並套用設定</button>
        </div>
    </div>
</div>

<script>
    function switchTab(tab) {
        document.querySelectorAll('.nav-links button').forEach(b => b.classList.remove('active'));
        document.getElementById('tab-' + tab).classList.add('active');
        
        document.getElementById('view-dashboard').classList.add('hidden');
        document.getElementById('view-settings').classList.add('hidden');
        document.getElementById('view-' + tab).classList.remove('hidden');

        if(tab === 'settings') loadSettings();
    }

    function updateStatus() {
        if(document.getElementById('view-dashboard').classList.contains('hidden')) return;

        fetch('/status')
            .then(r => r.json())
            .then(data => {
                const header = document.getElementById('status-header');
                const text = document.getElementById('status-text');
                
                if (data.state === 'RUNNING') {
                    header.className = 'status-running';
                    text.innerText = '運作中';
                } else {
                    header.className = 'status-stopped';
                    text.innerText = '已停止';
                }
                
                document.getElementById('processed-count').innerText = data.processed_count;
                document.getElementById('image-diff').innerText = Math.round(data.current_image_diff);
                document.getElementById('key-usage').innerText = (data.current_key_index + 1) + " / " + data.total_keys;
                document.getElementById('last-update').innerText = data.last_update;

                const errDiv = document.getElementById('global-error');
                if (data.last_error) {
                    errDiv.innerHTML = "<strong>⚠️ 系統警告:</strong> " + data.last_error;
                    errDiv.style.display = 'block';
                } else {
                    errDiv.style.display = 'none';
                }
            });
    }

    function control(action) {
        // 給按鈕一點回饋感
        fetch('/' + action, { method: 'POST' })
            .then(r => r.json())
            .then(data => {
                if(action === 'restart') alert('正在重啟系統，請稍候...');
                setTimeout(updateStatus, 500);
            });
    }

    function loadSettings() {
        fetch('/api/config')
            .then(r => r.json())
            .then(cfg => {
                document.getElementById('setting-keys').value = cfg.api_keys.join('\\n');
                document.getElementById('setting-model').value = cfg.model_name; // 自動選中目前的模型
                document.getElementById('setting-interval').value = cfg.check_interval;
                document.getElementById('setting-webhook').value = cfg.discord_webhook;
                
                document.getElementById('area-top').value = cfg.monitor_area.top;
                document.getElementById('area-left').value = cfg.monitor_area.left;
                document.getElementById('area-width').value = cfg.monitor_area.width;
                document.getElementById('area-height').value = cfg.monitor_area.height;
                
                updatePreview(cfg.monitor_area);
            });
    }

    function saveSettings() {
        const data = {
            api_keys: document.getElementById('setting-keys').value.split('\\n').filter(k => k.trim() !== ''),
            model_name: document.getElementById('setting-model').value,
            check_interval: parseFloat(document.getElementById('setting-interval').value),
            discord_webhook: document.getElementById('setting-webhook').value,
            monitor_area: {
                top: parseInt(document.getElementById('area-top').value),
                left: parseInt(document.getElementById('area-left').value),
                width: parseInt(document.getElementById('area-width').value),
                height: parseInt(document.getElementById('area-height').value)
            }
        };

        fetch('/api/config', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(data)
        })
        .then(r => r.json())
        .then(resp => {
            alert('✅ 設定已儲存！下次翻譯將使用新設定。');
        });
    }

    function updatePreview(existingArea = null) {
        let area = existingArea;
        if (!area) {
            area = {
                top: parseInt(document.getElementById('area-top').value) || 0,
                left: parseInt(document.getElementById('area-left').value) || 0,
                width: parseInt(document.getElementById('area-width').value) || 100,
                height: parseInt(document.getElementById('area-height').value) || 100
            };
        }
        const qs = `top=${area.top}&left=${area.left}&width=${area.width}&height=${area.height}&t=${new Date().getTime()}`;
        document.getElementById('preview-img').src = `/api/preview?${qs}`;
    }

    setInterval(updateStatus, 2000);
</script>
</body>
</html>
"""

# --- 5. Flask 路由 ---

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/status')
def status():
    app_status['total_keys'] = len(app_config.get('api_keys', []))
    app_status['current_key_index'] = monitor_thread.current_key_index if monitor_thread else 0
    return jsonify(app_status)

@app.route('/start', methods=['POST'])
def start_monitor():
    global monitor_thread, stop_event
    if monitor_thread is None or not monitor_thread.is_alive():
        if not app_config.get("api_keys"):
            app_status["last_error"] = "請先至設定頁面新增 API Key"
            return jsonify({"status": "Error: No API Keys"})
        stop_event.clear()
        monitor = ScreenMonitor(stop_event)
        monitor_thread = threading.Thread(target=monitor.run)
        monitor_thread.current_key_index = 0
        monitor_thread.start()
        return jsonify({"status": "Started"})
    return jsonify({"status": "Already running"})

@app.route('/stop', methods=['POST'])
def stop_monitor():
    global monitor_thread, stop_event
    if monitor_thread and monitor_thread.is_alive():
        stop_event.set()
        return jsonify({"status": "Stopping"})
    return jsonify({"status": "Not running"})

@app.route('/restart', methods=['POST'])
def restart_monitor():
    global monitor_thread, stop_event
    # 1. 先停止
    if monitor_thread and monitor_thread.is_alive():
        stop_event.set()
        monitor_thread.join(timeout=2) # 等待執行緒結束
        monitor_thread = None
    
    # 2. 稍作等待
    time.sleep(1)
    
    # 3. 再啟動
    if not app_config.get("api_keys"):
         return jsonify({"status": "Error: No API Keys"})
    
    stop_event.clear()
    monitor = ScreenMonitor(stop_event)
    monitor_thread = threading.Thread(target=monitor.run)
    monitor_thread.current_key_index = 0
    monitor_thread.start()
    
    return jsonify({"status": "Restarted"})

@app.route('/api/config', methods=['GET'])
def get_config():
    return jsonify(app_config)

@app.route('/api/config', methods=['POST'])
def update_config_api():
    global app_config
    new_data = request.json
    app_config.update(new_data)
    save_config(app_config)
    return jsonify({"status": "Saved", "config": app_config})

@app.route('/api/preview')
def preview_api():
    try:
        top = int(request.args.get('top', 0))
        left = int(request.args.get('left', 0))
        width = int(request.args.get('width', 800))
        height = int(request.args.get('height', 600))
        
        monitor = {"top": top, "left": left, "width": width, "height": height}
        
        with mss.mss() as sct:
            sct_img = sct.grab(monitor)
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            img_io = io.BytesIO()
            img.save(img_io, 'JPEG', quality=60)
            img_io.seek(0)
            return send_file(img_io, mimetype='image/jpeg')
    except Exception as e:
        return str(e), 500

if __name__ == '__main__':
    print("----------------------------------------------------------------")
    print(" 啟動成功！請打開瀏覽器訪問: http://127.0.0.1:5000")
    print("----------------------------------------------------------------")
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)

# --- END OF FILE ---