"""In-app notifications with per-category preferences, and email through the mail service.

Other modules call ``notify``:

    from ..notifications.service import notify
    await notify(db, [user_id], "assignment", "RFI-004 is in your court", link="/rfi?id=4",
                 entity=("rfi", 4), actor_id=me)

It adds the rows to the caller's transaction (commit with your own work) and emails the users whose
preference for that category asks for it, after the commit.
"""
