"""Project meetings: recurring series, agendas, attendance, action items and issued minutes.

A meeting in a series starts from the series' agenda template and default attendees. Action items
can become tasks (``tasks.service.create_task`` with ``entity=("meeting", id)``), and issuing the
minutes emails every attendee with an address a PDF copy.
"""
