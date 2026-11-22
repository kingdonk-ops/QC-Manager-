"""4D Schedule: a project's programme of activities, links, calendar and baselines.

``cpm`` (critical path), ``montecarlo`` (schedule risk) and ``interchange`` (P6 XER/XML and MS Project
XML) are pure Python; ``service`` stores and recalculates; ``router`` serves ``/api/v1/schedule``.
Other modules link to activities by id and read them through ``service.activity_snapshot``.
"""
