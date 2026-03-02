import os
import zipfile
import subprocess
from uuid import uuid4
import platform
from PIL import Image

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputFile,
)
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# Create directories
os.makedirs("files", exist_ok=True)
os.makedirs("output", exist_ok=True)

MAX_SIZE = 100 * 1024 * 1024  # 100MB

# Store waiting decisions
USER_PENDING_ZIP = {}
USER_PENDING_IMAGES = {}  # store images before merge decision


# -----------------------------
# START COMMAND
# -----------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📄 Send me PPT/DOC/JPG/PNG/ZIP and I will convert to PDF!\n"
        "🖼 Multiple images = I will ask if you want to merge.\n"
        "⚠ Max file size: 100MB."
    )


# -----------------------------
# DOCUMENT → PDF
# -----------------------------
def convert_to_pdf(input_file, output_dir="output"):
    system = platform.system()

    if system == "Windows":
        soffice_path = r"C:\Program Files\LibreOffice\program\soffice.exe"
    else:
        soffice_path = "/usr/bin/libreoffice"

    command = [
        soffice_path,
        "--headless",
        "--convert-to",
        "pdf",
        input_file,
        "--outdir",
        output_dir,
    ]

    subprocess.run(command, check=True)

    base = os.path.basename(input_file)
    name = os.path.splitext(base)[0] + ".pdf"
    return f"{output_dir}/{name}"


# -----------------------------
# IMAGE → SINGLE-PAGE A4 PDF
# -----------------------------
def image_to_pdf(image_path, output_path):
    A4_WIDTH, A4_HEIGHT = 595, 842  # Portrait

    image = Image.open(image_path).convert("RGB")
    w, h = image.size

    # Scale down if larger than page
    scale = min(A4_WIDTH / w, A4_HEIGHT / h, 1)
    new_w = int(w * scale)
    new_h = int(h * scale)
    image = image.resize((new_w, new_h), Image.LANCZOS)

    # Create white A4 page
    page = Image.new("RGB", (A4_WIDTH, A4_HEIGHT), "white")

    # Center the image
    x = (A4_WIDTH - new_w) // 2
    y = (A4_HEIGHT - new_h) // 2

    page.paste(image, (x, y))
    page.save(output_path)


# -----------------------------
# MULTI-IMAGE MERGE → PDF
# -----------------------------
def merge_images_to_pdf(image_list, output_path):
    A4_WIDTH, A4_HEIGHT = 595, 842

    pages = []
    for img_path in image_list:
        img = Image.open(img_path).convert("RGB")
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


# -----------------------------
# ZIP PROCESSING
# -----------------------------
async def process_zip(update, file_path):
    extract_folder = f"files/extracted_{uuid4()}"
    os.makedirs(extract_folder, exist_ok=True)

    with zipfile.ZipFile(file_path, "r") as zip_ref:
        zip_ref.extractall(extract_folder)

    file_list = []
    for root, _, files in os.walk(extract_folder):
        for f in files:
            file_list.append(os.path.join(root, f))

    if not file_list:
        await update.message.reply_text("❌ ZIP is empty.")
        return

    if len(file_list) == 1:
        pdf = convert_to_pdf(file_list[0])
        await update.message.reply_document(open(pdf, "rb"))
        return

    USER_PENDING_ZIP[update.effective_user.id] = file_list

    btns = [
        [
            InlineKeyboardButton("📦 ZIP all PDFs", callback_data="zip_all"),
            InlineKeyboardButton("📄 PDFs individually", callback_data="single_all"),
        ]
    ]

    await update.message.reply_text(
        "ZIP contains multiple files. Choose an option:",
        reply_markup=InlineKeyboardMarkup(btns),
    )


# -----------------------------
# ZIP DECISION CALLBACK
# -----------------------------
async def zip_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    files = USER_PENDING_ZIP.get(update.effective_user.id)
    if not files:
        await q.edit_message_text("Session expired. Send ZIP again.")
        return

    if q.data == "zip_all":
        zip_out = f"output/{uuid4()}.zip"
        with zipfile.ZipFile(zip_out, "w") as z:
            for f in files:
                pdf = convert_to_pdf(f)
                z.write(pdf, os.path.basename(pdf))

        await q.edit_message_text("📦 Creating ZIP...")
        await q.message.reply_document(open(zip_out, "rb"))
        os.remove(zip_out)

    else:
        await q.edit_message_text("📄 Sending individually…")
        for f in files:
            pdf = convert_to_pdf(f)
            await q.message.reply_document(open(pdf, "rb"))

    USER_PENDING_ZIP.pop(update.effective_user.id, None)


# -----------------------------
# PHOTO HANDLER (SINGLE / MULTI)
# -----------------------------
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    # Create user list if not exists
    if uid not in USER_PENDING_IMAGES:
        USER_PENDING_IMAGES[uid] = []

    # Download image
    photo = update.message.photo[-1]
    file = await photo.get_file()
    img_path = f"files/{uuid4()}.jpg"
    await file.download_to_drive(img_path)

    USER_PENDING_IMAGES[uid].append(img_path)

    # If only one image received so far → ask user if they want to keep sending
    if len(USER_PENDING_IMAGES[uid]) == 1:
        await update.message.reply_text(
            "🖼 You sent an image.\n"
            "Send more images OR choose an option:",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("➡ Convert this only", callback_data="img_single"),
                    InlineKeyboardButton("📚 Merge all images", callback_data="img_merge"),
                ]
            ])
        )
        return

    # More than one → ask again
    await update.message.reply_text(
        f"🖼 Received {len(USER_PENDING_IMAGES[uid])} images.\nChoose an option:",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📚 Merge images", callback_data="img_merge"),
                InlineKeyboardButton("📄 Convert individually", callback_data="img_multi_single"),
            ]
        ])
    )


# -----------------------------
# IMAGE DECISION CALLBACK
# -----------------------------
async def image_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    uid = update.effective_user.id
    imgs = USER_PENDING_IMAGES.get(uid)

    if not imgs:
        await q.edit_message_text("❌ No images found. Send again.")
        return

    if q.data == "img_single":
        # Convert first image only
        out = f"output/{uuid4()}.pdf"
        image_to_pdf(imgs[0], out)
        await q.edit_message_text("📄 Converting image…")
        await q.message.reply_document(open(out, "rb"))
        USER_PENDING_IMAGES.pop(uid, None)
        return

    if q.data == "img_multi_single":
        await q.edit_message_text("📄 Sending images individually…")
        for img in imgs:
            out = f"output/{uuid4()}.pdf"
            image_to_pdf(img, out)
            await q.message.reply_document(open(out, "rb"))
        USER_PENDING_IMAGES.pop(uid, None)
        return

    if q.data == "img_merge":
        merged_pdf = f"output/{uuid4()}.pdf"
        merge_images_to_pdf(imgs, merged_pdf)
        await q.edit_message_text("📚 Merging images into PDF…")
        await q.message.reply_document(open(merged_pdf, "rb"))
        USER_PENDING_IMAGES.pop(uid, None)
        return


# -----------------------------
# DOCUMENT/FILE HANDLER
# -----------------------------
async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document

    if doc.file_size > MAX_SIZE:
        await update.message.reply_text("❌ File too large (max 100MB).")
        return

    status = await update.message.reply_text("📥 Downloading file…")

    file = await doc.get_file()
    file_path = f"files/{doc.file_name}"
    await file.download_to_drive(file_path)

    await status.edit_text("⚙️ Converting…")

    if file_path.endswith(".zip"):
        await process_zip(update, file_path)
        return

    try:
        pdf = convert_to_pdf(file_path)
        await status.edit_text("📤 Uploading PDF…")
        await update.message.reply_document(open(pdf, "rb"))
    except Exception as e:
        await status.edit_text(f"❌ Conversion error: {e}")


# -----------------------------
# MAIN RUN
# -----------------------------
def run():
    app = ApplicationBuilder().token("8562243904:AAF-ht2W0SXIoyn6RURE0BHbfjlT1ykBV5Y").build()

    app.add_handler(CommandHandler("start", start))

    app.add_handler(MessageHandler(filters.Document.ALL, handle_file))

    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    app.add_handler(CallbackQueryHandler(zip_decision, pattern="zip"))
    app.add_handler(CallbackQueryHandler(image_decision, pattern="img"))

    print("Bot running…")
    app.run_polling()


if __name__ == "__main__":
    run()