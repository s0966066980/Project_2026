"""Operations module: health, readiness, observability, worker and settings.

The capability publishes these; nothing outside reaches past this package for
them. Session statistics live here too, which is why Recommendation reads them
through the Operations surface rather than owning a copy.
"""
