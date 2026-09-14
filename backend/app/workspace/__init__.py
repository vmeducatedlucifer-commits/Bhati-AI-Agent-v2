"""Workspace layer: per-session and per-agent file areas."""

from app.workspace.manager import WorkspaceManager, get_workspace_manager, workspaces

__all__ = ["WorkspaceManager", "get_workspace_manager", "workspaces"]
