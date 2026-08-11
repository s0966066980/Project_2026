# Separate emotion configuration from runtime readiness

Admin may save a non-Off Customer Emotion Analysis Mode while the selected Emotion Model Profile is not ready. The setting remains enabled and visible as degraded, but new customer captures pause before submission and resume automatically when readiness returns; an inference already submitted still records a safe failure under ADR-0033. This keeps operator intent durable without pretending an unavailable model is analysing customers or filling history with attempts that never began.
