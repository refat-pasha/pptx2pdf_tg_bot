import os
import zipfile
import subprocess
from uuid import uuid4
import platform
from PIL import Image
import asyncio

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ───────────────────────────────────────────────
# CREATE DIRECTORIES
# ───────────────────────────────────────────────
os.makedirs("files", exist_ok=True)
os.makedirs("output", exist_ok=True)

MAX_SIZE = 100 * 1024 * 1024   # 100MB


# ───────────────────────────────────────────────
# MEMORY STRUCTURES
# ───────────────────────────────────────────────

USER_IMAGE_BUFFER = {}        # {user_id: [img1, img2, ...]}
USER_LAST_IMAGE_TIME = {}     # {user_id: timestamp}
USER_AWAITING_PDFNAME = {}    # {user_id: [img paths]}


# ───────────────────────────────────────────────
# START COMMAND
# ───────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📄 Send PPT/DOC/ZIP/JPG/PNG and I will convert to PDF!\n"
        "🖼 Multiple images → I will auto-detect and ask for PDF name.\n"
        "⚠  Max file size: 100MB."
    )


# ───────────────────────────────────────────────
# DOCUMENT → PDF (LibreOffice)
# ───────────────────────────────────────────────
def convert_to_pdf(input_file, output_dir="output"):
    system = platform.system()
    if system == "Windows":
        soffice_path = r"C:\Program Files\LibreOffice\program\soffice.exe"
    else:
        soffice_path = "/usr/bin/libreoffice"

    command = [
        soffice_path, "--headless",
        "--convert-to", "pdf",
        input_file, "--outdir", output_dir
    ]

    subprocess.run(command, check=True)

    base = os.path.basename(input_file)
    name = os.path.splitext(base)[0] + ".pdf"
    return f"{output_dir}/{name}"


# ───────────────────────────────────────────────
# SINGLE IMAGE → PDF
# ───────────────────────────────────────────────
def image_to_pdf(image_path, output_path):
    A4_WIDTH, A4_HEIGHT = 595, 842

    img = Image.open(image_path).convert("RGB")
    w, h = img.size

    scale = min(A4_WIDTH / w, A4_HEIGHT / h, 1)
    new_w = int(w * scale)
    new_h = int(h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)

    page = Image.new("RGB", (A4_WIDTH, A4_HEIGHT), "white")
    x = (A4_WIDTH - new_w) // 2
    y = (A4_HEIGHT - new_h) // 2
    page.paste(img, (x, y))

    page.save(output_path)


# ───────────────────────────────────────────────
# MULTI IMAGE MERGE → PDF
# ───────────────────────────────────────────────
def merge_images_to_pdf(image_list, output_path):
    A4_WIDTH, A4_HEIGHT = 595, 842
    pages = []

    for path in image_list:
        img = Image.open(path).convert("RGB")
        w, h = img.size

        scale = min(A4_WIDTH / w, A4_HEIGHT / h, 1)
        new_w = int(w * scale)
        new_h = int(h * scale)
        img = img.resize((new_w, new_h), Image.LANCZOS)

        page = Image.new("RGB", (A4_WIDTH, A4_HEIGHT), "white")
        x = (A4_WIDTH - new_w) // 2
        y = (A4_HEIGHT - new_h) // 2
        page.paste(img, (x, y))
        pages.append(page)

    pages[0].save(output_path, save_all=True, append_images=pages[1:])


# ───────────────────────────────────────────────
# ZIP PROCESSING
# ───────────────────────────────────────────────
async def process_zip(update, file_path):
    extract_dir = f"files/extracted_{uuid4()}"
    os.makedirs(extract_dir, exist_ok=True)

    with zipfile.ZipFile(file_path, "r") as z:
        z.extractall(extract_dir)

    items = []
    for root, _, files in os.walk(extract_dir):
        for f in files:
            items.append(os.path.join(root, f))

    if not items:
        await update.message.reply_text("❌ ZIP is empty.")
        return

    if len(items) == 1:
        pdf = convert_to_pdf(items[0])
        await update.message.reply_document(open(pdf, "rb"))
        return

    buttons = [
        [
            InlineKeyboardButton("📦 ZIP all PDFs", callback_data="zip_all"),
            InlineKeyboardButton("📄 PDFs one by one", callback_data="zip_single")
        ]
    ]

    await update.message.reply_text(
        "ZIP contains multiple files:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

    # Store list for later
    update.user_data["zip_files"] = items


# ───────────────────────────────────────────────
# ZIP DECISION
# ───────────────────────────────────────────────
async def zip_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    files = update.user_data.get("zip_files")
    if not files:
        await q.edit_message_text("Session expired. Send ZIP again.")
        return

    if q.data == "zip_all":
        out_zip = f"output/{uuid4()}.zip"
        with zipfile.ZipFile(out_zip, "w") as z:
            for f in files:
                pdf = convert_to_pdf(f)
                z.write(pdf, os.path.basename(pdf))

        await q.message.reply_document(open(out_zip, "rb"))
        os.remove(out_zip)

    else:
        for f in files:
            pdf = convert_to_pdf(f)
            await q.message.reply_document(open(pdf, "rb"))

    update.user_data["zip_files"] = None


# ───────────────────────────────────────────────
# IMAGE HANDLER (MAIN LOGIC)
# ───────────────────────────────────────────────
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    # Download image
    file = await update.message.photo[-1].get_file()
    img_path = f"files/{uuid4()}.jpg"
    await file.download_to_drive(img_path)

    # Append image
    USER_IMAGE_BUFFER.setdefault(uid, []).append(img_path)
    USER_LAST_IMAGE_TIME[uid] = asyncio.get_event_loop().time()

    # Start 3-second timer task (non-blocking)
    asyncio.create_task(wait_for_images(uid, update, context))


# ───────────────────────────────────────────────
# WAIT FOR 3s NO NEW IMAGES
# ───────────────────────────────────────────────
async def wait_for_images(uid, update, context):
    last_time = USER_LAST_IMAGE_TIME[uid]
    await asyncio.sleep(3)

    # If user sent another image meanwhile → cancel
    if USER_LAST_IMAGE_TIME.get(uid) != last_time:
        return

    # Retrieve collected images
    images = USER_IMAGE_BUFFER.get(uid, [])

    # SINGLE IMAGE
    if len(images) == 1:
        original_name = os.path.splitext(update.message.photo[-1].file_unique_id)[0]
        pdf_path = f"output/{original_name}.pdf"
        image_to_pdf(images[0], pdf_path)

        await update.message.reply_document(open(pdf_path, "rb"))

        USER_IMAGE_BUFFER.pop(uid, None)
        USER_LAST_IMAGE_TIME.pop(uid, None)
        return

    # MULTIPLE IMAGES — ASK FOR NAME
    USER_AWAITING_PDFNAME[uid] = images
    await update.message.reply_text("📘 Multiple images received.\nSend PDF name:")


# ───────────────────────────────────────────────
# USER PROVIDES PDF NAME
# ───────────────────────────────────────────────
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    if uid not in USER_AWAITING_PDFNAME:
        return  # not naming a PDF

    images = USER_AWAITING_PDFNAME.pop(uid)
    name_raw = update.message.text.strip()

    pdf_name = name_raw + ".pdf"
    out_path = f"output/{pdf_name}"

    merge_images_to_pdf(images, out_path)

    await update.message.reply_document(open(out_path, "rb"))

    # full cleanup
    USER_IMAGE_BUFFER.pop(uid, None)
    USER_LAST_IMAGE_TIME.pop(uid, None)


# ───────────────────────────────────────────────
# DOCUMENT HANDLER
# ───────────────────────────────────────────────
async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document

    if doc.file_size > MAX_SIZE:
        await update.message.reply_text("❌ File too large (max 100MB).")
        return

    status = await update.message.reply_text("📥 Downloading…")

    file = await doc.get_file()
    file_path = f"files/{doc.file_name}"
    await file.download_to_drive(file_path)

    await status.edit_text("⚙ Converting…")

    if file_path.endswith(".zip"):
        await process_zip(update, file_path)
        return

    try:
        pdf = convert_to_pdf(file_path)
        await update.message.reply_document(open(pdf, "rb"))
    except Exception as e:
        await status.edit_text(f"❌ Error: {e}")


# ───────────────────────────────────────────────
# MAIN RUN
# ───────────────────────────────────────────────
def run():
    app = ApplicationBuilder().token("YOUR_BOT_TOKEN_HERE").build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file))
    app.add_handler(MessageHandler(filters.TEXT, handle_text))

    app.add_handler(CallbackQueryHandler(zip_decision, pattern="zip"))

    print("Bot running…")
    app.run_polling()


if __name__ == "__main__":
    run()