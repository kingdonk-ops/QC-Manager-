"""The project's physical and work breakdown: Site → Area → Asset → RSW → Items, configured per project.

Levels are data (``AssetLevel``); rules bind to a level's **roles**, never its name:
``grouping``, ``physical``, ``work_anchor``, ``inspection_anchor``, ``progress_unit``, ``schedule_link``.
Work books against a work-anchor node (RSW by default), at most one per root-to-leaf path;
inspections anchor to an ``inspection_anchor`` node or an Item. Other modules use
``service.work_anchor_for(db, node_id)``, ``service.node_path(db, node_id)`` and
``service.subtree_ids(db, node_id, with_lineage=True)``.
"""
