# 點對點路線編排工具（P2P Route Tool）

Abilix SKCON9 競賽用工具：在地圖上點選站點排路線、用積木寫點對點／任務函式、
一鍵匯出 **AbilixScratch 3.0 (.srhs)** 或 AbilixChart 3.0 (.chrts) 工程。

## 下載
到 [Releases](../../releases) 下載最新 `點對點路線工具_vX.Y.Z.zip`，解壓後雙擊 `點對點路線工具.exe`。
**免安裝 Python**，程式和資料（config／路線存檔／地圖）在同一資料夾。

## 更新
程式內按「檢查更新」會查詢本倉庫的最新 Release，發現新版會引導下載。
更新只需替換 exe 一個檔案，config 和路線存檔全部保留。

## 功能
- **地圖排路線**：黑白示意圖／現場照片雙檢視，點站點建立 `S → 07 → 03 → S` 路線，
  中間可替換／插入／刪除，輸出純站點字串與含任務字串
- **任務系統**：任務清單 config 可調（拿球 ball／小人 rotate／擡小人 up／藥盒 open…），
  任務筆刷貼到站點，右鍵選單指派
- **程序編輯器（積木）**：13 種積木（路口巡線、高級巡線、轉彎、雙馬達至編碼、
  雙馬達直到灰度停、單顆電機計時、巡线起步、編碼清零、延時、顯示、停車、等待按鈕、呼叫函式）
  組成函式本體；主流程由路線自動生成
- **匯出 .srhs**：生成含函式定義＋主流程的 AbilixScratch 工程，已用反編譯腳本驗證同構
- **匯入 .srhs**：還原函式積木鏈、從主程序呼叫序列反推路線、讀入巡線初始化設定；
  本工具匯出的檔案可無損往返
- **匯出 .chrts**：同樣的函式內容輸出成流程圖工程

## 原始碼執行
需要 Python 3.10+ 與 Pillow：
```bash
pip install pillow
python route_builder.py
```

## 打包 exe
```bash
pip install pyinstaller
python -m PyInstaller --onefile --windowed --icon=icon.ico --name=點對點路線工具 route_builder.py
```

## 發佈新版本
1. `route_builder.py` 開頭 `VERSION` 升版
2. 重新打包 exe，組 release 資料夾並壓 zip
3. git commit + push，然後：
```bash
gh release create v1.2.0 點對點路線工具_v1.2.0.zip --title "v1.2.0" --notes "更新內容"
```
（或用網頁 Releases → Draft a new release 上傳 zip）
程式內「檢查更新」查詢 `releases/latest` API，tag 即版本號。
