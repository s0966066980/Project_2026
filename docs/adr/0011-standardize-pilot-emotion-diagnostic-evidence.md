# Standardize local-pilot emotion diagnostic evidence

Status: accepted

Local Pilot Readiness evaluates emotion diagnostics against six operational labels—Neutral, Happy, Frustrated, Anxious, Confused, and Angry—instead of provider-defined free text or the broader legacy text-classification vocabulary. The fixed Emotion Diagnostic Acceptance Set contains sixty balanced samples: five samples for each label in audio-only mode and five for each label in live-media mode. The modes pass independently only when their capability and output contracts pass completely, macro-F1 is at least 0.70, every label's recall is at least 0.50, and Emotion Observation Explanation never changes the provider's authoritative classification.

We chose the smaller operational vocabulary because it covers the store-ordering situations that staff can act on while keeping a local acceptance set balanced and repeatable. Retaining twelve labels would substantially increase collection and labeling cost, while provider-native free text would prevent objective comparison across providers and model versions.

The acceptance samples are not customer recordings and are never a training corpus. Audio-only evidence includes controlled comparisons of the same semantic content with different prosody and different semantic content with the same neutral prosody; a blank-video wrapper does not satisfy the audio-only contract.
