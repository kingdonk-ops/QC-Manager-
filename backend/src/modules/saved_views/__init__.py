"""Saved register views: a grid's columns, widths, order, sort, filters and grouping, saved per register and project.

A register is named by a key such as ``rfi.register`` or ``asset_tree.items``; the frontend's
``useSavedViews(registerKey)`` and ``<SavedViewsMenu>`` apply a view to a ``DataGrid``. Views are
personal (``private``), shared with everyone who can read the project (``project``), or with named
teams (``team``). Each person may pick a default per register; a manager may set a project default.
"""
