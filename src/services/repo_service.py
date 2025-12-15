import os
import base64
import requests
from urllib.parse import urlparse, unquote


class RepoServiceError(Exception):
    pass


def _parse_azure_repo_url(repo_url: str):
    parsed = urlparse(repo_url)
    host = parsed.netloc.lower()
    parts = parsed.path.strip("/").split("/")

    if "dev.azure.com" in host:
        if len(parts) < 4 or parts[2] != "_git":
            raise RepoServiceError(
                "URL de Azure DevOps inválida. "
            )
        organization = parts[0]
        project = unquote(parts[1])
        repo = parts[3]
        return organization, project, repo

    # Formato viejo
    if "visualstudio.com" in host:
        organization = host.split(".")[0]

        
        if len(parts) < 3 or parts[1] != "_git":
            raise RepoServiceError(
                "URL de Azure DevOps inválida. "
            )

        project = unquote(parts[0])
        repo = parts[2]
        return organization, project, repo

    # Si no corresponde
    raise RepoServiceError(
        "Host de Azure DevOps no reconocido."
    )


def _build_azure_auth_header():
    pat = os.getenv("AZURE_PAT")
    if not pat:
        raise RepoServiceError("Variable de entorno AZURE_PAT no configurada")
    token = ":" + pat
    basic = base64.b64encode(token.encode()).decode()
    return {"Authorization": f"Basic {basic}"}

# Obtener info del último commit (lista de archivos modificados)
def get_last_commit_info(repo_url: str, branch: str | None = None) -> dict:
    if branch is None:
        branch = "main"

    organization, project, repo = _parse_azure_repo_url(repo_url)
    headers = _build_azure_auth_header()

    commits_url = (
        f"https://dev.azure.com/{organization}/{project}/_apis/git/repositories/"
        f"{repo}/commits"
    )

    params = {
        "searchCriteria.itemVersion.version": branch,
        "searchCriteria.itemVersion.versionType": "branch",
        # Solo el último commit
        "$top": 1, 
        "api-version": "7.1-preview.1",
    }

    r = requests.get(commits_url, headers=headers, params=params, timeout=15)
    if r.status_code != 200:
        raise RepoServiceError(
            f"Error al obtener commits de Azure DevOps: {r.status_code} {r.text}"
        )

    data = r.json()
    commits = data.get("value") or []
    if not commits:
        raise RepoServiceError("No se encontraron commits en la rama indicada")

    commit = commits[0]
    commit_id = commit.get("commitId")

    author_obj = commit.get("author") or {}
    author = author_obj.get("name")
    message = commit.get("comment")

    changes_url = (
        f"https://dev.azure.com/{organization}/{project}/_apis/git/repositories/"
        f"{repo}/commits/{commit_id}/changes?api-version=7.1-preview.1"
    )

    r2 = requests.get(changes_url, headers=headers, timeout=15)
    if r2.status_code != 200:
        raise RepoServiceError(
            f"Error al obtener cambios del commit: {r2.status_code} {r2.text}"
        )

    detail = r2.json() or {}
    files: list[str] = []
    for change in detail.get("changes") or []:
        item = change.get("item") or {}
        path = item.get("path", "desconocido")
        files.append(path)

    return {
        "repo": f"{organization}/{project}/{repo}",
        "sha": commit_id,
        "author": author,
        "message": message,
        "files": files,
        "diff": "",
    }
