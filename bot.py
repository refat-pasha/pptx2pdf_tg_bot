import os
import shutil
import subprocess
import tempfile
import zipfile
import platform
from uuid import uuid4

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters


# ---------------------- CONFIG ----------------------
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
TOKEN = os.getenv("8562243904:AAF-ht2W0SXIoyn6RURE0BHbfjlT1ykBV5Y")  # Railway uses env variable
# ----------------------------------------------------


# Global dictionary to hold user files until they choose ZIP or individual
USER_FILES = {}


# Detect correct LibreOffice path (Windows vs Linux)
def get_soffice_path():
    if platform.system() == "Windows":
        return r"C:\Program Files\LibreOffice\program\soffice.exe"
    return "/usr/bin/libreoffice"  # Linux / Railway


# Convert any supported file to PDF using LibreOffice
def convert_to_pdf(input_file, output_dir):
    soffice = get_soffice_path()

    command = [
        soffice,
        "--headless",
        "--convert-to", "pdf",
        input_file,
        "--outdir", output_dir,
    ]

    subprocess.run(command, check=True)

    base = os.path.basename(input_file)
    pdf_name = os.path.splitext(base)[0] + ".pdf"
    return os.path.join(output_dir, pdf_name)


# Cleanup helper
def safe_delete(path):
    try:
        if os.path.isfile(path):
            os.remove(path)
        elif os.path.isdir(path):
            shutil.rmtree(path)
    except:
        pass


# /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome! Send me PPTX, PPT, DOCX, DOC, XLSX, ODT, ZIP or any office file and I’ll convert it to PDF.\n\n"
        "📌 Max file size: 100MB\n"
        "📦 Send multiple files → choose ZIP or individual PDFs.\n"
    )


# Handle document upload
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    doc = update.message.document

    # Check size
    if doc.file_size > MAX_FILE_SIZE:
        await update.message.reply_text("❌ File too large! Max 100MB.")
        return

    await update.message.reply_text("📥 Uploading your file…")

    # Download file
    file = await doc.get_file()

    temp_dir = tempfile.mkdtemp()
    file_path = os.path.join(temp_dir, doc.file_name)

    await file.download_to_drive(file_path)

    # Store files per user
    if user_id not in USER_FILES:
        USER_FILES[user_id] = []

    USER_FILES[user_id].append(file_path)

    # If only one file → convert immediately
    if len(USER_FILES[user_id]) == 1:
        keyboard = [
            [InlineKeyboardButton("Convert This File", callback_data="convert_single")],
            [InlineKeyboardButton("Upload More Files", callback_data="more_files")],
        ]
        await update.message.reply_text("📄 File received! What do you want to do?", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        # Multiple files → ask ZIP or individual
        keyboard = [
            [InlineKeyboardButton("Convert All → ZIP", callback_data="convert_zip")],
            [InlineKeyboardButton("Convert All → Individual PDFs", callback_data="convert_individual")],
        ]
        await update.message.reply_text(
            f"📦 {len(USER_FILES[user_id])} files received! Choose an option:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


# Handle button actions
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    if user_id not in USER_FILES or not USER_FILES[user_id]:
        await query.edit_message_text("❌ No files found. Upload a file first.")
        return

    files = USER_FILES[user_id]

    if query.data == "more_files":
        await query.edit_message_text("📤 Okay! Send more files.")
        return

    # Single file conversion
    if query.data == "convert_single":
        await query.edit_message_text("⚙️ Converting your file…")

        file_path = files[0]
        output_dir = tempfile.mkdtemp()

        try:
            pdf_path = convert_to_pdf(file_path, output_dir)
            await query.message.reply_document(open(pdf_path, "rb"))
        except Exception as e:
            await query.edit_message_text(f"❌ Conversion error: {e}")
        finally:
            safe_delete(output_dir)
            safe_delete(os.path.dirname(file_path))
            USER_FILES[user_id] = []
        return

    # Convert all → Individual PDFs
    if query.data == "convert_individual":
        await query.edit_message_text("⚙️ Converting all files…")

        output_dir = tempfile.mkdtemp()
        try:
            for f in files:
                pdf_path = convert_to_pdf(f, output_dir)
                await query.message.reply_document(open(pdf_path, "rb"))
        except Exception as e:
            await query.edit_message_text(f"❌ Conversion error: {e}")
        finally:
            safe_delete(output_dir)
            for f in files:
                safe_delete(os.path.dirname(f))
            USER_FILES[user_id] = []
        return

    # Convert all → ZIP
    if query.data == "convert_zip":
        await query.edit_message_text("⚙️ Converting all files and creating ZIP…")

        output_dir = tempfile.mkdtemp()
        zip_path = os.path.join(output_dir, f"converted_{uuid4()}.zip")

        try:
            with zipfile.ZipFile(zip_path, "w") as zipf:
                for f in files:
                    pdf_path = convert_to_pdf(f, output_dir)
                    zipf.write(pdf_path, os.path.basename(pdf_path))

            await query.message.reply_document(open(zip_path, "rb"))
        except Exception as e:
            await query.edit_message_text(f"❌ Error: {e}")
        finally:
            safe_delete(output_dir)
            for f in files:
                safe_delete(os.path.dirname(f))
            USER_FILES[user_id] = []
        return


# Main
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(CallbackQueryHandler(button_handler))

    app.run_polling()


if __name__ == "__main__":
    main()