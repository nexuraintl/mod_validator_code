# src/utils/json_tools.py
import json
import re
import logging
from typing import Any, Dict, Optional, Union

# Regex para eliminar fences de Markdown
MD_FENCE = re.compile(r"```(?:json)?", flags=re.IGNORECASE)

# Regex para eliminar comentarios /* */
BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)

# Regex comunes de reparación
RE_TRAILING_COMMA = re.compile(r",\s*([}\]])")
RE_KEY_NO_QUOTES = re.compile(r'(\n\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:')


def strip_md_fences(text: str) -> str:
    """Elimina fences como ```json ... ``` sin destruir contenido."""
    return MD_FENCE.sub("", text)


def remove_json_comments_preserve_strings(text: str) -> str:
    """
    Elimina comentarios tipo // y /* */ fuera de strings.
    """
    result = []
    for line in text.splitlines():
        out, in_str, esc = [], False, False
        i = 0
        while i < len(line):
            ch = line[i]

            if esc:
                out.append(ch)
                esc = False
                i += 1
                continue

            if ch == "\\" and in_str:
                out.append(ch)
                esc = True
                i += 1
                continue

            if ch == '"':
                in_str = not in_str
                out.append(ch)
                i += 1
                continue

            if not in_str and line.startswith("//", i):
                break

            out.append(ch)
            i += 1

        result.append("".join(out))

    no_single = "\n".join(result)
    return BLOCK_COMMENT.sub("", no_single)


def extract_first_json(text: str) -> Optional[str]:
    """
    Extrae el primer bloque JSON con llaves balanceadas.
    """
    in_str, esc = False, False
    start = None
    stack = []

    # Buscar inicio del JSON
    for i, ch in enumerate(text):
        if esc:
            esc = False
            continue
        if ch == "\\":
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue

        if not in_str and ch in "{[":
            start = i
            stack.append(ch)
            break

    if start is None:
        return None

    # Buscar fin del JSON
    in_str, esc = False, False
    for j in range(start + 1, len(text)):
        ch = text[j]
        if esc:
            esc = False
            continue
        if ch == "\\":
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue

        if not in_str:
            if ch in "{[":
                stack.append(ch)
            elif ch in "}]":
                if stack:
                    stack.pop()
                if not stack:
                    return text[start:j + 1]

    return None


def repair_json(blob: str) -> str:
    """
    Repara errores comunes generados por LLM.
    """
    blob = RE_TRAILING_COMMA.sub(r"\1", blob)
    blob = RE_KEY_NO_QUOTES.sub(r'\1"\2":', blob)
    blob = re.sub(r"}\s*{", r"},{", blob)
    blob = re.sub(r"]\s*\[", r"],", blob)
    blob = re.sub(r",,+", ",", blob)
    return blob


def parse_llm_json(text: str, return_default: bool = True) -> Union[Dict[str, Any], Any]:
    """
    Parser robusto para texto devuelto por un LLM. Intenta extraer un bloque JSON,
    limpiarlo, repararlo y parsearlo.
    
    Args:
        text: Texto crudo de la respuesta del LLM
        return_default: Si es True, devuelve un dict por defecto en caso de error.
                       Si es False, lanza ValueError.
    
    Returns:
        Dict parseado o dict por defecto con errores vacíos
    
    Raises:
        ValueError: Si return_default=False y no se puede parsear
    """
    if not isinstance(text, str) or not text.strip():
        msg = "Respuesta vacía del modelo"
        if return_default:
            return {"errores": [], "resumen": msg, "archivo": "desconocido"}
        raise ValueError(msg)

    cleaned = strip_md_fences(text)
    cleaned = remove_json_comments_preserve_strings(cleaned)

    blob = extract_first_json(cleaned)
    if not blob:
        msg = "No se encontró JSON en la respuesta"
        if return_default:
            return {"errores": [], "resumen": msg, "archivo": "desconocido"}
        raise ValueError(msg)

    # Intentos de reparación
    attempts = [blob, repair_json(blob)]

    # Intento básico adicional: cerrar llaves
    need_obj = blob.count("{") - blob.count("}")
    need_arr = blob.count("[") - blob.count("]")

    if need_obj or need_arr:
        fixed = blob + "}" * max(0, need_obj) + "]" * max(0, need_arr)
        attempts.append(fixed)

    # Procesar intentos
    for candidate in attempts:
        try:
            parsed = json.loads(candidate)
            # Asegurar estructura mínima esperada
            if isinstance(parsed, dict):
                parsed.setdefault("errores", [])
                parsed.setdefault("resumen", "Análisis completado")
                parsed.setdefault("archivo", "desconocido")
            return parsed
        except json.JSONDecodeError:
            continue

    # Si todos los intentos fallan
    msg = f"No se pudo parsear JSON después de {len(attempts)} intentos"
    if return_default:
        return {
            "errores": [],
            "resumen": msg,
            "archivo": "desconocido",
            "respuesta_raw": text[:500]
        }
    raise ValueError(msg)


def extract_code_blocks(text: str) -> list[str]:
    """
    Extrae bloques de código de respuestas con formato markdown
    """
    pattern = r'```(?:\w+)?\n(.*?)```'
    matches = re.findall(pattern, text, re.DOTALL)
    return [m.strip() for m in matches]