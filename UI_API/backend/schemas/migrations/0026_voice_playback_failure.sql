ALTER TABLE voice_turns
    DROP CONSTRAINT voice_turns_status_check;

ALTER TABLE voice_turns
    ADD CONSTRAINT voice_turns_status_check CHECK (status IN (
        'accepted', 'transcribing', 'assisting', 'synthesizing',
        'completed', 'transcription_failed', 'assistant_failed', 'playback_failed'
    ));
