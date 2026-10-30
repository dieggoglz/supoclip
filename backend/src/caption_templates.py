"""
Caption template definitions for animated subtitles.
Each template defines styling and animation properties for different caption styles.

Newer styling fields (all optional, read with .get() in the renderer so older
templates keep working):
  - word_pop:           scale the active karaoke word up with a spring (bool)
  - emoji:              inject contextual emojis next to keywords (bool)
  - emphasis_color:     colour for emphasised power/keyword words (hex or None)
  - word_box:           draw a filled "pill" behind the active word (bool)
  - word_box_color:     colour of that pill (hex, supports 8-digit alpha)
  - uppercase:          force caption text to uppercase (bool)
  - max_words_per_line: words shown per caption line (int)
  - glow:               soft neon glow on the text outline (bool)
"""

from typing import Dict, Any, Literal

AnimationType = Literal["none", "karaoke", "pop", "fade", "bounce", "glow"]

# Advance of each capital in Nunito Black, as a share of the font size (read from the font file).
NUNITO_BLACK_WIDTHS: Dict[str, float] = {
    'A': 0.763, 'B': 0.702, 'C': 0.688, 'D': 0.786, 'E': 0.614, 'F': 0.579, 'G': 0.747, 'H': 0.786, 'I': 0.312,
    'J': 0.39, 'K': 0.712, 'L': 0.585, 'M': 0.884, 'N': 0.758, 'O': 0.807, 'P': 0.676, 'Q': 0.807, 'R': 0.706,
    'S': 0.651, 'T': 0.644, 'U': 0.748, 'V': 0.742, 'W': 1.128, 'X': 0.698, 'Y': 0.645, 'Z': 0.625, '0': 0.6,
    '1': 0.6, '2': 0.6, '3': 0.6, '4': 0.6, '5': 0.6, '6': 0.6, '7': 0.6, '8': 0.6, '9': 0.6,
    ' ': 0.286, '.': 0.272, ',': 0.272, '?': 0.478, '!': 0.272, "'": 0.269, '"': 0.515, '-': 0.445, ':': 0.272,
    ';': 0.272, '$': 0.6, '%': 0.964, '&': 0.766, '—': 1.0, '’': 0.272, '“': 0.502, '”': 0.502,
}

CAPTION_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "default": {
        "name": "Default",
        "description": "Punchy word-by-word captions with a pop highlight and emojis",
        "font_family": "THEBOLDFONT",
        "font_size": 32,
        "font_color": "#FFFFFF",
        "highlight_color": "#FFE000",  # Bright yellow for the active word
        "emphasis_color": "#FFE000",  # Power/keyword words pop in the same accent
        "stroke_color": "#000000",
        "stroke_width": 3,
        "background": False,
        "background_color": None,
        "word_box": False,
        "word_box_color": None,
        "animation": "karaoke",
        "word_pop": True,
        "emoji": True,
        "uppercase": False,
        "shadow": True,
        "glow": False,
        "max_words_per_line": 4,
        "position_y": 0.80,
    },
    "hormozi": {
        "name": "Hormozi",
        "description": "Bold green highlight with a pill behind the active word",
        "font_family": "THEBOLDFONT",
        "font_size": 32,
        "font_color": "#FFFFFF",
        "highlight_color": "#00FF66",  # Bright green
        "emphasis_color": "#FFE000",
        "stroke_color": "#000000",
        "stroke_width": 4,
        "background": False,
        "background_color": None,
        "word_box": True,
        "word_box_color": "#00BF49",  # Green pill behind active word
        "animation": "karaoke",
        "word_pop": True,
        "emoji": True,
        "uppercase": True,
        "shadow": True,
        "glow": False,
        "max_words_per_line": 3,
        "position_y": 0.74,
    },
    "mrbeast": {
        "name": "MrBeast",
        "description": "Large yellow text with red pop highlights and emojis",
        "font_family": "THEBOLDFONT",
        "font_size": 34,
        "font_color": "#FFFF00",  # Yellow
        "highlight_color": "#FF2D2D",  # Red
        "emphasis_color": "#FFFFFF",
        "stroke_color": "#000000",
        "stroke_width": 5,
        "background": False,
        "background_color": None,
        "word_box": False,
        "word_box_color": None,
        "animation": "karaoke",
        "word_pop": True,
        "emoji": True,
        "uppercase": True,
        "shadow": True,
        "glow": False,
        "max_words_per_line": 3,
        "position_y": 0.70,
    },
    "minimal": {
        "name": "Minimal",
        "description": "Clean, subtle captions with a soft background",
        "font_family": "TikTokSans-Regular",
        "font_size": 26,
        "font_color": "#FFFFFF",
        "highlight_color": "#FFFFFF",
        "emphasis_color": None,
        "stroke_color": None,
        "stroke_width": 0,
        "background": True,
        "background_color": "#00000080",  # 50% transparent black
        "word_box": False,
        "word_box_color": None,
        "animation": "fade",
        "word_pop": False,
        "emoji": False,
        "uppercase": False,
        "shadow": False,
        "glow": False,
        "max_words_per_line": 6,
        "position_y": 0.82,
    },
    "tiktok": {
        "name": "TikTok",
        "description": "TikTok-style with pink pop highlights",
        "font_family": "TikTokSans-Bold",
        "font_size": 28,
        "font_color": "#FFFFFF",
        "highlight_color": "#FE2C55",  # TikTok pink
        "emphasis_color": "#FE2C55",
        "stroke_color": "#000000",
        "stroke_width": 3,
        "background": False,
        "background_color": None,
        "word_box": False,
        "word_box_color": None,
        "animation": "karaoke",
        "word_pop": True,
        "emoji": True,
        "uppercase": False,
        "shadow": True,
        "glow": False,
        "max_words_per_line": 4,
        "position_y": 0.78,
    },
    "neon": {
        "name": "Neon",
        "description": "Glowing neon text with magenta highlights",
        "font_family": "THEBOLDFONT",
        "font_size": 30,
        "font_color": "#00FFFF",  # Cyan
        "highlight_color": "#FF00FF",  # Magenta
        "emphasis_color": "#FF00FF",
        "stroke_color": "#002A6B",  # Dark blue
        "stroke_width": 2,
        "background": False,
        "background_color": None,
        "word_box": False,
        "word_box_color": None,
        "animation": "karaoke",
        "word_pop": True,
        "emoji": False,
        "uppercase": False,
        "shadow": False,
        "glow": True,
        "max_words_per_line": 4,
        "position_y": 0.76,
    },
    "podcast": {
        "name": "Podcast",
        "description": "Professional podcast-style captions",
        "font_family": "TikTokSans-Regular",
        "font_size": 28,
        "font_color": "#FFFFFF",
        "highlight_color": "#FFB800",  # Warm gold
        "emphasis_color": "#FFB800",
        "stroke_color": "#1A1A1A",
        "stroke_width": 2,
        "background": True,
        "background_color": "#1A1A1ACC",  # Dark semi-transparent
        "word_box": False,
        "word_box_color": None,
        "animation": "karaoke",
        "word_pop": False,
        "emoji": False,
        "uppercase": False,
        "shadow": False,
        "glow": False,
        "max_words_per_line": 5,
        "position_y": 0.80,
    },
    # The look most podcast clippers post (seen on BILF Podcast clips, 29 Oct 2026):
    # two big bold words at a time, white with a heavy outline, power words and
    # numbers in red, no emojis, the whole line popping in once.
    "clipper": {
        "name": "Clipper",
        "description": "Two big bold words at a time, white with red emphasis",
        "font_family": "THEBOLDFONT",
        "font_size": 38,
        "font_color": "#FFFFFF",
        "highlight_color": "#FF2D2D",
        "emphasis_color": "#FF2D2D",
        "stroke_color": "#000000",
        "stroke_width": 5,
        "background": False,
        "background_color": None,
        "word_box": False,
        "word_box_color": None,
        "animation": "pop",
        "word_pop": True,
        "emoji": False,
        "uppercase": True,
        "shadow": True,
        "glow": False,
        "max_words_per_line": 2,
        "position_y": 0.72,
    },
    # The look of most podcast clip channels (reference Shorts from Diego, 29 Oct
    # 2026): Montserrat ExtraBold capitals, white with a soft dark halo (no hard
    # outline), one neon word per line with a glow of its colour, lines blurring
    # in and out, mid-frame. One palette colour per clip.
    "glow": {
        "name": "Glow",
        "description": "Bold white captions with a soft halo and one neon glowing word per line",
        "font_family": "Nunito-Black",     # rounded, as in the reference Short (Diego, 30 Oct)
        "font_size": 48,
        "font_color": "#FFFFFF",
        "highlight_color": "#39FF14",
        "emphasis_color": "#39FF14",
        # No cyan: Diego, 29 Oct, hard to read. Red and orange from the reference Short
        "emphasis_palette": ["#39FF14", "#FF3FD2", "#FFE600", "#FF4D4D", "#FF9F1C"],
        # Reference Shorts (Diego, 30 Oct): a new colour every line, lines cut by phrase
        # (1-4 words), a cross-fade with a soft blur between lines and a hard shadow
        "color_per_line": True,
        "phrase_chunks": True,
        "line_blur_px": 7,
        "gradient_word": True,             # the coloured word fades from strong at the top to pale below
        "text_weight_px": 2,               # heavier letters
        "line_motion": True,
        "caption_char_width": 0.62,        # for a character missing from the table
        "caption_char_widths": NUNITO_BLACK_WIDTHS,
        "stroke_color": None,
        "stroke_width": 0,
        "background": False,
        "background_color": None,
        "word_box": False,
        "word_box_color": None,
        "animation": "glow",
        "word_pop": False,
        "emoji": False,
        "uppercase": True,
        "shadow": False,
        "glow": False,
        "max_words_per_line": 4,
        "position_y": 0.56,
        # A louder headline (Diego, 29 Oct): 7 s on screen, bigger, on a dark box,
        # below the TikTok feed tabs
        "hook_title_seconds": 7.0,
        "hook_title_max_px": 104,
        "hook_title_box": "#000000D9",
        "hook_title_top": 0.10,
    },
}


# Defaults for any styling key a template might omit, so the renderer can rely
# on get_template(...).get(key, ...) without scattering fallbacks everywhere.
TEMPLATE_DEFAULTS: Dict[str, Any] = {
    "highlight_color": "#FFE000",
    "emphasis_color": None,
    "stroke_color": "#000000",
    "stroke_width": 3,
    "background": False,
    "background_color": None,
    "word_box": False,
    "word_box_color": None,
    "animation": "karaoke",
    "word_pop": True,
    "emoji": True,
    "uppercase": False,
    "shadow": True,
    "glow": False,
    "max_words_per_line": 4,
    "position_y": 0.80,
}


def get_template(template_name: str) -> Dict[str, Any]:
    """Get a caption template by name, returns default if not found."""
    template = CAPTION_TEMPLATES.get(template_name, CAPTION_TEMPLATES["default"])
    merged = dict(TEMPLATE_DEFAULTS)
    merged.update(template)
    return merged


def get_all_templates() -> Dict[str, Dict[str, Any]]:
    """Get all available caption templates."""
    return CAPTION_TEMPLATES


def get_template_names() -> list:
    """Get list of all template names."""
    return list(CAPTION_TEMPLATES.keys())


def get_template_info() -> list:
    """Get list of template info for API response."""
    return [
        {
            "id": name,
            "name": template["name"],
            "description": template["description"],
            "animation": template["animation"],
            "font_family": template["font_family"],
            "font_size": template["font_size"],
            "font_color": template["font_color"],
            "highlight_color": template["highlight_color"],
        }
        for name, template in CAPTION_TEMPLATES.items()
    ]
