import os
import zipfile
import subprocess
from uuid import uuid4

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# Create folders
os.makedirs("files", exist_ok=True)
os.makedirs("output", exist_ok=True)

# Store user pending zip decisions
USER_PENDING = {}

MAX_SIZE = 100 * 1024 * 1024   # 100MB


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📄 Send me any file (PPT, DOC, ZIP, JPG, XLS) and I will convert it to PDF!\n"
        "⚠️ Max file size: 100MB"
    )


# -----------------------------
# PDF Conversion Function
# -----------------------------
import platform

def convert_to_pdf(input_file, output_dir="output"):
    system = platform.system()

    # Windows path
    if system == "Windows":
        soffice_path = r"C:\Program Files\LibreOffice\program\soffice.exe"
    else:
        # Linux / Railway path
        soffice_path = "/usr/bin/libreoffice"

    command = [
        soffice_path,
        "--headless",
        "--convert-to", "pdf",
        input_file,
        "--outdir", output_dir,
    ]

    subprocess.run(command, check=True)
    base = os.path.basename(input_file)
    name = os.path.splitext(base)[0] + ".pdf"
    return f"{output_dir}/{name}"


# -----------------------------
# ZIP Processing
# -----------------------------
async def process_zip(update, file_path):
    extract_folder = f"files/extracted_{uuid4()}"
    os.makedirs(extract_folder, exist_ok=True)

    with zipfile.ZipFile(file_path, "r") as zip_ref:
        zip_ref.extractall(extract_folder)

    # Find all files inside
    file_list = []
    for root, dirs, files in os.walk(extract_folder):
        for f in files:
            file_list.append(os.path.join(root, f))

    if len(file_list) == 0:
        await update.message.reply_text("❌ ZIP file is empty.")
        return

    if len(file_list) == 1:
        # Only one file → convert directly
        pdf_path = convert_to_pdf(file_list[0])
        await update.message.reply_document(open(pdf_path, "rb"))
        return

    # Multiple files → Ask user
    USER_PENDING[update.effective_user.id] = file_list

    buttons = [
        [
            InlineKeyboardButton("📁 Get ZIP of all PDFs", callback_data="zip_all"),
            InlineKeyboardButton("📄 Send PDFs individually", callback_data="single_all"),
        ]
    ]

    await update.message.reply_text(
        "This ZIP contains multiple files. What do you want?",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


# -----------------------------
# User Choice Callback
# -----------------------------
async def zip_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    files = USER_PENDING.get(update.effective_user.id)
    if not files:
        await query.edit_message_text("Session expired. Please send ZIP again.")
        return

    if query.data == "zip_all":
        # Convert all → zip
        zip_out = f"output/{uuid4()}.zip"
        with zipfile.ZipFile(zip_out, "w") as z:
            for f in files:
                pdf = convert_to_pdf(f)
                z.write(pdf, os.path.basename(pdf))

        await query.edit_message_text("📦 Creating ZIP...")
        await query.message.reply_document(open(zip_out, "rb"))

        os.remove(zip_out)

    elif query.data == "single_all":
        await query.edit_message_text("📄 Sending PDFs individually...")
        for f in files:
            pdf = convert_to_pdf(f)
            await query.message.reply_document(open(pdf, "rb"))

    USER_PENDING.pop(update.effective_user.id, None)


# -----------------------------
# File Handler
# -----------------------------
async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document

    # -----------------------------
    # Check file size
    # -----------------------------
    if doc.file_size > MAX_SIZE:
        await update.message.reply_text("❌ File too large! Max allowed: 100MB.")
        return

    # -----------------------------
    # Begin message
    # -----------------------------
    status = await update.message.reply_text("📥 Downloading file...")

    file = await doc.get_file()

    file_id = uuid4()
    file_path = f"files/{doc.file_name}"
    await file.download_to_drive(file_path)

    await status.edit_text("⚙️ Converting file...")

    # -----------------------------
    # ZIP HANDLING
    # -----------------------------
    if file_path.endswith(".zip"):
        await process_zip(update, file_path)
        return

    # -----------------------------
    # Normal conversion
    # -----------------------------
    try:
        pdf_path = convert_to_pdf(file_path)

        await status.edit_text("📤 Uploading PDF...")
        await update.message.reply_document(open(pdf_path, "rb"))

    except Exception as e:
        await status.edit_text(f"❌ Conversion error: {e}")


# -----------------------------
# MAIN
# -----------------------------
def run():
    app = ApplicationBuilder().token("8562243904:AAF-ht2W0SXIoyn6RURE0BHbfjlT1ykBV5Y").build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file))
    app.add_handler(CallbackQueryHandler(zip_decision))

    print("Bot running…")
    app.run_polling()


if __name__ == "__main__":
    run()