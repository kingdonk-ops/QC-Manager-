"""The project lobby: access requests, project invites, and lobby listing.

How access is granted (see ``service``): an approved request or an accepted invite either adds the person to
the project's **client team** (externals, when the project has one: they then see exactly what the client
portal shows that team) or writes a **direct project member** row (``projects.ProjectMember``), which
``readable_project`` honours like client-team membership. Neither grants permissions: roles still decide
which modules a person may use.
"""
