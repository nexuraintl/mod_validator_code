import os
import requests
import sys

# Añadir el directorio actual al path para importar módulos locales
sys.path.append(os.getcwd())

# --- Importar sevices ---
from src.services.gemini_service import call_gemini, GeminiError
from src.services.router_service import build_prompt
from src.utils.json_tools import parse_llm_json

# --- CONFIGURACION CON AZURE ---
AZURE_PAT = os.environ.get("AZURE_PAT")
ORG_URL = os.environ.get("SYSTEM_TEAMFOUNDATIONCOLLECTIONURI")
PROJECT = os.environ.get("SYSTEM_TEAMPROJECT")
REPO_ID = os.environ.get("BUILD_REPOSITORY_ID")
COMMIT_ID = os.environ.get("BUILD_SOURCEVERSION")

# Configuración
EXTENSIONS_PERMITIDAS = (".py", ".js", ".ts", ".php", ".java", ".html", ".css", ".sql")


def get_changed_files():
    """
    Obtiene la lista de archivos cambiados desde Azure DevOps.
    """
    if not all([AZURE_PAT, ORG_URL, PROJECT, REPO_ID, COMMIT_ID]):
        print("##[warning] Variables de Azure DevOps no configuradas completamente")
        return []

    url = f"{ORG_URL}{PROJECT}/_apis/git/repositories/{REPO_ID}/commits/{COMMIT_ID}/changes?api-version=7.0"

    try:
        response = requests.get(url, auth=("", AZURE_PAT), timeout=30)
        if response.status_code != 200:
            print(
                f"##[error] Error API Azure ({response.status_code}): {response.text}"
            )
            return []

        files = []
        for change in response.json().get("changes", []):
            item = change.get("item", {})
            # Filtra solo archivos editados/agregados (no borrados)
            if (
                item.get("gitObjectType") == "blob"
                and change.get("changeType") != "delete"
            ):
                files.append(item["path"])
        return files
    except requests.Timeout:
        print("##[error] Timeout conectando a Azure DevOps API")
        return []
    except Exception as e:
        print(f"##[error] Excepción conectando a Azure: {e}")
        return []


def analyze_file(file_path_azure):
    """
    Lee archivo, arma prompt y llama a Gemini.
    """
    # Convertir path de Azure a local
    local_path = file_path_azure.lstrip("/")

    if not os.path.exists(local_path):
        print(f" Archivo no encontrado localmente: {local_path}")
        return None

    print(f" Analizando: {local_path}...")

    try:
        # 1. Leer contenido
        with open(local_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        # 2. Detectar extensión
        _, ext = os.path.splitext(local_path)

        # 3. Armar Prompt
        full_prompt = build_prompt(texto=content, categoria="revision_general", ext=ext)

        # 4. Llamar a Gemini
        resultado = call_gemini(prompt=full_prompt)

        # Parsear resultado (JSON)
        print(f"   Parseando respuesta...")
        resultado = parse_llm_json(resultado, return_default=True)

        # Agregar metadata
        resultado["archivo"] = local_path
        return resultado

    except GeminiError as ge:
        print(f"##[error] Error de Gemini para {local_path}: {ge}")
        return None
    except Exception as e:
        print(f"##[error] Error procesando {local_path}: {e}")
        import traceback

        traceback.print_exc()
        return None


def print_results(resultados):
    """
    Imprime resultados en consola Azure DevOps
    Formato json:
    """
    print("\n" + "=" * 80)
    print("Analisis:")
    print("=" * 80)

    archivos_analizados = len([r for r in resultados if r])
    total_errores = sum(len(r.get("errores", [])) for r in resultados if r)
    total_sugerencias = sum(len(r.get("sugerencias", [])) for r in resultados if r)

    print(f"\n Archivos analizados: {archivos_analizados}")
    print(f" Errores encontrados: {total_errores}")
    print(f" Sugerencias generadas: {total_sugerencias}")

    # Detalle por archivo
    for resultado in resultados:
        if not resultado:
            continue

        archivo = resultado.get("archivo", "desconocido")
        errores = resultado.get("errores", [])
        sugerencias = resultado.get("sugerencias", [])
        resumen = resultado.get("resumen", "Sin resumen")

        print(f"\n{'─'*80}")
        print(f" ARCHIVO: {archivo}")
        print(f"{'─'*80}")
        print(f" Resumen: {resumen}\n")

        if errores:
            print(f"Errores encontrados ({len(errores)}):")
            for i, error in enumerate(errores, 1):
                desc = error.get("descripcion", "Sin descripción")
                linea = error.get("linea", "N/A")
                print(f"   {i}. [Línea {linea}] {desc}")
                # Formato Azure DevOps para warnings
                print(
                    f"##vso[task.logissue type=warning;sourcepath={archivo};linenumber={linea}]{desc}"
                )
        else:
            print("No se encontraron errores")

        if sugerencias:
            print(f"\nSugerencias de cambios({len(sugerencias)}):")
            for i, sug in enumerate(sugerencias, 1):
                print(f"   {i}. {sug}")
        else:
            print("\n El codigo no tiene errores")

    print(f"\n{'='*80}")

    # Resumen final con formato Azure DevOps
    if total_errores > 0:
        print(
            f"##vso[task.complete result=SucceededWithIssues;]Análisis completado con {total_errores} errores"
        )
    else:
        print(f"##vso[task.complete result=Succeeded;]Análisis completado sin errores")

    return total_errores


def main():
    """
    Función principal del pipeline
    """
    print("Iniciando Pipeline de Análisis de Código con Gemini")
    print("=" * 80)

    # Verificar API key de Gemini
    if not os.getenv("GEMINI_API_KEY"):
        print("##[error] GEMINI_API_KEY no configurada")
        sys.exit(1)

    # Obtener archivos modificados
    print("\n Obteniendo archivos modificados del ultimo commit")
    changed_files = get_changed_files()

    # Filtrar por extensiones permitidas
    files_to_check = [f for f in changed_files if f.endswith(EXTENSIONS_PERMITIDAS)]

    print(f"\n Archivos a revisar ({len(files_to_check)}):")
    for f in files_to_check:
        print(f"   • {f}")

    if not files_to_check:
        print("\nNo hay cambios en archivos de código. Pipeline completado.")
        return

    # Analizar cada archivo
    print(f"\n{'='*80}")
    print("Analizando")
    print("=" * 80)

    resultados = []
    for file_path in files_to_check:
        resultado = analyze_file(file_path)
        if resultado:
            resultados.append(resultado)

    # Imprimir resultados
    if resultados:
        total_errores = print_results(resultados)




if __name__ == "__main__":
    main()
