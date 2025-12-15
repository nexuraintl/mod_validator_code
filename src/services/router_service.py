from pathlib import Path

PROMPT_DIR = Path(__file__).resolve().parents[1] / "prompt"

PLANTILLA_PATH = PROMPT_DIR / "plantilla.txt"

# Cargar plantilla
PLANTILLA = PLANTILLA_PATH.read_text(encoding="utf-8")


def build_prompt(texto: str, categoria: str = "") -> str:
    return PLANTILLA.format(
        texto=texto.strip(),
        categoria=categoria or ""
    )
