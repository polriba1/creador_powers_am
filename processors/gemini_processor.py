"""
Processador d'imatges amb Gemini Flash.
Descriu i etiqueta les imatges extretes del PDF.
"""
import google.generativeai as genai
from pathlib import Path
from typing import List
from dataclasses import dataclass
import json
import time
import base64

from config import GOOGLE_API_KEY, GEMINI_ANALYSIS_MODEL
from extractors.image_extractor import ImageInfo
from database import log_usage, get_api_keys


@dataclass
class ImageCatalogEntry:
    """Entrada del catàleg d'imatges amb descripció."""
    id: str
    path: Path
    width: int
    height: int
    page_number: int
    description: str
    topic: str
    image_type: str  # diagram, chart, photo, illustration
    keywords: List[str]
    relevance_score: float  # 0-1, utilitat per a presentació


def describe_images(
    images: List[ImageInfo],
    session_id: str = "default",
    api_key: str = None
) -> List[ImageCatalogEntry]:
    """
    Descriu i etiqueta cada imatge utilitzant Gemini Flash.

    Args:
        images: Llista d'imatges extretes del PDF.
        session_id: ID de sessió per tracking.
        api_key: API key opcional (usa la configurada si no es proporciona).

    Returns:
        Catàleg d'imatges amb descripcions i metadades.
    """
    if not images:
        return []

    # Configurar Google AI Studio amb API key
    effective_api_key = api_key or get_api_keys().get("google") or GOOGLE_API_KEY
    genai.configure(api_key=effective_api_key)

    total_input_tokens = 0
    total_output_tokens = 0

    # Crear model per anàlisi d'imatges
    model = genai.GenerativeModel(model_name=GEMINI_ANALYSIS_MODEL)

    catalog: List[ImageCatalogEntry] = []

    for img in images:
        try:
            # Llegir imatge com a bytes
            with open(img.path, "rb") as f:
                image_bytes = f.read()

            # Determinar mime type
            ext = img.format.lower()
            mime_map = {
                'png': 'image/png',
                'jpg': 'image/jpeg',
                'jpeg': 'image/jpeg',
                'gif': 'image/gif',
                'webp': 'image/webp'
            }
            mime_type = mime_map.get(ext, 'image/png')

            # Prompt per descriure la imatge
            prompt = """Analitza aquesta imatge d'un llibre d'administració d'empreses amb MÀXIMA PRECISIÓ i DETALL.

Respon en format JSON amb els següents camps:

{
    "description": "DESCRIPCIÓ ULTRA-DETALLADA en català com si l'explicessis a una persona COMPLETAMENT CEGA. Inclou: TOTS els elements visuals visibles, colors exactes (tons, intensitats), formes geomètriques, text llegible (cita'l exactament), diagrames (descriu cada component, fletxes, connexions), gràfics (tipus, dades, eixos), taules (capçaleres, contingut), persones/objectes (posició, mida, relacions), estil artístic, composició, jerarquia visual. MINIM 8-10 frases completes i especifiques. No siguis vague - sigues concret i exhaustiu.",
    "topic": "Tema principal específic (ex: 'matriu BCG amb quadrants de creixement', 'diagrama de flux del procés de planificació estratègica', 'gràfic de barres comparatiu d'estratègies'...)",
    "image_type": "Tipus d'imatge específic: flowchart | bar_chart | pie_chart | matrix | timeline | organizational_chart | concept_map | table | illustration | photograph | screenshot",
    "keywords": ["paraula_clau_1", "paraula_clau_2", "paraula_clau_3", "paraula_clau_4", "paraula_clau_5"],
    "relevance_score": 0.8
}

IMPORTANT: La descripció ha de ser TAN DETALLADA que Claude Opus pugui decidir amb precisió si aquesta imatge encaixa perfectament amb un contingut específic de presentació. Inclou dimensions relatives, posicions, colors RGB si és possible, text exacte, números, i qualsevol detall visual rellevant."""

            # Crear contingut amb imatge
            response = model.generate_content([prompt, {"mime_type": mime_type, "data": image_bytes}])

            # Registrar tokens (si disponible)
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                total_input_tokens += getattr(response.usage_metadata, 'prompt_token_count', 0)
                total_output_tokens += getattr(response.usage_metadata, 'candidates_token_count', 0)

            # Parsejar resposta JSON
            response_text = response.text.strip()
            # Netejar possibles marques de codi
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            response_text = response_text.strip()

            data = json.loads(response_text)

            catalog.append(ImageCatalogEntry(
                id=img.id,
                path=img.path,
                width=img.width,
                height=img.height,
                page_number=img.page_number,
                description=data.get("description", "Sense descripció"),
                topic=data.get("topic", "General"),
                image_type=data.get("image_type", "illustration"),
                keywords=data.get("keywords", []),
                relevance_score=float(data.get("relevance_score", 0.5))
            ))

            print(f"  Processada: {img.id} - {data.get('topic', 'N/A')}")

            # Petit delay per evitar rate limits
            time.sleep(0.5)

        except Exception as e:
            print(f"  Error processant {img.id}: {e}")
            # Afegir amb descripció per defecte
            catalog.append(ImageCatalogEntry(
                id=img.id,
                path=img.path,
                width=img.width,
                height=img.height,
                page_number=img.page_number,
                description="Imatge del capítol",
                topic="General",
                image_type="illustration",
                keywords=[],
                relevance_score=0.5
            ))

    # Registrar ús total
    if total_input_tokens > 0 or total_output_tokens > 0:
        cost = log_usage(
            session_id=session_id,
            model=GEMINI_ANALYSIS_MODEL,
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
            operation="image_analysis",
            chapter_name=f"{len(images)} images"
        )
        print(f"  Tokens anàlisi: {total_input_tokens:,} input, {total_output_tokens:,} output | Cost: ${cost:.4f}")

    print(f"Catàleg creat amb {len(catalog)} imatges descrites")
    return catalog


def catalog_to_text(catalog: List[ImageCatalogEntry]) -> str:
    """
    Converteix el catàleg d'imatges a text per enviar a Opus.

    Args:
        catalog: Catàleg d'imatges.

    Returns:
        Text formatat amb la informació de les imatges.
    """
    if not catalog:
        return """═══════════════════════════════════════════════════════════════
CATÀLEG D'IMATGES DEL LLIBRE: BUIT
═══════════════════════════════════════════════════════════════
No s'han trobat imatges al PDF. Hauràs de generar totes les imatges.
Usa "source": "generate" per a totes les diapositives que necessitin imatge."""

    lines = [
        "═══════════════════════════════════════════════════════════════",
        f"CATÀLEG D'IMATGES DEL LLIBRE ({len(catalog)} imatges disponibles)",
        "═══════════════════════════════════════════════════════════════",
        "",
        "PRIORITAT: Usa imatges del catàleg si encaixen PERFECTAMENT.",
        "Els esquemes i diagrames del llibre són valuosos per coherència acadèmica.",
        "",
        "─────────────────────────────────────────────────────────────────"
    ]

    for i, entry in enumerate(catalog, 1):
        quality_indicator = "★★★" if entry.relevance_score >= 0.8 else "★★" if entry.relevance_score >= 0.6 else "★"
        lines.append(f"")
        lines.append(f"[IMATGE {i}] ID: {entry.id}  {quality_indicator} ({entry.relevance_score:.1f}/1.0)")
        lines.append(f"├── Pàgina PDF: {entry.page_number}")
        lines.append(f"├── Tipus: {entry.image_type}")
        lines.append(f"├── Tema específic: {entry.topic}")
        lines.append(f"├── Keywords: {', '.join(entry.keywords)}")
        lines.append(f"└── DESCRIPCIÓ VISUAL COMPLETA:")
        # Dividir descripció en línies per millor llegibilitat
        desc_lines = entry.description.split('. ')
        for desc_line in desc_lines:
            if desc_line.strip():
                lines.append(f"    {desc_line.strip()}.")
        lines.append(f"─────────────────────────────────────────────────────────────────")

    lines.append("")
    lines.append("RECORDATORI: Només usa 'catalog' si la imatge encaixa EXACTAMENT amb el contingut de la diapositiva.")
    lines.append("Si no hi ha cap imatge adequada, genera una nova amb 'generate'.")
    lines.append("")

    return "\n".join(lines)
