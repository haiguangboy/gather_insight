# Source policy

Source roles are not interchangeable:

1. official human transcript;
2. uListen;
3. UseTranscribe;
4. manually supplied Markdown;
5. YouTube transcript export.

YouTube remains the final evidence timeline. Third-party transcripts must never be labeled official. Phase 2 resolves sources in the listed order and records every check in the manifest.

Source checks are degradable: a missing or malformed higher-priority source is recorded and does not block a lower-priority local source. A URL-only source is recorded as `url_only` and requires a human download/export before ingest. No login state or paid API is used.

The repository does not store audio or video. Full third-party transcripts are not published. External articles and social expressions may help discovery, but they are not primary evidence and must be labeled separately.
