"""Catalog entry builders.

Helpers that emit Strategy / Tactic / Mode / Technique dicts from compact
overlay inputs. Files here are NOT loaded by the catalog loader (which only
scans ``registries/<kind>/*.py`` looking for the matching constant) — they
are imported by individual catalog registry modules to share a skeleton.
"""
