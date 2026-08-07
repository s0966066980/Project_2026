# Skip unvalidated audio-only emotion without blocking Voice Turns

Status: accepted

R1-Omni exposes a native audio inference path, but neither upstream evidence nor this project's tests currently establish reliable audio-only emotion recognition. Kiosk therefore uses audiovisual evidence when camera and microphone media are available. When camera media is unavailable, the Voice Turn, ordering, and required synthesized-speech playback continue normally, while emotion analysis records an explicit skipped outcome instead of invoking unvalidated audio-only inference.

Audio-only emotion inference remains isolated to Admin experimentation until the selected Emotion Model Profile passes the project's controlled semantic-versus-prosody comparisons and earns Validated Audio-Only Emotion Capability. A declared health capability, a successful single inference, or a zero-valued visual placeholder is not sufficient validation.
