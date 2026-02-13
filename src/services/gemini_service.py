# src/services/gemini_service.py
import os
import requests

# 1. Configuramos las constantes (Sin la key en el string)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = "gemini-2.0-flash"
# Usamos un f-string correcto para el modelo
URL = f"https://generativelanguage.googleapis.com/v1/models/{MODEL_NAME}:generateContent"

class GeminiError(RuntimeError):
    pass

def call_gemini(prompt: str, timeout: int = 80) -> str:
    if not GEMINI_API_KEY:
        raise GeminiError("GEMINI_API_KEY no configurada en variables de entorno")
    
    body = {
        "contents": [
            {
                "parts": [{"text": prompt}]
            }
        ],
        "generationConfig": {
            "temperature": 0.0, 
            "maxOutputTokens": 10000,
            "response_mime_type": "application/json"  
        }
    }
    
    try:
        # 2. Realizar petición POST 
        # Dejamos que 'params' inserte la ?key= de forma limpia y sin espacios
        response = requests.post(
            URL,
            params={"key": GEMINI_API_KEY}, 
            json=body,
            timeout=timeout,
            headers={"Content-Type": "application/json"}
        )
        
        # 3. Verificar errores HTTP antes de procesar
        response.raise_for_status()
        
        data = response.json()
        
        # Validación de seguridad y estructura
        if "candidates" not in data or not data["candidates"]:
            raise GeminiError("Respuesta de Gemini sin candidatos")
        
        candidate = data["candidates"][0]
        
        if "finishReason" in candidate and candidate["finishReason"] not in ["STOP", "MAX_TOKENS"]:
            finish_reason = candidate.get("finishReason", "UNKNOWN")
            raise GeminiError(f"Respuesta bloqueada o incompleta: {finish_reason}")
        
        text = candidate["content"]["parts"][0]["text"]
        return text.strip()
        
    except requests.HTTPError as e:
        # Ahora el error 400 nos daría el detalle real de Google si algo más falla
        error_detail = e.response.json() if e.response.text else e.response.text
        raise GeminiError(f"HTTP {e.response.status_code}: {error_detail}") from e
    except Exception as e:
        raise GeminiError(f"Error inesperado: {str(e)}") from e