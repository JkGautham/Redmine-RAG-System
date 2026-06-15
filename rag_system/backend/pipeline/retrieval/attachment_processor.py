"""
Stage 2c: Attachment Processor

No model needed for PDF/text/patch — pure file I/O + libraries.
Image OCR uses pytesseract (tesseract must be installed on system).

Attachment URLs in the scraped data are like "/attachments/13".
Files are downloaded on demand to ATTACHMENTS_CACHE_DIR.
"""

import os
from PIL import Image
try:
    from pytesseract import image_to_string
except ImportError:
    image_to_string = None

import pdfplumber
import requests
from config import REDMINE_BASE_URL, REDMINE_SESSION_COOKIE, ATTACHMENTS_CACHE_DIR

MAX_FILE_SIZE = 10 * 1024 * 1024   # 10 MB

os.makedirs(ATTACHMENTS_CACHE_DIR, exist_ok=True)


def process_attachment(attachment: dict) -> dict:
    """
    Routes an attachment to the correct extractor based on content_type.
    Downloads from Redmine URL if not already cached on disk.
    Returns: {"filename": ..., "type": ..., "text": ..., "error": ...}
    """
    filename     = attachment.get("filename", "unknown")
    content_type = attachment.get("content_type", "").lower()
    url          = attachment.get("url", "")
    att_id       = attachment.get("attachment_id", "")

    result = {
        "filename":     filename,
        "content_type": content_type,
        "text":         "",
        "error":        None
    }

    # Build local cache path
    safe_name = f"{att_id}_{filename}" if att_id else filename
    disk_path = os.path.join(ATTACHMENTS_CACHE_DIR, safe_name)

    # Download if not cached
    if not os.path.exists(disk_path):
        downloaded = _download_attachment(url, disk_path)
        if not downloaded:
            result["error"] = f"Download failed for {url} → {disk_path}"
            return result

    # Route by type
    try:
        if content_type.startswith("image/"):
            result["text"] = _ocr_image(disk_path)
            result["type"] = "ocr"

        elif content_type == "application/pdf":
            result["text"] = _extract_pdf(disk_path)
            result["type"] = "pdf"

        elif _is_patch_file(filename, content_type):
            result["text"] = _read_text_file(disk_path)
            result["type"] = "patch"

        elif _is_text_file(content_type, filename):
            result["text"] = _read_text_file(disk_path)
            result["type"] = "text"

        else:
            result["error"] = f"Unsupported type: {content_type}"

    except Exception as e:
        result["error"] = str(e)

    return result


def _ocr_image(path: str) -> str:
    """Tesseract OCR on PNG/JPG/GIF screenshots."""
    if image_to_string is None:
        return "[pytesseract not installed — cannot OCR image]"
    img = Image.open(path)
    w, h = img.size
    if w < 1000:
        scale = 1000 / w
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    return image_to_string(img, lang="eng").strip()


def _extract_pdf(path: str) -> str:
    """pdfplumber for text PDFs."""
    pages_text = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages_text.append(text.strip())
    return "\n\n".join(pages_text)


def _read_text_file(path: str, max_bytes: int = 50_000) -> str:
    """Plain text read — for .patch, .diff, .txt, .log, .rb, .py etc."""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read(max_bytes)


def _is_patch_file(filename: str, content_type: str) -> bool:
    patch_ext   = {".patch", ".diff", ".patch.gz"}
    patch_types = {"text/x-patch", "text/x-diff", "application/x-patch"}
    ext = os.path.splitext(filename)[1].lower()
    return ext in patch_ext or content_type in patch_types


def _is_text_file(content_type: str, filename: str) -> bool:
    text_types = {
        "text/plain", "text/html", "text/csv", "application/json",
        "text/x-ruby", "text/x-python", "text/x-shellscript"
    }
    text_ext = {
        ".txt", ".log", ".md", ".csv", ".json", ".rb",
        ".py", ".sh", ".yml", ".yaml", ".xml", ".conf"
    }
    ext = os.path.splitext(filename)[1].lower()
    return content_type in text_types or ext in text_ext


def _download_attachment(url: str, disk_path: str) -> bool:
    """
    Download attachment from Redmine.
    URL format from scraper: "/attachments/13" (relative) or full URL.
    Session cookie is optional — public attachments work without it.
    """
    if not url:
        return False
    full_url = url if url.startswith("http") else REDMINE_BASE_URL + url
    cookies  = {"_redmine_session": REDMINE_SESSION_COOKIE} if REDMINE_SESSION_COOKIE else {}
    try:
        os.makedirs(os.path.dirname(disk_path), exist_ok=True)
        resp = requests.get(full_url, cookies=cookies, timeout=30, stream=True)
        if resp.status_code == 200:
            with open(disk_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            return True
    except Exception:
        pass
    return False


def process_attachments_for_issue(issue_id: int, attachment_index: list[dict]) -> list[dict]:
    """
    Process all attachments for an issue.
    Skips files > 10 MB.
    """
    results = []
    for att in attachment_index:
        if att.get("file_size", 0) > MAX_FILE_SIZE:
            results.append({
                "filename": att.get("filename", "unknown"),
                "type": "skipped",
                "text": f"[File too large: {att['file_size']} bytes]",
                "error": None
            })
            continue
        results.append(process_attachment(att))
    return results
