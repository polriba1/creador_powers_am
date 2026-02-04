"""
Generador d'imatges amb Imagen 3 via Google AI Studio.
Genera imatges noves per a les diapositives que ho necessitin.
"""
from google import genai
from google.genai import types
from pathlib import Path
from typing import List
import time
import uuid
import base64

from config import GOOGLE_API_KEY, GEMINI_IMAGE_MODEL, IMAGES_GENERATED_DIR
from processors.content_processor import PresentationPlan, SlideImage
from processors.gemini_processor import ImageCatalogEntry
from database import log_usage, get_api_keys

# Configuració de retry per generació d'imatges
MAX_IMAGE_RETRIES = 3
IMAGE_RETRY_DELAY = 5  # segons


def generate_missing_images(
    plan: PresentationPlan,
    image_catalog: List[ImageCatalogEntry],
    output_dir: Path = IMAGES_GENERATED_DIR,
    session_id: str = "default",
    api_key: str = None
) -> PresentationPlan:
    """
    Genera les imatges que falten per a la presentació.

    Args:
        plan: Pla de presentació amb slides.
        image_catalog: Catàleg d'imatges existents.
        output_dir: Directori on guardar les imatges generades.
        session_id: ID de sessió per tracking.
        api_key: API key opcional.

    Returns:
        Pla actualitzat amb els paths de les imatges.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Configurar client Google AI Studio (nova API gen-ai)
    effective_api_key = api_key or get_api_keys().get("google") or GOOGLE_API_KEY
    client = genai.Client(api_key=effective_api_key)

    images_generated_count = 0

    # Crear diccionari del catàleg per accés ràpid
    catalog_dict = {entry.id: entry for entry in image_catalog}

    images_to_generate = []
    catalog_images = []

    # Classificar imatges
    for slide in plan.slides:
        if slide.image is None:
            continue

        if slide.image.source == "catalog":
            if slide.image.catalog_id and slide.image.catalog_id in catalog_dict:
                slide.image.path = str(catalog_dict[slide.image.catalog_id].path)
                catalog_images.append(slide.number)
            else:
                # ID no trobat, convertir a generació
                slide.image.source = "generate"
                slide.image.generate_prompt = f"Professional flat design business illustration for presentation slide about {slide.title}, orange and gray corporate colors"
                images_to_generate.append(slide)
        elif slide.image.source == "generate":
            images_to_generate.append(slide)

    print(f"  Imatges del catàleg: {len(catalog_images)}")
    print(f"  Imatges a generar: {len(images_to_generate)}")

    # Generar imatges noves amb Gemini 3 Pro Image Preview (Nano Banana)
    for slide in images_to_generate:
        if not slide.image or not slide.image.generate_prompt:
            continue

        try:
            print(f"  Generant imatge per slide {slide.number}: {slide.title[:40]}...")

            # Millorar el prompt amb estil consistent
            enhanced_prompt = enhance_image_prompt(slide.image.generate_prompt)

            # Generar imatge amb Gemini 3 Pro Image Preview via Google AI Studio
            image_generated = False
            last_error = None

            for attempt in range(MAX_IMAGE_RETRIES):
                try:
                    # Usar generate_content per models Gemini amb capacitat d'imatge
                    response = client.models.generate_content(
                        model=GEMINI_IMAGE_MODEL,
                        contents=f"Generate an image: {enhanced_prompt}",
                        config=types.GenerateContentConfig(
                            response_modalities=["IMAGE"],
                            temperature=0.7,
                        )
                    )

                    # Extreure imatge de la resposta
                    if response.candidates and len(response.candidates) > 0:
                        candidate = response.candidates[0]
                        if candidate.content and candidate.content.parts:
                            for part in candidate.content.parts:
                                if hasattr(part, 'inline_data') and part.inline_data:
                                    # Guardar imatge
                                    img_id = f"gen_{slide.number}_{uuid.uuid4().hex[:8]}"
                                    img_path = output_dir / f"{img_id}.png"

                                    # Extreure bytes de la imatge
                                    image_bytes = part.inline_data.data
                                    if isinstance(image_bytes, str):
                                        image_bytes = base64.b64decode(image_bytes)

                                    with open(img_path, "wb") as f:
                                        f.write(image_bytes)

                                    slide.image.path = str(img_path)
                                    print(f"    ✓ Guardada: {img_path.name}")
                                    image_generated = True
                                    images_generated_count += 1
                                    break

                    if image_generated:
                        break
                    else:
                        last_error = "No s'ha trobat imatge a la resposta"

                except Exception as e:
                    last_error = str(e)
                    if attempt < MAX_IMAGE_RETRIES - 1:
                        print(f"    Reintentant... ({attempt + 1}/{MAX_IMAGE_RETRIES})")
                        time.sleep(IMAGE_RETRY_DELAY)

            if not image_generated:
                print(f"    ✗ Error: {last_error}")

            # Delay entre generacions per evitar rate limits
            time.sleep(1.5)

        except Exception as e:
            print(f"    ✗ Error generant imatge per slide {slide.number}: {str(e)}")

    # Registrar ús de generació d'imatges
    if images_generated_count > 0:
        cost = log_usage(
            session_id=session_id,
            model=GEMINI_IMAGE_MODEL,
            images_generated=images_generated_count,
            operation="image_generation",
            chapter_name=plan.chapter_name
        )
        print(f"  Imatges generades: {images_generated_count} | Cost: ${cost:.4f}")

    return plan


def enhance_image_prompt(base_prompt: str) -> str:
    """
    Millora el prompt per obtenir imatges consistents amb l'estil.

    Args:
        base_prompt: Prompt base de l'usuari/Opus.

    Returns:
        Prompt millorat amb estil consistent.
    """
    # Estil corporatiu consistent per a totes les imatges
    style_prefix = "Professional business presentation illustration, modern flat design style, "
    style_suffix = (
        ". Corporate color palette: warm orange (#E07A2F) as primary color, "
        "complementary yellow (#F5A623), neutral gray (#4A4A4A), white background. "
        "Clean vector art style, no gradients, minimal shadows, geometric shapes. "
        "High quality, suitable for PowerPoint presentation. "
        "NO text, NO words, NO letters in the image. "
        "16:9 aspect ratio, centered composition."
    )

    return f"{style_prefix}{base_prompt}{style_suffix}"


def get_placeholder_for_failed_generation(slide_title: str) -> str:
    """
    Retorna un missatge per quan la generació d'imatge falla.

    Args:
        slide_title: Títol de la diapositiva.

    Returns:
        Missatge placeholder.
    """
    return f"[Imatge no generada per: {slide_title}]"
