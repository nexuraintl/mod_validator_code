from flask import Blueprint, request, jsonify
from src.services.router_service import build_prompt
from src.services.gemini_service import call_gemini, GeminiError
from src.services.repo_service import get_last_commit_info, RepoServiceError
from src.utils.json_tools import parse_llm_json

upload_bp = Blueprint("upload", __name__, url_prefix="/analizar")


@upload_bp.post("/repositorio")
def analizar_repositorio():
    try:
        # recibe la peticion del cliente
        body_json = request.get_json(silent=True) or {}
        repo_url = body_json.get("repo_url") or request.form.get("repo_url")
        branch = body_json.get("branch") or request.form.get("branch")

        if not repo_url:
            return jsonify({"error": "repo_url es obligatorio"}), 400

        # obtiene Info del ultimo commit
        commit_info = get_last_commit_info(repo_url=repo_url, branch=branch)

        # Si por alguna razón no es dict, paramos aquí
        if not isinstance(commit_info, dict):
            raise RepoServiceError(
                f"Respuesta inesperada de get_last_commit_info (tipo {type(commit_info)}): {commit_info}"
            )

        # pasa el checklist y prepara el prompt para Gemini
        archivos = "\n".join(commit_info.get("files", [])) or "Sin archivos listados"

        texto = (
            f"Analiza el siguiente commit en un repositorio de Azure DevOps.\n\n"
            f"Repositorio: {commit_info.get('repo')}\n"
            f"Commit SHA: {commit_info.get('sha')}\n"
            f"Autor: {commit_info.get('author')}\n"
            f"Mensaje del commit: {commit_info.get('message')}\n\n"
            f"Archivos modificados:\n{archivos}\n"
        )

        
        prompt = build_prompt(
            texto=texto,
            categoria="revision_general"   
        )

        # Llamar a Gemini
        salida = call_gemini(prompt)

        # Parsear JSON de Gemini
        analisis = parse_llm_json(salida)

        # respuesta
        resp = {
            "repo_url": repo_url,
            "branch": branch or "refs/heads/main",
            "commit": {
                "sha": commit_info.get("sha"),
                "author": commit_info.get("author"),
                "message": commit_info.get("message"),
                "files": commit_info.get("files", []),
            },
            "analysis": analisis,
        }

        return jsonify(resp), 200

    except RepoServiceError as re:
        return jsonify({"error": str(re)}), 502
    except GeminiError as ge:
        return jsonify({"error": f"Error al llamar a Gemini: {ge}"}), 502
    except Exception as e:
        return jsonify({"error": f"fallo: {e}"}), 500
