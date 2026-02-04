"""
Extractor de text de fitxers PDF.
Utilitza PyMuPDF (fitz) per extreure el contingut textual dels capítols.
"""
import fitz  # PyMuPDF
from pathlib import Path
from typing import Optional


def extract_text(pdf_path: str | Path, start_page: Optional[int] = None, end_page: Optional[int] = None) -> str:
    """
    Extreu tot el text d'un fitxer PDF.

    Args:
        pdf_path: Ruta al fitxer PDF.
        start_page: Pàgina inicial (0-indexed, opcional).
        end_page: Pàgina final (exclusiva, opcional).

    Returns:
        Text complet del PDF o del rang de pàgines especificat.
    """
    pdf_path = Path(pdf_path)

    if not pdf_path.exists():
        raise FileNotFoundError(f"No s'ha trobat el fitxer: {pdf_path}")

    doc = fitz.open(pdf_path)
    text_parts = []

    # Determinar rang de pàgines
    first_page = start_page if start_page is not None else 0
    last_page = end_page if end_page is not None else len(doc)

    for page_num in range(first_page, min(last_page, len(doc))):
        page = doc[page_num]
        text = page.get_text("text")
        if text.strip():
            text_parts.append(text)

    doc.close()

    return "\n\n".join(text_parts)


def extract_text_with_metadata(pdf_path: str | Path) -> dict:
    """
    Extreu text amb metadades del PDF.

    Args:
        pdf_path: Ruta al fitxer PDF.

    Returns:
        Diccionari amb text, metadades i informació de pàgines.
    """
    pdf_path = Path(pdf_path)

    if not pdf_path.exists():
        raise FileNotFoundError(f"No s'ha trobat el fitxer: {pdf_path}")

    doc = fitz.open(pdf_path)

    result = {
        "filename": pdf_path.name,
        "total_pages": len(doc),
        "metadata": doc.metadata,
        "pages": []
    }

    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text("text")

        result["pages"].append({
            "number": page_num + 1,
            "text": text,
            "word_count": len(text.split())
        })

    doc.close()

    # Text complet
    result["full_text"] = "\n\n".join(p["text"] for p in result["pages"])
    result["total_words"] = sum(p["word_count"] for p in result["pages"])

    return result
