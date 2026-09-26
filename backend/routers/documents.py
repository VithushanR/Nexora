"""
backend/routers/documents.py

Part D — Document upload, listing, viewing and deletion.

Owns: this file, backend/uploads/ (encrypted PDFs on disk)
Depends on: backend/documents_store.py (Postgres metadata),
            backend/auth/jwt.py (get_current_user),
            backend/auth/sanitize.py (sanitize_for_prompt),
            backend/rag/chat.py (build_index)

Endpoints:
    POST   /documents/upload            -> {document_id, title, n_pages}
    GET    /documents?session_id=&thread_id=  -> [{document_id, title, n_pages}, ...]
    GET    /documents/{document_id}/file -> the decrypted PDF (owner-only)
    DELETE /documents/{document_id}      -> {deleted: true}

Chatting about a document lives in routers/chat.py (one merged chat
router: general, document/report-grounded, and web-search chat).

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
from "exists, not yours" -- see get_owned_document_or_404.
"""

import logging
import os
import re
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, UploadFile, status
from pypdf import PdfReader

from backend import documents_store
from backend.auth.encryption import decrypt_bytes, encrypt_bytes
from backend.auth.jwt import get_current_user
from backend.auth.sanitize import sanitize_for_prompt
from backend.documents_store import Document
from backend.rag.chat import build_index
from backend.routers.copilot import require_owned_thread

logger = logging.getLogger("nexora.documents")

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

MAX_ID_CHARS = 128

# Real PDF files start with this byte sequence ("%PDF-"). Checking this
# instead of trusting the filename/extension is the whole point of step 2
# in the upload validation order -- a renamed .exe or .html file with a
# ".pdf" extension will fail this check.
_PDF_MAGIC_BYTES = b"%PDF-"

# Chunking: simple fixed-size window with overlap. Good enough for RAG
# over a single paper -- no need for anything fancier here.
_CHUNK_SIZE_CHARS = 1000
_CHUNK_OVERLAP_CHARS = 150


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def document_namespace(document_id: str) -> str:
    """Matches the frozen convention from rag/chat.py: 'document:{document_id}'."""
    return f"document:{document_id}"


async def get_owned_document_or_404(document_id: str, user_id: str) -> Document:
    """
    Fetches a document and verifies ownership in one step.

    Returns 404 (not 403) when the document exists but belongs to someone
    else, so a non-owner can't distinguish "doesn't exist" from "exists,
    not yours" -- this avoids confirming other users' document_ids exist
    at all.
    """
    document = await documents_store.get_document(document_id)
    if document is None or document.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )
    return document


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

    namespace = document_namespace(document_id)
    sanitized = re.sub(r"[^a-zA-Z0-9_\-]", "_", namespace)

    index_path = os.path.join(_INDEX_STORE_DIR, f"{sanitized}.faiss")
    chunks_path = os.path.join(_INDEX_STORE_DIR, f"{sanitized}.chunks.pkl")

    for path in (index_path, chunks_path):
        if os.path.exists(path):
            os.remove(path)


def _clean_id(value: Optional[str]) -> Optional[str]:
    value = (value or "").strip()
    return value[:MAX_ID_CHARS] or None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_document(
    request: Request,
    file: UploadFile,
    session_id: Optional[str] = Form(None),
    thread_id: Optional[str] = Form(None),
    user_id: str = Depends(get_current_user),
):
    """
    Uploads a PDF, extracts and chunks its text, builds a RAG index for it
    under an isolated document:{document_id} namespace, and records it
    against the caller's chat session and/or Deep Search thread so the
    session's document list survives a refresh.

    Validation runs in the exact order specified in §D.1:
        1. Content-Length size check
        2. Real PDF magic-byte check (not just filename/extension)
        3. Text extraction (treated as fully untrusted)
        4. Chunk + embed into an isolated namespace
        5. Store the file under UPLOAD_DIR, encrypted at rest
    """
    session_id = _clean_id(session_id)
    thread_id = _clean_id(thread_id)
    if not session_id and not thread_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="session_id or thread_id is required.",
        )
    if thread_id:
        await require_owned_thread(thread_id, user_id)

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
    # it is embedded, since embedded text later flows into chat prompts via
    # query() results.
    chunks = [sanitize_for_prompt(c) for c in _chunk_text(full_text)]
    chunks = [c for c in chunks if c]  # drop any chunk that sanitized to empty

    if not chunks:
        os.remove(temp_path)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No usable text content remained after sanitization.",
        )

    # --- 4 + 5. Index, encrypt to disk, record. If any later step fails,
    # everything already created is removed so no orphaned index/file is
    # left behind with no database row pointing at it. ---
    title = file.filename or f"document-{document_id}.pdf"
    final_path = os.path.join(UPLOAD_DIR, f"{document_id}.pdf")
    try:
        build_index(chunks, namespace=document_namespace(document_id))
        # file_bytes (the original plaintext upload) is encrypted and written
        # to final_path. temp_path (plaintext, used only for pypdf parsing
        # above) is removed rather than renamed, since it must never persist
        # on disk unencrypted.
        with open(final_path, "wb") as f:
            f.write(encrypt_bytes(file_bytes))
        await documents_store.create_document(
            document_id=document_id,
            user_id=user_id,
            title=title,
            n_pages=n_pages,
            file_path=final_path,
            thread_id=thread_id,
            session_id=session_id,
        )
    except Exception:
        logger.exception("Upload failed after indexing; removing partial artifacts for %s", document_id)
        _delete_rag_index_files(document_id)
        if os.path.exists(final_path):
            os.remove(final_path)
        raise
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

    return {"document_id": document_id, "title": title, "n_pages": n_pages}


@router.get("")
async def list_session_documents(
    session_id: Optional[str] = None,
    thread_id: Optional[str] = None,
    user_id: str = Depends(get_current_user),
):
    """The caller's documents in the given chat session and/or Deep Search
    thread (never the whole library), oldest first. created_at lets the client
    tell which documents were uploaded after the last message was sent."""
    documents = await documents_store.list_documents(
        user_id, session_id=_clean_id(session_id), thread_id=_clean_id(thread_id)
    )
    return [
        {"document_id": d.document_id, "title": d.title, "n_pages": d.n_pages, "created_at": d.created_at.isoformat()}
        for d in documents
    ]


@router.get("/{document_id}/file")
async def get_document_file(
    document_id: str,
    user_id: str = Depends(get_current_user),
):
    """
    Returns the original PDF, decrypted on the fly. Owner-only (404 for
    anyone else). Files are encrypted at rest and there is deliberately no
    static URL for them -- the frontend fetches this with its auth header
    and opens the result as a blob.
    """
    document = await get_owned_document_or_404(document_id, user_id)

    try:
        with open(document.file_path, "rb") as f:
            encrypted_bytes = f.read()
        pdf_bytes = decrypt_bytes(encrypted_bytes)
    except (OSError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document file is unavailable."
        )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "inline", "Cache-Control": "private, no-store"},
    )


@router.delete("/{document_id}")
async def delete_document(
    document_id: str,
    user_id: str = Depends(get_current_user),
):
    """
    Deletes a document: its database row, its file on disk, and its RAG
    index files. Owner-only. Chat messages that referenced it are kept (the
    conversation stays; only the link to the document is cleared). Per D.4
    checklist: deletion must actually remove both the file and its RAG
    index, not just the database row.
    """
    document = await get_owned_document_or_404(document_id, user_id)

    await documents_store.delete_document(document_id)

    if os.path.exists(document.file_path):
        os.remove(document.file_path)
    _delete_rag_index_files(document_id)

    return {"deleted": True}
