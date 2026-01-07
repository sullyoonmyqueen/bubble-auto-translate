# 🫧 泡泡智慧翻譯器 (AI Screen Translator)

![Python](https://img.shields.io/badge/Python-3.10%2B-blue) ![License](https://img.shields.io/badge/License-GPL%20v3%20(Non--Commercial)-red) ![AI](https://img.shields.io/badge/Backend-Google%20Gemini-orange)

這是一個基於 Google Gemini AI 的即時螢幕翻譯工具。它能監控螢幕上的特定區域（例如泡泡對話框），自動辨識韓文並將其翻譯成繁體中文，支援 Web 介面操作與 Discord 同步。

## ✨ 主要功能
- **無需安裝視窗**：全網頁 (Web UI) 操作介面，輕量好用。
- **即時預覽**：設定截圖區域時，可即時看到預覽畫面，精準定位不截歪。
- **多模型切換**：支援 Gemini 2.5 Flash / Pro 以及最新的 3.0 模型。
- **多金鑰輪詢**：可設定多組 Google API Key 自動輪替，避免單一帳號額度不足。
- **背景執行**：程式可隱藏在後台運作，完全不干擾遊戲體驗。
- **Discord 推送**：支援 Webhook，可將翻譯結果同步發送到 Discord 頻道。

---

## 🛠️ 安裝教學

### 1. 安裝 Python
請前往 [Python 官網](https://www.python.org/downloads/) 下載並安裝 Python (建議版本 3.10 以上)。
> ⚠️ **注意**：安裝時請務必勾選 **"Add Python to PATH"**。

### 2. 安裝必要套件
您可以直接執行資料夾中的 `install.bat`，或者在資料夾中按右鍵開啟終端機 (或 cmd)，手動執行以下指令：
```bash
pip install -r requirements.txt

### 3. 啟動程式

點擊 `啟動.bat` ，然後打開瀏覽器輸入 http://127.0.0.1:5000 即可看到控制及設定畫面。

---

## 📜 授權聲明 (License)

本專案採用 **GPL v3** 授權條款，並附加**非商業使用限制**。使用本專案即代表您同意以下所有條款：

### 1. 非商業使用限制 (Non-Commercial Use Only)

> **Free for personal, educational, and non-commercial use only. Any commercial use is strictly prohibited without prior permission.**

（僅限個人、教育及非商業用途。未經許可嚴禁任何商業使用。）

### 2. 開源與分享 (GPL v3 Core)

基於 GPL v3 精神，如果您修改了本程式的原始碼並將其發布（或是作為服務提供），您必須遵守：

* **強制開源**：必須公開您修改後的完整原始碼。
* **版權聲明**：必須保留原作者的版權聲明。
* **專利條款**：本授權包含專利保護條款。

若您有商業授權需求（例如：閉源使用、商業販售），請聯繫作者洽談特別授權。

---

## ⚠️ 免責聲明

本工具僅供個人學習與輔助使用，請勿用於違反遊戲服務條款之行為。開發者不對因使用本工具而導致的任何帳號風險負責。
