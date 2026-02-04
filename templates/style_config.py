"""
Configuració d'estils per a les presentacions PowerPoint.
Basat en l'estil de les presentacions MENAG del màster.
"""
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR


# Funció helper per compatibilitat
def RgbColor(r, g, b):
    """Crea un color RGB compatible amb python-pptx."""
    return RGBColor(r, g, b)


class StyleConfig:
    """Configuració d'estils per al PowerPoint."""

    # Colors principals (RGB)
    ORANGE_PRIMARY = RgbColor(224, 122, 47)      # #E07A2F - Títols
    ORANGE_DARK = RgbColor(180, 90, 30)          # #B45A1E - Accent fosc
    BROWN = RgbColor(139, 90, 43)                # #8B5A2B - Franja inferior
    GRAY_DARK = RgbColor(64, 64, 64)             # #404040 - Text principal
    GRAY_LIGHT = RgbColor(128, 128, 128)         # #808080 - Text secundari
    WHITE = RgbColor(255, 255, 255)              # #FFFFFF - Fons
    BLACK = RgbColor(0, 0, 0)                    # #000000 - Text èmfasi

    # Colors per a llistes numerades
    LIST_NUMBER_COLOR = ORANGE_PRIMARY

    # Fonts
    FONT_TITLE = "Calibri Light"
    FONT_BODY = "Calibri"
    FONT_FALLBACK = "Arial"

    # Mides de font (en punts)
    FONT_SIZE_TITLE_SLIDE = Pt(44)
    FONT_SIZE_SECTION_TITLE = Pt(40)
    FONT_SIZE_SLIDE_TITLE = Pt(36)
    FONT_SIZE_SUBTITLE = Pt(24)
    FONT_SIZE_BODY = Pt(18)
    FONT_SIZE_SMALL = Pt(14)
    FONT_SIZE_FOOTER = Pt(10)

    # Dimensions de la diapositiva (16:9)
    SLIDE_WIDTH = Inches(13.333)
    SLIDE_HEIGHT = Inches(7.5)

    # Marges
    MARGIN_LEFT = Inches(0.5)
    MARGIN_RIGHT = Inches(0.5)
    MARGIN_TOP = Inches(0.5)
    MARGIN_BOTTOM = Inches(1.0)  # Espai per la franja

    # Franja inferior
    BOTTOM_STRIPE_HEIGHT = Inches(0.4)
    BOTTOM_STRIPE_Y = SLIDE_HEIGHT - Inches(0.4)

    # Línia separadora (sota títols)
    SEPARATOR_LINE_WIDTH = Pt(2)
    SEPARATOR_LINE_COLOR = BROWN

    # Posicions estàndard
    TITLE_TOP = Inches(0.4)
    TITLE_HEIGHT = Inches(1.0)
    CONTENT_TOP = Inches(1.6)
    CONTENT_HEIGHT = Inches(5.0)

    # Configuració d'imatges
    IMAGE_MAX_WIDTH = Inches(5.5)
    IMAGE_MAX_HEIGHT = Inches(4.0)

    @classmethod
    def get_title_style(cls):
        """Retorna configuració per a títols."""
        return {
            'font_name': cls.FONT_TITLE,
            'font_size': cls.FONT_SIZE_SLIDE_TITLE,
            'font_color': cls.ORANGE_PRIMARY,
            'bold': False,
            'alignment': PP_ALIGN.LEFT
        }

    @classmethod
    def get_body_style(cls):
        """Retorna configuració per a text del cos."""
        return {
            'font_name': cls.FONT_BODY,
            'font_size': cls.FONT_SIZE_BODY,
            'font_color': cls.GRAY_DARK,
            'bold': False,
            'alignment': PP_ALIGN.LEFT
        }

    @classmethod
    def get_index_style(cls):
        """Retorna configuració per a l'índex."""
        return {
            'font_name': cls.FONT_BODY,
            'font_size': cls.FONT_SIZE_BODY,
            'font_color': cls.GRAY_DARK,
            'number_color': cls.ORANGE_PRIMARY,
            'bold': False,
            'alignment': PP_ALIGN.LEFT
        }
