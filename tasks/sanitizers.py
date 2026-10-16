"""Sanitización de texto libre que escribe el usuario (notas de ejecución)."""

import re
import unicodedata

from django.utils.html import strip_tags

# Caracteres invisibles o de control de dirección que no aportan texto y sirven para engañar
# (U+200B espacio de ancho cero, marcas y overrides bidireccionales, BOM...). Se conservan
# U+200C y U+200D porque forman parte de emojis compuestos y de algunos idiomas.
_INVISIBLES = dict.fromkeys(
    [
        0x200B,
        0x200E,
        0x200F,
        *range(0x202A, 0x202F),
        *range(0x2060, 0x2065),
        *range(0x2066, 0x206A),
        0xFEFF,
    ]
)
_SALTOS_EXTRA = re.compile(r"\n{3,}")
_ESPACIOS_FINALES = re.compile(r"[ \t]+(?=\n)")


def sanitize_text(value):
    """Devuelve texto plano seguro para guardar, o None si no queda contenido.

    Normaliza a NFC, unifica saltos de línea, elimina caracteres de control (menos \\n y \\t),
    sustitutos Unicode inválidos, caracteres invisibles y etiquetas HTML; limita los saltos de
    línea seguidos a dos y recorta espacios sobrantes.
    """
    text = unicodedata.normalize("NFC", str(value))
    text = text.replace("\r\n", "\n").replace("\r", "\n").translate(_INVISIBLES)
    text = "".join(
        ch
        for ch in text
        if ch in "\n\t" or unicodedata.category(ch) not in ("Cc", "Cs")
    )
    text = strip_tags(text)
    text = _ESPACIOS_FINALES.sub("", text)
    text = _SALTOS_EXTRA.sub("\n\n", text).strip()
    return text or None
