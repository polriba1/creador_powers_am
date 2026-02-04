"""
Extractor d'imatges de fitxers PDF.
Utilitza PyMuPDF (fitz) per extreure les imatges dels capítols.
"""
import fitz  # PyMuPDF
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass
from PIL import Image
import io
import hashlib

from config import MIN_IMAGE_WIDTH, MIN_IMAGE_HEIGHT, IMAGES_EXTRACTED_DIR


@dataclass
class ImageInfo:
    """Informació d'una imatge extreta."""
    id: str
    path: Path
    width: int
    height: int
    page_number: int
    format: str
    size_bytes: int


def extract_images(
    pdf_path: str | Path,
    output_dir: Optional[Path] = None,
    min_width: int = MIN_IMAGE_WIDTH,
    min_height: int = MIN_IMAGE_HEIGHT
) -> List[ImageInfo]:
    """
    Extreu totes les imatges d'un PDF que superin la mida mínima.

    Args:
        pdf_path: Ruta al fitxer PDF.
        output_dir: Directori on guardar les imatges (per defecte: cache/images/extracted).
        min_width: Amplada mínima en píxels.
        min_height: Alçada mínima en píxels.

    Returns:
        Llista d'ImageInfo amb les imatges extretes.
    """
    pdf_path = Path(pdf_path)
    output_dir = output_dir or IMAGES_EXTRACTED_DIR

    if not pdf_path.exists():
        raise FileNotFoundError(f"No s'ha trobat el fitxer: {pdf_path}")

    # Crear subdirectori per aquest PDF
    pdf_name = pdf_path.stem
    images_dir = output_dir / pdf_name
    images_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(pdf_path)
    extracted_images: List[ImageInfo] = []
    seen_hashes = set()  # Per evitar duplicats

    for page_num in range(len(doc)):
        page = doc[page_num]
        image_list = page.get_images(full=True)

        for img_index, img_info in enumerate(image_list):
            xref = img_info[0]

            try:
                # Extreure imatge
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]
                image_ext = base_image["ext"]

                # Calcular hash per evitar duplicats
                img_hash = hashlib.md5(image_bytes).hexdigest()
                if img_hash in seen_hashes:
                    continue
                seen_hashes.add(img_hash)

                # Obrir amb PIL per verificar dimensions
                img = Image.open(io.BytesIO(image_bytes))
                width, height = img.size

                # Filtrar per mida mínima
                if width < min_width or height < min_height:
                    continue

                # Generar ID únic
                img_id = f"img_{page_num + 1}_{img_index + 1}_{img_hash[:8]}"

                # Guardar imatge
                img_filename = f"{img_id}.{image_ext}"
                img_path = images_dir / img_filename

                with open(img_path, "wb") as f:
                    f.write(image_bytes)

                # Afegir a la llista
                extracted_images.append(ImageInfo(
                    id=img_id,
                    path=img_path,
                    width=width,
                    height=height,
                    page_number=page_num + 1,
                    format=image_ext,
                    size_bytes=len(image_bytes)
                ))

            except Exception as e:
                print(f"Error extraient imatge {xref} de pàgina {page_num + 1}: {e}")
                continue

    doc.close()

    print(f"Extretes {len(extracted_images)} imatges de {pdf_path.name}")
    return extracted_images


def get_image_as_base64(image_path: Path) -> str:
    """
    Converteix una imatge a base64 per enviar a l'API.

    Args:
        image_path: Ruta a la imatge.

    Returns:
        String en base64.
    """
    import base64

    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")
