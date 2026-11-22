"""Change orders: priced line items (original against new), an approval workflow and the project's change log.

An approved change order can push its line deltas into the linked CVR cost heads' forecasts
(``cvr_apply``). It does so directly when ``cvr`` is on for the project, and always publishes
``change_orders.change_order.approved`` for anything else that listens.
"""
