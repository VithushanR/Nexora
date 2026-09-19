"""
backend/routers/documents.py

Part D — Document Upload, Single-Paper Chat.

Owns: this file, backend/uploads/ (storage dir)
Depends on: backend/auth/jwt.py (get_current_user), backend/auth/sanitize.py
            (sanitize_for_prompt), backend/rag/chat.py (build_index, rag_chat)

Endpoints (per handoff doc §D.1):
    POST   /documents/upload                        -> {document_id, title, n_pages}
    POST   /documents/{document_id}/chat             -> {message_id, answer, sources}
    GET    /documents/{document_id}/chat/history      -> [{message_id, role, content, timestamp}, ...]
    DELETE /documents/{document_id}                  -> {deleted: true}

Upload validation order (non-negotiable, §D.1):
    1. Reject if Content-Length exceeds UPLOAD_MAX_SIZE_MB
    2. Reject if the file doesn't start with real PDF magic bytes
    3. Extract text (pypdf) -- treat as fully untrusted, MORE so than
       arXiv PDFs, since this is arbitrary user input
    4. Chunk + embed into an isolated namespace: document:{document_id}
    5. Store the file under UPLOAD_DIR, encrypted at rest (auth/encryption.py),
       scoped to the uploading user

Every document-scoped route is owner-only: a user can only touch their
own documents. A document that exists but belongs to someone else
returns 404 (not 403), so a non-owner can't distinguish "doesn't exist"
from "exists, not yours" -- see _get_owned_document_or_404.
"""

import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status
from pypdf import PdfReader

from backend.auth.encryption import encrypt_bytes
from backend.auth.jwt import get_current_user
from backend.auth.sanitize import sanitize_for_prompt
from backend.rag.chat import build_index, rag_chat

router = APIRouter(prefix="/documents", tags=["documents"])

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

UPLOAD_DIR = os.environ.get(
    "UPLOAD_DIR", os.path.join(os.path.dirname(__file__), "..", "uploads")
)
os.makedirs(UPLOAD_DIR, exist_ok=True)

UPLOAD_MAX_SIZE_MB = int(os.environ.get("UPLOAD_MAX_SIZE_MB", "20"))
UPLOAD_MAX_SIZE_BYTES = UPLOAD_MAX_SIZE_MB * 1024 * 1024

_DB_PATH = os.path.join(UPLOAD_DIR, "documents.db")

# Real PDF files start with this byte sequence ("%PDF-"). Checking this
# instead of trusting the filename/extension is the whole point of step 2
# in the upload validation order -- a renamed .exe or .html file with a
# ".pdf" extension will fail this check.
_PDF_MAGIC_BYTES = b"%PDF-"

_MAX_MESSAGE_LENGTH = 2000  # server-side cap, per B.4-style checklist pattern

# Chunking: simple fixed-size window with overlap. Good enough for RAG
# over a single paper -- no need for anything fancier here.
_CHUNK_SIZE_CHARS = 1000
_CHUNK_OVERLAP_CHARS = 150


# ---------------------------------------------------------------------------
# SQLite setup — document_id -> {user_id, title, n_pages, file_path, created_at}
# and per-document chat history, matching Part A's thread_id table pattern.
# ---------------------------------------------------------------------------

def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _init_db() -> None:
    conn = _get_db()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                document_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                title TEXT NOT NULL,
                n_pages INTEGER NOT NULL,
                file_path TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS document_chat_history (
                message_id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (document_id) REFERENCES documents(document_id)
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


_init_db()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _document_namespace(document_id: str) -> str:
    """Matches the frozen convention from rag/chat.py: 'document:{document_id}'."""
    return f"document:{document_id}"


def _get_owned_document_or_404(document_id: str, user_id: str) -> sqlite3.Row:
    """
    Fetches a document row and verifies ownership in one step.

    Returns 404 (not 403) when the document exists but belongs to someone
    else, so a non-owner can't distinguish "doesn't exist" from "exists,
    not yours" -- this avoids confirming other users' document_ids exist
    at all.
    """
    conn = _get_db()
    try:
        row = conn.execute(
            "SELECT * FROM documents WHERE document_id = ?", (document_id,)
        ).fetchone()
    finally:
        conn.close()

    if row is None or row["user_id"] != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )
    return row


def _chunk_text(text: str) -> list[str]:
    """
    Splits extracted PDF text into overlapping fixed-size chunks for
    embedding. Overlap helps avoid losing context at chunk boundaries
    (e.g. a sentence split across two chunks still appears whole in at
    least one of them).
    """
    text = text.strip()
    if not text:
        return []

    chunks = []
    start = 0
    text_len = len(text)
    step = _CHUNK_SIZE_CHARS - _CHUNK_OVERLAP_CHARS

    while start < text_len:
        end = min(start + _CHUNK_SIZE_CHARS, text_len)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == text_len:
            break
        start += step

    return chunks


def _delete_rag_index_files(document_id: str) -> None:
    """
    rag/chat.py's frozen interface (§D.2) has no delete_index() function --
    it only defines build_index/query/rag_chat. Since we know its storage
    convention (one .faiss + one .chunks.pkl file per namespace, named
    after the sanitized namespace string), we remove those files directly
    here rather than adding an unplanned function to the frozen interface.

    Mirrors the sanitization logic in rag/chat.py's _sanitize_namespace:
    ':' becomes '_', so "document:abc-123" -> "document_abc-123".
    """
    from backend.rag.chat import _INDEX_STORE_DIR  # local import: internal detail, not part of the frozen public interface

    namespace = _document_namespace(document_id)
    sanitized = re.sub(r"[^a-zA-Z0-9_\-]", "_", namespace)

    index_path = os.path.join(_INDEX_STORE_DIR, f"{sanitized}.faiss")
    chunks_path = os.path.join(_INDEX_STORE_DIR, f"{sanitized}.chunks.pkl")

    for path in (index_path, chunks_path):
        if os.path.exists(path):
            os.remove(path)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_document(
    request: Request,
    file: UploadFile,
    user_id: str = Depends(get_current_user),
):
    """
    Uploads a PDF, extracts and chunks its text, and builds a RAG index
    for it under an isolated document:{document_id} namespace.

    Validation runs in the exact order specified in §D.1:
        1. Content-Length size check
        2. Real PDF magic-byte check (not just filename/extension)
        3. Text extraction (treated as fully untrusted)
        4. Chunk + embed into an isolated namespace
        5. Store the file under UPLOAD_DIR, encrypted at rest
    """
    # --- 1. Size check ---
    content_length = request.headers.get("content-length")
    if content_length is not None and int(content_length) > UPLOAD_MAX_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the {UPLOAD_MAX_SIZE_MB}MB upload limit.",
        )

    file_bytes = await file.read()

    # Content-Length can be absent/spoofed, so re-check the actual bytes
    # read regardless of what the header claimed.
    if len(file_bytes) > UPLOAD_MAX_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the {UPLOAD_MAX_SIZE_MB}MB upload limit.",
        )

    # --- 2. Real PDF magic-byte check ---
    if not file_bytes.startswith(_PDF_MAGIC_BYTES):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File is not a valid PDF (failed magic-byte check).",
        )

    # --- 3. Extract text (untrusted) ---
    document_id = str(uuid.uuid4())
    temp_path = os.path.join(UPLOAD_DIR, f"_tmp_{document_id}.pdf")
    with open(temp_path, "wb") as f:
        f.write(file_bytes)

    try:
        reader = PdfReader(temp_path)
        n_pages = len(reader.pages)
        full_text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        os.remove(temp_path)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not parse PDF. The file may be corrupted or unsupported.",
        )

    if not full_text.strip():
        os.remove(temp_path)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No extractable text found in this PDF (it may be a scanned image with no OCR layer).",
        )

    # Extracted text is arbitrary user input -- more untrusted than an
    # arXiv PDF the pipeline itself fetched. Sanitize every chunk before
    # it is embedded, since embedded text later flows into rag_chat()
    # prompts via query() results.
    chunks = [sanitize_for_prompt(c) for c in _chunk_text(full_text)]
    chunks = [c for c in chunks if c]  # drop any chunk that sanitized to empty

    if not chunks:
        os.remove(temp_path)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No usable text content remained after sanitization.",
        )

    # --- 4. Chunk + embed into isolated namespace ---
    build_index(chunks, namespace=_document_namespace(document_id))

    # --- 5. Store the file under UPLOAD_DIR, encrypted at rest ---
    # file_bytes (the original plaintext upload) is encrypted and written
    # to final_path. temp_path (plaintext, used only for pypdf parsing
    # above) is removed rather than renamed, since it must never persist
    # on disk unencrypted.
    title = file.filename or f"document-{document_id}.pdf"
    final_path = os.path.join(UPLOAD_DIR, f"{document_id}.pdf")
    encrypted_bytes = encrypt_bytes(file_bytes)
    with open(final_path, "wb") as f:
        f.write(encrypted_bytes)
    os.remove(temp_path)

    conn = _get_db()
    try:
        conn.execute(
            "INSERT INTO documents (document_id, user_id, title, n_pages, file_path, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (document_id, user_id, title, n_pages, final_path, _now_iso()),
        )
        conn.commit()
    finally:
        conn.close()

    return {"document_id": document_id, "title": title, "n_pages": n_pages}


@router.post("/{document_id}/chat")
async def chat_with_document(
    document_id: str,
    body: dict,
    user_id: str = Depends(get_current_user),
):
    """
    Chats with a single uploaded document, grounded via rag_chat() over
    that document's isolated namespace. Owner-only.
    """
    _get_owned_document_or_404(document_id, user_id)

    message = body.get("message")
    if not message or not isinstance(message, str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="'message' is required and must be a string.",
        )

    if len(message) > _MAX_MESSAGE_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Message exceeds the {_MAX_MESSAGE_LENGTH} character limit.",
        )

    # Sanitize the user's message before it reaches any prompt, per D.3/B.4.
    safe_message = sanitize_for_prompt(message)

    namespace = _document_namespace(document_id)
    answer = rag_chat(namespace, safe_message)

    message_id = str(uuid.uuid4())
    timestamp = _now_iso()

    conn = _get_db()
    try:
        conn.execute(
            "INSERT INTO document_chat_history (message_id, document_id, role, content, timestamp) "
            "VALUES (?, ?, 'user', ?, ?)",
            (str(uuid.uuid4()), document_id, safe_message, timestamp),
        )
        conn.execute(
            "INSERT INTO document_chat_history (message_id, document_id, role, content, timestamp) "
            "VALUES (?, ?, 'assistant', ?, ?)",
            (message_id, document_id, answer, timestamp),
        )
        conn.commit()
    finally:
        conn.close()

    # Sources are page-level per §D.1's response shape ({"sources": [{"page": 4}]}),
    # but rag/chat.py's frozen query()/rag_chat() interface does not track
    # page numbers per chunk -- only text + score. Returning an empty list
    # here rather than fabricating page numbers we don't actually have.
    return {"message_id": message_id, "answer": answer, "sources": []}


@router.get("/{document_id}/chat/history")
async def get_document_chat_history(
    document_id: str,
    user_id: str = Depends(get_current_user),
):
    """Returns this document's chat history, oldest first. Owner-only."""
    _get_owned_document_or_404(document_id, user_id)

    conn = _get_db()
    try:
        rows = conn.execute(
            "SELECT message_id, role, content, timestamp FROM document_chat_history "
            "WHERE document_id = ? ORDER BY timestamp ASC",
            (document_id,),
        ).fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]


@router.delete("/{document_id}")
async def delete_document(
    document_id: str,
    user_id: str = Depends(get_current_user),
):
    """
    Deletes a document: its DB row, its chat history, its file on disk,
    and its RAG index files. Owner-only. Per D.4 checklist: deletion must
    actually remove both the file and its RAG index, not just the DB row.
    """
    row = _get_owned_document_or_404(document_id, user_id)

    # Remove the stored file.
    if os.path.exists(row["file_path"]):
        os.remove(row["file_path"])

    # Remove the RAG index files for this namespace.
    _delete_rag_index_files(document_id)

    # Remove DB records (history first, to respect the foreign key).
    conn = _get_db()
    try:
        conn.execute(
            "DELETE FROM document_chat_history WHERE document_id = ?", (document_id,)
        )
        conn.execute("DELETE FROM documents WHERE document_id = ?", (document_id,))
        conn.commit()
    finally:
        conn.close()

    return {"deleted": True}
