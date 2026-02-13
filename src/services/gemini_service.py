# src/services/gemini_service.py
import os
import requests

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = "gemini-2.0-flash"
URL = "https://generativelanguage.googleapis.com/v1/models/{MODEL_NAME}:generateContent?key= {GEMINI_API_KEY}"

class GeminiError(RuntimeError):
    pass


def call_gemini(prompt: str, timeout: int = 80) -> str:
    """
    Llama a Gemini API usando REST y fuerza respuesta JSON pura
    
    """
    if not GEMINI_API_KEY:
        raise GeminiError("GEMINI_API_KEY no configurada en variables de entorno")
    
    # Configuración del cuerpo de la petición
    body = {
        "contents": [
            {
                "parts": [{"text": prompt}]
            }
        ],
        "generationConfig": {
            "temperature": 0.0, 
            "maxOutputTokens": 10000,
            "responseMimeType": "application/json"  
        }
    }
    
    try:
        # Realizar petición POST
        response = requests.post(
            URL,
            params={"key": GEMINI_API_KEY},
            json=body,
            timeout=timeout,
            headers={"Content-Type": "application/json"}
        )
        
        # Verificar status code
        response.raise_for_status()
        
        # Extraer respuesta
        data = response.json()
        
        # Validar estructura de respuesta
        if "candidates" not in data or not data["candidates"]:
            raise GeminiError("Respuesta de Gemini sin candidatos")
        
        candidate = data["candidates"][0]
        
        # Verificar bloqueos de seguridad
        if "finishReason" in candidate and candidate["finishReason"] != "STOP":
            finish_reason = candidate.get("finishReason", "UNKNOWN")
            raise GeminiError(f"Respuesta bloqueada por seguridad: {finish_reason}")
        
        # Extraer texto
        text = candidate["content"]["parts"][0]["text"]
        
        return text.strip()
        
    except requests.HTTPError as e:
        error_msg = e.response.text[:300] if e.response else str(e)
        raise GeminiError(f"HTTP {e.response.status_code}: {error_msg}") from e
    
    except requests.Timeout:
        raise GeminiError(f"Timeout después de {timeout} segundos")
    
    except KeyError as e:
        raise GeminiError(f"Estructura de respuesta inesperada: falta clave {e}") from e
    
    except Exception as e:
        raise GeminiError(f"Error inesperado: {str(e)}") from e