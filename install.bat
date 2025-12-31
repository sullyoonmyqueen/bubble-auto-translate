@echo off
chcp 65001 >nul
title 韓文翻譯器 - 一鍵安裝工具

echo ========================================================
echo        正在為您安裝翻譯器所需的環境...
echo        請確保您已經安裝了 Python 並且已連上網路。
echo ========================================================
echo.

:: 檢查 requirements.txt 是否存在
if not exist requirements.txt (
    color 0C
    echo [錯誤] 找不到 requirements.txt 檔案！
    echo 請確保 install.bat 與 requirements.txt 在同一個資料夾內。
    echo.
    pause
    exit
)

:: 開始安裝套件
echo 正在執行 pip install...
echo.
pip install -r requirements.txt

:: 檢查上一行指令是否成功
if %errorlevel% neq 0 (
    color 0C
    echo.
    echo ========================================================
    echo [失敗] 安裝過程發生錯誤！
    echo.
    echo 可能的原因：
    echo 1. 您尚未安裝 Python (請去 python.org 下載)。
    echo 2. 安裝 Python 時沒勾選 "Add to PATH"。
    echo 3. 網路連線不穩。
    echo ========================================================
    pause
    exit
)

:: 安裝成功
color 0A
echo.
echo ========================================================
echo      ✅ 恭喜！所有套件已安裝完成。
echo      現在您可以點擊 app.pyw 來啟動翻譯器了！
echo ========================================================
echo.
pause