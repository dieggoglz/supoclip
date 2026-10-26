-- Word-timed transcripts of transcript-only tasks, readable through the API.
-- Stored in the database because the media sidecar may be cleaned up or live in remote storage.
CREATE TABLE IF NOT EXISTS task_transcripts (
    task_id VARCHAR(36) PRIMARY KEY REFERENCES tasks(id) ON DELETE CASCADE,
    transcript_json JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);
