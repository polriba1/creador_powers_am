#!/usr/bin/env python3
"""
MENAG Presentation Generator
============================
Genera presentacions PowerPoint i xuletes d'estudi automàticament
a partir de capítols del llibre Koontz.

Ús:
    python main.py <pdf_path> <chapter_name> <group_name>

Exemple:
    python main.py input/capitol4.pdf KWC04 GRUPG
"""
import sys
import argparse
from pathlib import Path
from datetime import datetime

# Afegir directori arrel al path
sys.path.insert(0, str(Path(__file__).parent))

from config import validate_config, OUTPUT_DIR
from extractors import extract_text, extract_images
from processors import describe_images, structure_presentation, generate_missing_images
from generators import create_presentation, create_study_guide


def main():
    """Punt d'entrada principal."""
    parser = argparse.ArgumentParser(
        description="Genera presentacions MENAG automàticament",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples:
  python main.py input/capitol4.pdf KWC04 GRUPG
  python main.py "input/cap 5.pdf" KWC05 GRUPG --no-images
        """
    )
    parser.add_argument("pdf_path", help="Ruta al PDF del capítol")
    parser.add_argument("chapter_name", help="Nom del capítol (ex: KWC04)")
    parser.add_argument("group_name", help="Nom del grup (ex: GRUPG)")
    parser.add_argument("--no-images", action="store_true",
                        help="No generar imatges noves (només usar les del PDF)")
    parser.add_argument("--skip-image-extraction", action="store_true",
                        help="Saltar extracció d'imatges del PDF")

    args = parser.parse_args()

    # Validar configuració
    print("=" * 60)
    print("MENAG PRESENTATION GENERATOR")
    print("=" * 60)
    print()

    try:
        validate_config()
        print("✓ Configuració validada")
    except ValueError as e:
        print(f"✗ Error de configuració:\n{e}")
        print("\nAssegura't de crear el fitxer .env amb les API keys.")
        print("Pots copiar .env.example com a plantilla.")
        sys.exit(1)

    pdf_path = Path(args.pdf_path)
    if not pdf_path.exists():
        print(f"✗ No s'ha trobat el fitxer: {pdf_path}")
        sys.exit(1)

    print(f"✓ PDF trobat: {pdf_path.name}")
    print()

    # 1. Extreure text
    print("1. Extraient text del PDF...")
    chapter_text = extract_text(pdf_path)
    word_count = len(chapter_text.split())
    print(f"   Extret: {word_count} paraules")
    print()

    # 2. Extreure imatges
    image_catalog = []
    if not args.skip_image_extraction:
        print("2. Extraient imatges del PDF...")
        images = extract_images(pdf_path)
        print(f"   Extretes: {len(images)} imatges")

        if images:
            print()
            print("3. Descrivint imatges amb Gemini Flash...")
            image_catalog = describe_images(images)
            print(f"   Descrites: {len(image_catalog)} imatges")
    else:
        print("2. Salt d'extracció d'imatges (--skip-image-extraction)")
        print("3. Salt descripció d'imatges")

    print()

    # 4. Estructurar amb Opus 4.5
    print("4. Estructurant presentació amb Claude Opus 4.5...")
    plan = structure_presentation(
        chapter_text,
        image_catalog,
        args.chapter_name,
        args.group_name
    )
    print(f"   Generades: {len(plan.slides)} diapositives")
    print()

    # 5. Generar imatges (si cal)
    if not args.no_images:
        print("5. Generant imatges amb Nano Banana...")
        plan = generate_missing_images(plan, image_catalog)
    else:
        print("5. Salt generació d'imatges (--no-images)")

    print()

    # 6. Crear PPT i DOCX
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    output_base = OUTPUT_DIR / f"{args.chapter_name}_{args.group_name}_{timestamp}"

    print("6. Generant fitxers finals...")
    pptx_path = create_presentation(plan, f"{output_base}.pptx")
    # docx_path = create_study_guide(plan, f"{output_base}_xuleta.docx")  # DESACTIVAT

    print()
    print("=" * 60)
    print("COMPLETAT!")
    print("=" * 60)
    print()
    print(f"Fitxers generats:")
    print(f"  PowerPoint: {pptx_path}")
    print()
    print("Bona sort amb la presentació!")


if __name__ == "__main__":
    main()
