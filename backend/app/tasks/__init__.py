"""User-facing task board: the panel where you assign work to the swarm."""

from app.tasks.board import BoardTask, TaskBoard, get_task_board

__all__ = ["BoardTask", "TaskBoard", "get_task_board"]
