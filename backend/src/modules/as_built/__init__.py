"""As-built records: a captured value compared with an acceptance criterion of the inspections library.

A record starts as a draft, is surveyed (as often as needed while draft or surveyed, each survey storing a tolerance
result), is verified (an out-of-tolerance result then raises a workmanship report) and is finally signed as a
legal-record attestation. Verified records are never rewritten: a correction supersedes them and a new record is made.

Permissions: ``as_built.read`` to read, ``create`` and ``update`` for editors (create, edit, survey), ``delete`` for
managers, ``review`` to verify and ``approve`` to sign the attestation.
"""
