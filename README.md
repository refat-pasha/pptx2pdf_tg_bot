# 📄 PPTX2PDF Telegram Bot  
### Convert PPTX, DOCX, XLSX, ZIP & more → PDF instantly  
**Bot:** [@dotfiles2pdf_bot](https://t.me/dotfiles2pdf_bot)

---

## 🚀 Overview  
`pptx2pdf_tg_bot` is a Telegram bot that converts office documents (PPTX, PPT, DOCX, DOC, XLSX, ODT, etc.) and ZIP archives into clean, high-quality PDF files using LibreOffice.

The bot is optimized for Telegram users and runs 24/7 using a **Railway Worker Deployment**, with automatic OS detection to support both Windows (local dev) and Linux (production).

---

## ✨ Features  
### 🔄 **Document Conversion**
- Convert **PPTX → PDF**
- Convert **PPT → PDF**
- Convert **DOCX/DOC → PDF**
- Convert **XLSX → PDF**
- Convert **ODT/ODS → PDF**
- Convert **ZIP → Batch PDF**
- Up to **100MB file size**

### 📦 **ZIP Support**
- If user uploads multiple documents:
  - Ask: “Send PDFs individually or ZIP them?”
  - Return either:
    - Individual files  
    - One ZIP file containing all converted PDFs

### 📤 **Progress Updates**
- `Uploading…`
- `Converting…`
- `Preparing your file…`

### 🖥 Cross-Platform LibreOffice Support
- Detect Windows → use  
  `C:\Program Files\LibreOffice\program\soffice.exe`
- Detect Linux → use  
  `/usr/bin/libreoffice`

### ⚡ **Fast & Reliable**
- Non-blocking asynchronous Telegram handling  
- Uses Python `python-telegram-bot v21+`  
- Clean filename preservation (example:  
  `Lecture_01.pptx → Lecture_01.pdf`)

### 🌐 **Runs 24/7**
- Hosted on Railway using **Worker Mode**  
- Dockerized environment  
- LibreOffice installed in container

---

## 🛠 Tech Stack  
- **Python 3.10+**  
- **python-telegram-bot**  
- **LibreOffice**  
- **Docker**  
- **Railway (Worker Deployment)**  
- **asyncio**  

---

## 📁 Project Structure  
```bash
pptx2pdf_tg_bot/
│
├── bot.py                # Main Telegram bot logic
├── converter.py          # (optional) Conversion helper
├── requirements.txt      # Python dependencies
├── Dockerfile            # Container setup (LibreOffice included)
├── start.sh              # Entry point for Railway
└── README.md             # Project documentation
