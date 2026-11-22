"""Signing an issued revision: append the signer's attestation page, then hash the final bytes.

PAdES (pyHanko, PAdES-B-LTA with an RFC 3161 timestamp) is not wired yet: it needs a signing certificate
and a timestamp authority per deployment. When it is, it slots in after ``attest`` and before the hash,
and ``signature["method"]`` becomes ``"pades"``. Nothing printed in the file ever claims its own hash.
"""

import hashlib
import io
from typing import Any

from pypdf import PdfReader, PdfWriter

from ...infrastructure.pdf import Document, render_pdf


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def attest(stamped: bytes, attestation: dict[str, Any], label: str) -> bytes:
    """``stamped`` with a signature attestation page appended and the signer in the document metadata."""
    page = Document(title="Signature attestation", subtitle=label, footer=label)
    page.fields(
        [
            ("Dossier", label),
            ("Signed by", f"{attestation['signer_name']} <{attestation['signer_email']}>"),
            ("Authority", attestation["authority"]),
            ("Signed at (UTC)", attestation["signed_at"]),
            ("Method", attestation["method"]),
            ("Intent statement", f"{attestation['intent_statement']} (version {attestation['intent_version']})"),
            ("From address", attestation.get("ip") or "-"),
            ("Content SHA-256 before signing", attestation["content_sha256"]),
        ]
    )
    page.paragraph(
        "The SHA-256 of this signed file is recorded with the dossier revision and in the audit ledger; "
        "signed-in users can check a copy against it on the dossier screen."
    )
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(stamped)))
    for p in PdfReader(io.BytesIO(render_pdf(page))).pages:
        writer.add_page(p)
    writer.add_metadata({"/Author": attestation["signer_name"], "/Keywords": f"signed {attestation['signed_at']}"})
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
