"""
Processador de contingut amb Claude Opus 4.5.
Estructura el contingut del capítol i crea el pla de la presentació.
"""
import anthropic
from typing import List, Optional
from dataclasses import dataclass, field
import json
import time

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, TARGET_SLIDES, TARGET_DURATION_MINUTES, MAX_TOKENS, API_TIMEOUT
from database import log_usage, get_api_keys

# Configuració de retry
MAX_RETRIES = 8
INITIAL_RETRY_DELAY = 15  # segons
MAX_RETRY_DELAY = 120  # màxim segons d'espera entre intents
from processors.gemini_processor import ImageCatalogEntry, catalog_to_text


@dataclass
class SlideImage:
    """Configuració d'imatge per a una diapositiva."""
    source: str  # "catalog" o "generate"
    catalog_id: Optional[str] = None  # Si source == "catalog"
    generate_prompt: Optional[str] = None  # Si source == "generate"
    path: Optional[str] = None  # Path a la imatge (s'omple després)


@dataclass
class SlideContent:
    """Contingut d'una diapositiva."""
    number: int
    slide_type: str  # title, index, content, diagram, conclusion
    title: str
    content: List[str]  # Punts o paràgrafs
    speaker_notes: str  # Notes per l'orador (xuleta)
    image: Optional[SlideImage] = None
    duration_seconds: int = 60  # Temps estimat


@dataclass
class PresentationPlan:
    """Pla complet de la presentació."""
    chapter_name: str
    chapter_title: str
    group_name: str
    slides: List[SlideContent] = field(default_factory=list)
    key_concepts: List[str] = field(default_factory=list)
    study_summary: str = ""


def structure_presentation(
    chapter_text: str,
    image_catalog: List[ImageCatalogEntry],
    chapter_name: str,
    group_name: str = "GRUP",
    session_id: str = "default",
    api_key: str = None
) -> PresentationPlan:
    """
    Estructura el contingut del capítol en una presentació.

    Args:
        chapter_text: Text complet del capítol.
        image_catalog: Catàleg d'imatges disponibles.
        chapter_name: Nom del capítol (ex: "KWC04").
        group_name: Nom del grup (ex: "GRUPG").

    Returns:
        Pla de presentació amb totes les diapositives.
    """
    # Usar API key proporcionada o la configurada
    effective_api_key = api_key or get_api_keys().get("anthropic") or ANTHROPIC_API_KEY
    client = anthropic.Anthropic(api_key=effective_api_key)

    # Preparar catàleg d'imatges com a text
    catalog_text = catalog_to_text(image_catalog)

    # Prompt per Opus 4.5
    system_prompt = """Ets un expert en crear presentacions acadèmiques d'alta qualitat.
La teva tasca és estructurar el contingut d'un capítol d'un llibre d'administració d'empreses
en una presentació EQUILIBRADA per a una exposició de **MÀXIM 20 MINUTS**.

═══════════════════════════════════════════════════════════════════════════════
⏱️ RESTRICCIÓ TEMPORAL CRÍTICA: 20 MINUTS MÀXIM
═══════════════════════════════════════════════════════════════════════════════

LA PRESENTACIÓ HA DE CABRE EN 20 MINUTS. Això significa:
• MÀXIM 18-22 diapositives (ideal: 20)
• ~1 minut per diapositiva de mitjana
• PRIORITZA els conceptes més importants del capítol
• NO intentis cobrir-ho TOT - selecciona el més rellevant
• Millor menys slides ben explicades que moltes superficials

ESTRATÈGIA DE PRIORITZACIÓ:
1. Identifica els 5-7 conceptes CLAU del capítol
2. Dedica 2-3 slides a cada concepte important
3. Elimina contingut secundari o repetitiu
4. La portada i l'índex no compten com a contingut (30s cadascuna)
5. Reserva temps per preguntes si cal

═══════════════════════════════════════════════════════════════════════════════
QUASI TOTES LES SLIDES AMB IMATGE! - MOLT VISUAL
═══════════════════════════════════════════════════════════════════════════════

REGLA D'OR: CADA DIAPOSITIVA HA DE TENIR IMATGE (excepte l'índex)

Les imatges han d'aportar MOLT VALOR VISUAL al contingut. NO imatges genèriques!

TIPUS D'IMATGES SEGONS CONTINGUT:

1. DEFINICIONS/CONCEPTES → Diagrama conceptual
   Prompt: "Conceptual diagram showing [concept] with labeled components"
   Exemple: "Conceptual diagram showing administration as central hub connecting planning, organizing, staffing, leading and controlling"

2. PROCESSOS/CICLES → Diagrama de flux circular
   Prompt: "Circular flow diagram showing [process steps] with arrows"
   Exemple: "Circular flow diagram showing management cycle: Plan → Organize → Staff → Lead → Control → back to Plan"

3. JERARQUIES/NIVELLS → Piràmide o escala
   Prompt: "Pyramid diagram with [levels] from bottom to top"
   Exemple: "Pyramid diagram with technical skills at base, human skills middle, conceptual skills top"

4. COMPARACIONS → Diagrama de Venn o balança
   Prompt: "Venn diagram showing overlap between [A] and [B]"
   Exemple: "Venn diagram showing efficiency and effectiveness overlapping to create productivity"

5. RELACIONS → Mapa conceptual amb connexions
   Prompt: "Mind map with [central concept] connected to [related concepts]"
   Exemple: "Mind map with Manager at center connected to: Planning, Organizing, Staffing, Leading, Controlling"

6. LLISTES/FACTORS → Icones amb etiquetes
   Prompt: "Icon grid showing 4-6 [concepts] with simple icons and labels"
   Exemple: "Icon grid showing 6 management principles: Unity of command, Span of control, Division of labor..."

USA CATÀLEG si coincideix EXACTAMENT amb el contingut de la diapositiva.
GENERA si necessites una il·lustració específica del concepte.

═══════════════════════════════════════════════════════════════════════════════
FORMAT DE CONTINGUT - EXPLICATIU + ESTRUCTURAT
═══════════════════════════════════════════════════════════════════════════════

IMPORTANT: NO SIGUIS MASSA ESQUEMÀTIC! Cal donar CONTEXT i EXPLICACIÓ.

ESTRUCTURA IDEAL:
1. Frase introductòria que expliqui el concepte (1-2 línies)
2. Llista estructurada amb els punts clau
3. Frase de conclusió o connexió si cal

REGLES:
• 8-12 LÍNIES de contingut per slide
• BARREJA text explicatiu amb llistes numerades/bullets
• Les llistes soles NO són suficients - afegeix context!
• USA **negreta** per termes clau
• USA números (1. 2. 3.) per seqüències/processos
• USA guions (-) per subpunts o detalls

EXEMPLES DE SLIDES AMB EXPLICACIÓ + ESTRUCTURA:

EXEMPLE A - Definició amb context:
{
  "content": [
    "L'**administració** és el procés mitjançant el qual les persones que ocupen càrrecs directius",
    "coordinen els esforços humans i els recursos materials amb la finalitat d'assolir objectius",
    "organitzacionals de manera **eficient** i **eficaç**.",
    "",
    "**GERENTS**",
    "Els gerents desenvolupen cinc funcions gerencials:",
    "1. Planificar",
    "2. Organitzar",
    "3. Integrar personal",
    "4. Dirigir",
    "5. Controlar"
  ],
  "image": {"source": "generate", "generate_prompt": "Conceptual diagram showing administration as central hub connecting planning, organizing, staffing, leading and controlling"}
}

EXEMPLE B - Concepte amb explicació:
{
  "content": [
    "L'administració s'aplica a tot tipus d'organitzacions i a tots els nivells jeràrquics.",
    "",
    "Es centra en:",
    "1. **Productivitat**, que integra:",
    "2. **Efectivitat**",
    "3. **Eficiència**",
    "",
    "- La seva combinació dona lloc a l'**eficàcia**.",
    "",
    "Objectiu comú dels gerents: crear **valor afegit**."
  ],
  "image": {"source": "generate", "generate_prompt": "Venn diagram showing productivity combining effectiveness and efficiency"}
}

EXEMPLE C - Teoria amb principis:
{
  "content": [
    "Henri Fayol és considerat el pare de la teoria de l'administració moderna.",
    "Va identificar la necessitat de disposar de principis administratius que guiessin la gestió",
    "formulant 14 principis, definits com a flexibles i adaptables.",
    "",
    "**Autoritat i responsabilitat**",
    "- L'autoritat i la responsabilitat estan directament relacionades.",
    "- La responsabilitat és conseqüència de l'exercici de l'autoritat.",
    "",
    "**Unitat de comandament**",
    "- Cada treballador ha de rebre ordres d'un **únic superior**."
  ],
  "image": {"source": "catalog", "catalog_id": "img_fayol_principles"}
}

EXEMPLE D - Habilitats amb nivells:
{
  "content": [
    "Segons Robert L. Katz, els gerents necessiten:",
    "1. **Habilitats tècniques**",
    "2. **Habilitats humanes**",
    "3. **Habilitats conceptuals**",
    "4. **Habilitat de disseny** de solucions",
    "",
    "Importància segons el nivell:",
    "- Supervisors: predomini de les tècniques",
    "- Nivell mitjà: essencials les humanes i creix la importància de les conceptuals",
    "- Alta direcció: clau les conceptuals, de disseny i humanes"
  ],
  "image": {"source": "generate", "generate_prompt": "Pyramid diagram with 3 management levels showing different skill proportions at each level"}
}

═══════════════════════════════════════════════════════════════════════════════
FORMAT DE RESPOSTA (JSON) - EXPLICATIU + VISUAL
═══════════════════════════════════════════════════════════════════════════════
{
    "chapter_title": "Administració: Ciència, teoria i pràctica",
    "slides": [
        {
            "number": 1,
            "slide_type": "title",
            "title": "Capítol 1: Administració: Ciència, teoria i pràctica",
            "content": ["Administració d'Empreses"],
            "speaker_notes": "Benvinguts a la presentació sobre administració...",
            "image": {"source": "generate", "generate_prompt": "Modern corporate building with interconnected gears and people icons representing management and organization, orange and gray colors"},
            "duration_seconds": 30
        },
        {
            "number": 2,
            "slide_type": "index",
            "title": "Índex",
            "content": ["Què és l'administració?", "Funcions de l'administració", "L'administració com a element essencial", "Funcions gerencials segons el nivell", "Habilitats gerencials", "Adaptació als canvis del segle XXI", "Productivitat, eficàcia i eficiència", "Henri Fayol i l'administració moderna"],
            "speaker_notes": "Avui veurem vuit blocs principals...",
            "image": null,
            "duration_seconds": 30
        },
        {
            "number": 3,
            "slide_type": "content",
            "title": "1. Què és l'administració?",
            "content": [
                "L'**administració** és el procés mitjançant el qual les persones que ocupen càrrecs directius",
                "coordinen els esforços humans i els recursos materials amb la finalitat d'assolir objectius",
                "organitzacionals de manera **eficient** i **eficaç**.",
                "",
                "**GERENTS**",
                "Els gerents desenvolupen cinc funcions gerencials:",
                "1. Planificar",
                "2. Organitzar",
                "3. Integrar personal",
                "4. Dirigir",
                "5. Controlar"
            ],
            "speaker_notes": "L'administració és fonamental perquè permet coordinar els esforços de moltes persones cap a un objectiu comú...",
            "image": {"source": "generate", "generate_prompt": "Conceptual diagram showing Administration as central hub connecting 5 management functions with arrows"},
            "duration_seconds": 60
        },
        {
            "number": 4,
            "slide_type": "content",
            "title": "1. Què és l'administració?",
            "content": [
                "L'administració s'aplica a tot tipus d'organitzacions i a tots els nivells jeràrquics.",
                "",
                "Es centra en:",
                "1. **Productivitat**, que integra:",
                "2. **Efectivitat**",
                "3. **Eficiència**",
                "",
                "- La seva combinació dona lloc a l'**eficàcia**.",
                "",
                "Objectiu comú dels gerents: crear **valor afegit**."
            ],
            "speaker_notes": "És important entendre que l'administració no és exclusiva de grans empreses...",
            "image": {"source": "generate", "generate_prompt": "Venn diagram showing productivity combining effectiveness and efficiency to create efficacy"},
            "duration_seconds": 60
        },
        {
            "number": 5,
            "slide_type": "content",
            "title": "2. Funcions de l'administració",
            "content": [
                "El coneixement administratiu s'organitza en cinc funcions gerencials:",
                "1. Planificar",
                "2. Organitzar",
                "3. Integrar personal",
                "4. Dirigir",
                "5. Controlar",
                "",
                "Aquest marc facilita l'anàlisi i l'estudi de l'administració.",
                "És un model àmpliament acceptat i validat en la literatura acadèmica."
            ],
            "speaker_notes": "Les cinc funcions formen un cicle continu que tot gerent ha de dominar...",
            "image": {"source": "generate", "generate_prompt": "Circular flow diagram showing 5 management functions as connected cycle with arrows"}
        }
    ],
    "key_concepts": ["Administració", "Funcions gerencials", "Eficiència", "Eficàcia", "Productivitat"],
    "study_summary": "Resum de 2-3 paràgrafs per estudiar"
}

═══════════════════════════════════════════════════════════════════════════════
SPEAKER_NOTES - MOLT IMPORTANTS!
═══════════════════════════════════════════════════════════════════════════════
Les speaker_notes han de ser APUNTS COMPLETS que expliquin el concepte com si
el lector no sabés res del tema. NO són un guió breu, són una EXPLICACIÓ COMPLETA.

Cada speaker_notes ha d'incloure:
1. EXPLICACIÓ del concepte en paraules senzilles
2. EXEMPLES pràctics o casos reals
3. CONNEXIONS amb altres conceptes del capítol
4. Per què és IMPORTANT aquest punt

Exemple de speaker_notes CORRECTE:
"L'administració és fonamental perquè permet coordinar esforços de moltes persones
cap a un objectiu comú. Sense administració, cada treballador faria el que volgués
i no s'aconseguirien resultats. Per exemple, penseu en un equip de futbol: sense
un entrenador que planifiqui, organitzi i dirigeixi, els jugadors no sabrien
quina posició ocupar ni quina estratègia seguir. Els gerents fan exactament això
a les empreses: planifiquen què s'ha de fer, organitzen els recursos, integren
les persones adequades, dirigeixen les accions i controlen que tot surti bé."

═══════════════════════════════════════════════════════════════════════════════
REGLES FINALS - EXPLICATIU + VISUAL
═══════════════════════════════════════════════════════════════════════════════

REGLES DE CONTINGUT (MOLT IMPORTANT!):
• NO SIGUIS MASSA ESQUEMÀTIC - afegeix context i explicació!
• 8-12 LÍNIES per slide - barreja text explicatiu amb llistes
• Comença amb frase introductòria que expliqui el concepte
• Després llista estructurada amb números o bullets
• **negreta** per termes clau importants
• MAJUSCULES per subtítols dins la slide (ex: "GERENTS", "AUTORITAT")

REGLES DE VISUALITAT:
• QUASI TOTES LES SLIDES AMB IMATGE (excepte índex)
• Prompts d'imatge en ANGLÈS, específics: diagrames, piràmides, cicles...
• NO imatges genèriques - han d'il·lustrar el concepte explicat!

REGLES GENERALS:
• NOMBRE SLIDES: 18-22 diapositives (MÀXIM 20 minuts de presentació)
• NO EMOJIS - absolutament prohibits
• NO TAULES ni figures fetes amb text
• PORTADA sempre amb imatge generada atractiva
• Speaker_notes: explicacions MOLT completes per estudiar
• USA IMATGES DEL CATÀLEG si encaixen perfectament
• Respon NOMÉS amb JSON vàlid, sense text addicional"""

    user_prompt = f"""CAPÍTOL: {chapter_name}
GRUP: {group_name}

{catalog_text}

CONTINGUT DEL CAPÍTOL:
{chapter_text}

Genera el pla de presentació en format JSON."""

    # Cridar Opus 4.5 amb retry automàtic
    print("Estructurant presentació amb Opus 4.5...")
    response = None
    last_error = None

    for attempt in range(MAX_RETRIES):
        try:
            response = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=MAX_TOKENS,
                timeout=API_TIMEOUT,
                messages=[
                    {"role": "user", "content": user_prompt}
                ],
                system=system_prompt
            )
            break  # Si funciona, sortim del bucle

        except anthropic.APIStatusError as e:
            last_error = e
            if e.status_code in (529, 503, 502):  # Overloaded o servidor no disponible
                wait_time = min(INITIAL_RETRY_DELAY * (2 ** attempt), MAX_RETRY_DELAY)
                print(f"  API saturada ({e.status_code}). Reintentant en {wait_time}s... (intent {attempt + 1}/{MAX_RETRIES})")
                time.sleep(wait_time)
            elif e.status_code == 429:  # Rate limit
                wait_time = min(INITIAL_RETRY_DELAY * (2 ** attempt), MAX_RETRY_DELAY)
                print(f"  Límit de velocitat (429). Reintentant en {wait_time}s... (intent {attempt + 1}/{MAX_RETRIES})")
                time.sleep(wait_time)
            else:
                raise  # Altres errors els propaguem
        except anthropic.APIConnectionError as e:
            last_error = e
            wait_time = min(INITIAL_RETRY_DELAY * (2 ** attempt), MAX_RETRY_DELAY)
            print(f"  Error de connexió. Reintentant en {wait_time}s... (intent {attempt + 1}/{MAX_RETRIES})")
            time.sleep(wait_time)

    if response is None:
        raise Exception(
            f"No s'ha pogut connectar amb l'API després de {MAX_RETRIES} intents.\n"
            f"Últim error: {last_error}\n"
            f"Suggeriment: L'API d'Anthropic pot estar saturada. Espera uns minuts i torna-ho a provar."
        )

    # Registrar ús de tokens
    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens
    cost = log_usage(
        session_id=session_id,
        model=CLAUDE_MODEL,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        operation="structure_presentation",
        chapter_name=chapter_name
    )
    print(f"  Tokens: {input_tokens:,} input, {output_tokens:,} output | Cost: ${cost:.4f}")

    # Parsejar resposta
    response_text = response.content[0].text.strip()

    # Netejar possibles marques de codi
    if response_text.startswith("```"):
        response_text = response_text.split("```")[1]
        if response_text.startswith("json"):
            response_text = response_text[4:]
    if response_text.endswith("```"):
        response_text = response_text[:-3]
    response_text = response_text.strip()

    data = json.loads(response_text)

    # Construir PresentationPlan
    plan = PresentationPlan(
        chapter_name=chapter_name,
        chapter_title=data.get("chapter_title", chapter_name),
        group_name=group_name,
        key_concepts=data.get("key_concepts", []),
        study_summary=data.get("study_summary", "")
    )

    # Processar slides
    for slide_data in data.get("slides", []):
        image = None
        if slide_data.get("image"):
            img_data = slide_data["image"]
            image = SlideImage(
                source=img_data.get("source", "generate"),
                catalog_id=img_data.get("catalog_id"),
                generate_prompt=img_data.get("generate_prompt")
            )

        plan.slides.append(SlideContent(
            number=slide_data.get("number", 0),
            slide_type=slide_data.get("slide_type", "content"),
            title=slide_data.get("title", ""),
            content=slide_data.get("content", []),
            speaker_notes=slide_data.get("speaker_notes", ""),
            image=image,
            duration_seconds=slide_data.get("duration_seconds", 60)
        ))

    print(f"Pla creat: {len(plan.slides)} diapositives, {len(plan.key_concepts)} conceptes clau")
    return plan
