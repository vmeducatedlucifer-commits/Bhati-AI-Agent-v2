"""Autonomous coding support: clone, diff, commit, branch, push, open PR."""

from __future__ import annotations

import httpx

from app.core.config import settings
from app.sandbox.runner import get_sandbox
from app.tools.base import Permission, Tool, ToolContext, ToolResult, tool_schema


async def _git(ctx: ToolContext, args: str, cwd: str = ".", timeout: int = 180) -> ToolResult:
    sandbox = get_sandbox()
    result = await sandbox.exec(f"git {args}", workdir=ctx.resolve(cwd), timeout=timeout)
    output = (result.stdout + ("\n" + result.stderr if result.stderr else "")).strip()
    if result.exit_code != 0:
        return ToolResult.failure(output or f"git {args} failed")
    return ToolResult.success(output or "(ok)")


async def git_clone(ctx: ToolContext, repo_url: str, directory: str = "") -> ToolResult:
    target = directory or repo_url.rstrip("/").split("/")[-1].removesuffix(".git")
    url = repo_url
    if settings.github_token and url.startswith("https://github.com/"):
        url = url.replace("https://", f"https://{settings.github_token}@")
    return await _git(ctx, f"clone --depth 50 {url} {target}", timeout=600)


async def git_status(ctx: ToolContext, repo: str = ".") -> ToolResult:
    return await _git(ctx, "status --short --branch", cwd=repo)


async def git_diff(ctx: ToolContext, repo: str = ".", staged: bool = False) -> ToolResult:
    return await _git(ctx, f"diff{' --cached' if staged else ''}", cwd=repo)


async def git_commit(ctx: ToolContext, message: str, repo: str = ".", add_all: bool = True) -> ToolResult:
    if add_all:
        staged = await _git(ctx, "add -A", cwd=repo)
        if not staged.ok:
            return staged
    safe_message = message.replace('"', "'")
    return await _git(ctx, f'-c user.name="Bhati Agent" -c user.email="agent@bhati.ai" commit -m "{safe_message}"', cwd=repo)


async def git_branch(ctx: ToolContext, name: str, repo: str = ".") -> ToolResult:
    return await _git(ctx, f"checkout -b {name}", cwd=repo)


async def git_push(ctx: ToolContext, branch: str, repo: str = ".") -> ToolResult:
    return await _git(ctx, f"push -u origin {branch}", cwd=repo, timeout=600)


async def open_pull_request(
    owner: str, repo: str, title: str, head: str, base: str = "main", body: str = ""
) -> ToolResult:
    if not settings.github_token:
        return ToolResult.failure("GITHUB_TOKEN is not configured")
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"https://api.github.com/repos/{owner}/{repo}/pulls",
            headers={
                "Authorization": f"Bearer {settings.github_token}",
                "Accept": "application/vnd.github+json",
            },
            json={"title": title, "head": head, "base": base, "body": body},
        )
    if response.status_code >= 400:
        return ToolResult.failure(f"GitHub API {response.status_code}: {response.text[:400]}")
    data = response.json()
    return ToolResult.success(f"PR opened: {data.get('html_url')}", url=data.get("html_url"))


GIT_TOOLS = [
    Tool(
        name="git_clone",
        description="Clone a git repository into the workspace.",
        parameters=tool_schema(
            repo_url={"type": "string", "required": True}, directory={"type": "string"}
        ),
        handler=git_clone,
        permission=Permission.DANGEROUS,
        tags=["git", "coding"],
    ),
    Tool(
        name="git_status",
        description="Show git status of a repository in the workspace.",
        parameters=tool_schema(repo={"type": "string", "default": "."}),
        handler=git_status,
        permission=Permission.SAFE,
        tags=["git", "coding"],
    ),
    Tool(
        name="git_diff",
        description="Show the working-tree or staged diff.",
        parameters=tool_schema(
            repo={"type": "string", "default": "."}, staged={"type": "boolean", "default": False}
        ),
        handler=git_diff,
        permission=Permission.SAFE,
        tags=["git", "coding"],
    ),
    Tool(
        name="git_commit",
        description="Stage all changes and create a commit.",
        parameters=tool_schema(
            message={"type": "string", "required": True},
            repo={"type": "string", "default": "."},
            add_all={"type": "boolean", "default": True},
        ),
        handler=git_commit,
        permission=Permission.WRITE,
        tags=["git", "coding"],
    ),
    Tool(
        name="git_branch",
        description="Create and switch to a new branch.",
        parameters=tool_schema(
            name={"type": "string", "required": True}, repo={"type": "string", "default": "."}
        ),
        handler=git_branch,
        permission=Permission.WRITE,
        tags=["git", "coding"],
    ),
    Tool(
        name="git_push",
        description="Push a branch to origin (requires GITHUB_TOKEN for private repos).",
        parameters=tool_schema(
            branch={"type": "string", "required": True}, repo={"type": "string", "default": "."}
        ),
        handler=git_push,
        permission=Permission.DANGEROUS,
        tags=["git", "coding"],
    ),
    Tool(
        name="open_pull_request",
        description="Open a GitHub pull request from a pushed branch.",
        parameters=tool_schema(
            owner={"type": "string", "required": True},
            repo={"type": "string", "required": True},
            title={"type": "string", "required": True},
            head={"type": "string", "required": True},
            base={"type": "string", "default": "main"},
            body={"type": "string", "default": ""},
        ),
        handler=open_pull_request,
        permission=Permission.DANGEROUS,
        tags=["git", "coding"],
    ),
]
