"""Temporary works register: items (falsework, formwork, propping and so on) and their permits to load, strike and
dismantle.

An item moves along a guarded main flow (identified through removed, with on hold as a side status). Loading and
striking are cleared only on positive evidence: a permit that is issued or active, inside its validity window, and
(for loading) records both prerequisites. An item that is loaded or in use with no valid permit to load is a
compliance breach. Gates, breaches, overdue lists and the clearance percentage are derived at read time for an
as-of day and are never stored.

The pure rule files (``rules``, ``validation``, ``transitions``) import neither the web framework nor the database
layer. The scaffolds module is an optional, one-way link: this module may use it, it never imports this one.
"""
