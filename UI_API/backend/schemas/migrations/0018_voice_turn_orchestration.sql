CREATE TABLE IF NOT EXISTS voice_turns (
    tenant_id UUID NOT NULL,
    store_id UUID NOT NULL,
    voice_turn_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN (
        'accepted', 'transcribing', 'assisting', 'synthesizing',
        'completed', 'transcription_failed', 'assistant_failed'
    )),
    audio_ref TEXT NOT NULL,
    transcript TEXT NOT NULL DEFAULT '',
    language TEXT NOT NULL DEFAULT '',
    assistant_text TEXT NOT NULL DEFAULT '',
    order_draft_json TEXT NOT NULL DEFAULT 'null',
    mentioned_ids_json TEXT NOT NULL DEFAULT '[]',
    tts_audio_ref TEXT NOT NULL DEFAULT '',
    tts_format TEXT NOT NULL DEFAULT '',
    playback_status TEXT NOT NULL DEFAULT '',
    safe_reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    PRIMARY KEY (tenant_id, store_id, voice_turn_id)
);

CREATE TABLE IF NOT EXISTS voice_turn_events (
    tenant_id UUID NOT NULL,
    store_id UUID NOT NULL,
    voice_turn_id TEXT NOT NULL,
    sequence BIGINT NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    terminal BOOLEAN NOT NULL DEFAULT FALSE,
    occurred_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, store_id, voice_turn_id, sequence),
    FOREIGN KEY (tenant_id, store_id, voice_turn_id)
        REFERENCES voice_turns (tenant_id, store_id, voice_turn_id)
);

CREATE INDEX IF NOT EXISTS voice_turns_session_idx
    ON voice_turns (tenant_id, store_id, session_id, updated_at DESC);
