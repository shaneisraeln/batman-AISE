"""BATMAN cloud control plane — users, projects, models, keys, upstream config.

This layer sits on top of the Phase 1 detection engine and the Phase 2
persistence layer. It never touches the detection decision path: the policy
engine remains authoritative and the LLM stays advisory.
"""
