from __future__ import annotations

from app.agents.planner import Plan, Task


def test_dependency_scheduling() -> None:
    plan = Plan(
        summary="demo",
        tasks=[
            Task(id="t1", title="a"),
            Task(id="t2", title="b", depends_on=["t1"]),
            Task(id="t3", title="c"),
        ],
    )
    ready = {task.id for task in plan.ready()}
    assert ready == {"t1", "t3"}
    plan.tasks[0].status = "done"
    plan.tasks[2].status = "done"
    assert [task.id for task in plan.ready()] == ["t2"]


def test_unfinished() -> None:
    plan = Plan(summary="demo", tasks=[Task(id="t1", title="a", status="done")])
    assert plan.unfinished() is False
