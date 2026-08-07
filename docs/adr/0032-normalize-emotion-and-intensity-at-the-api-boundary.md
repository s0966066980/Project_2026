# Normalize emotion and intensity at the API boundary

Status: accepted

Emotion APIs and persistence accept only the shared Operational Emotion Classification. Emotion is Neutral, Happy, Angry, Frustrated, Anxious, Confused, or Undetermined; intensity is Low, Medium, High, or Undetermined. Admin may display localized Traditional Chinese labels, but transport and storage use the stable canonical values.

Every Emotion Model Profile maps its provider-specific output before returning an accepted observation. Labels or intensities that cannot be mapped reliably become Undetermined rather than being guessed. Relevant provider detail may remain in the overall description, but free-form labels never enter reporting or history fields.
