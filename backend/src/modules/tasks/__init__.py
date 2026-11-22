"""Project tasks: five types, a Kanban board with WIP limits, and links to any record.

Other modules create tasks through ``service.create_task`` (meeting actions, inspection deficiencies,
NCR corrective actions), passing ``entity=(type, id)`` so the task links back to its source.
"""
