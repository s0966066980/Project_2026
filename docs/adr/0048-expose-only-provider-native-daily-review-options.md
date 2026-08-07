# Expose only provider-native daily review options

Status: accepted

Admin may enable or disable Codex, Claude, and Grok as Daily Review Analyzer Profiles. Each adapter discovers the models and reasoning-effort values supported by its installed analyzer version, and the UI exposes those provider-native choices rather than inventing one shared scale or accepting arbitrary text. Every run explicitly names one enabled analyzer, one advertised model, and one advertised effort.

The selected analyzer version, model, and effort are included in the Daily Optimization Reference Report and data-egress audit. Unsupported values fail validation before evidence is sent. A runtime failure ends the run visibly and never switches analyzer, model, or effort automatically. Another analyzer may be compared only through a separate explicit run over the same frozen evidence selection.
