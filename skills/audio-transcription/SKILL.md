---
name: audio-transcription
description: Media toolkit — transcribe audio (Whisper), search GIFs (Tenor), extract YouTube transcripts, and generate AI music (Suno). Covers .ogg, .mp3, .wav, .m4a, .flac, GIFs, YouTube, and songwriting.
version: 2.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [audio, transcription, Whisper, voice, media, GIF, YouTube, music, Suno]
    related_skills: []
---

# Media Toolkit

Handle all media content: audio transcription, GIF search, YouTube transcripts, and AI music generation.

## Quick Reference

| Task | Section |
|------|---------|
| Transcribe audio (.ogg, .mp3, .wav) | [Audio Transcription](#audio-transcription) |
| Search/download GIFs | [GIF Search](#gif-search-tenor-api) |
| YouTube transcripts/summaries | [YouTube Content](#youtube-content) |
| AI music generation (Suno) | [Songwriting & AI Music](#songwriting--ai-music) |

## GIF Search (Tenor API)

Search and download GIFs directly via the Tenor API using curl. No extra tools needed.

### When to use

Useful for finding reaction GIFs, creating visual content, and sending GIFs in chat.

### Setup

Set your Tenor API key in your environment (add to `${HERMES_HOME:-~/.hermes}/.env`):

```bash
TENOR_API_KEY=your_key_here
```

Get a free API key at https://developers.google.com/tenor/guides/quickstart — the Google Cloud Console Tenor API key is free and has generous rate limits.

### Prerequisites

- `curl` and `jq` (both standard on macOS/Linux)
- `TENOR_API_KEY` environment variable

### Search for GIFs

```bash
# Search and get GIF URLs
curl -s "https://tenor.googleapis.com/v2/search?q=thumbs+up&limit=5&key=${TENOR_API_KEY}" | jq -r '.results[].media_formats.gif.url'

# Get smaller/preview versions
curl -s "https://tenor.googleapis.com/v2/search?q=nice+work&limit=3&key=${TENOR_API_KEY}" | jq -r '.results[].media_formats.tinygif.url'
```

### Download a GIF

```bash
# Search and download the top result
URL=$(curl -s "https://tenor.googleapis.com/v2/search?q=celebration&limit=1&key=${TENOR_API_KEY}" | jq -r '.results[0].media_formats.gif.url')
curl -sL "$URL" -o celebration.gif
```

### Get Full Metadata

```bash
curl -s "https://tenor.googleapis.com/v2/search?q=cat&limit=3&key=${TENOR_API_KEY}" | jq '.results[] | {title: .title, url: .media_formats.gif.url, preview: .media_formats.tinygif.url, dimensions: .media_formats.gif.dims}'
```

### API Parameters

| Parameter | Description |
|-----------|-------------|
| `q` | Search query (URL-encode spaces as `+`) |
| `limit` | Max results (1-50, default 20) |
| `key` | API key (from `$TENOR_API_KEY` env var) |
| `media_filter` | Filter formats: `gif`, `tinygif`, `mp4`, `tinymp4`, `webm` |
| `contentfilter` | Safety: `off`, `low`, `medium`, `high` |
| `locale` | Language: `en_US`, `es`, `fr`, etc. |

### Available Media Formats

Each result has multiple formats under `.media_formats`:

| Format | Use case |
|--------|----------|
| `gif` | Full quality GIF |
| `tinygif` | Small preview GIF |
| `mp4` | Video version (smaller file size) |
| `tinymp4` | Small preview video |
| `webm` | WebM video |
| `nanogif` | Tiny thumbnail |

### Notes

- URL-encode the query: spaces as `+`, special chars as `%XX`
- For sending in chat, `tinygif` URLs are lighter weight
- GIF URLs can be used directly in markdown: `![alt](url)`

---

## YouTube Content

Extract transcripts from YouTube videos, generate summaries, threads, or blog posts.

### When to use

- User shares a YouTube URL or video link
- User asks to summarize a video, requests a transcript
- User wants to extract and reformat content from any YouTube video

### Setup

Use `uv` so the dependency is installed into the same Hermes-managed environment:

```bash
uv pip install youtube-transcript-api
```

### Workflow

#### 1. Extract Transcript — Preferred method (helper script)

`SKILL_DIR` is the directory containing this SKILL.md. The script accepts any standard YouTube URL format, short links (youtu.be), shorts, embeds, live links, or a raw 11-character video ID.

```bash
# JSON output with metadata
uv run python3 SKILL_DIR/scripts/fetch_transcript.py "https://youtube.com/watch?v=VIDEO_ID"

# Plain text (good for piping into further processing)
uv run python3 SKILL_DIR/scripts/fetch_transcript.py "URL" --text-only

# With timestamps
uv run python3 SKILL_DIR/scripts/fetch_transcript.py "URL" --timestamps

# Specific language with fallback chain
uv run python3 SKILL_DIR/scripts/fetch_transcript.py "URL" --language tr,en
```

#### 2. Alternative methods

```bash
# Use yt-dlp to extract subtitles/transcript
yt-dlp --write-auto-sub --skip-download --sub-lang es --sub-format vtt --output "%(title)s.%(ext)s" "https://youtube.com/watch?v=VIDEO_ID"
```

Or use `web_extract` on the YouTube URL directly:
```
web_extract(urls=["https://youtube.com/watch?v=VIDEO_ID"])
```

#### 3. Validate and chunk

- Confirm the output is non-empty and in the expected language. If empty, retry without `--language` to get any available transcript.
- If the transcript exceeds ~50K characters, split into overlapping chunks (~40K with 2K overlap) and summarize each chunk before merging.

#### 4. Transform into output format

If the user did not specify a format, default to a summary:

- **Chapters**: Group by topic shifts, output timestamped chapter list
- **Summary**: Concise 5-10 sentence overview of the entire video
- **Chapter summaries**: Chapters with a short paragraph summary for each
- **Thread**: Twitter/X thread format — numbered posts, each under 280 chars
- **Blog post**: Full article with title, sections, and key takeaways
- **Quotes**: Notable quotes with timestamps

#### 5. Verify

Re-read the transformed output to check for coherence, correct timestamps, and completeness before presenting.

### Error Handling

- **Transcript disabled**: tell the user; suggest they check if subtitles are available on the video page.
- **Private/unavailable video**: relay the error and ask the user to verify the URL.
- **No matching language**: retry without `--language` to fetch any available transcript, then note the actual language to the user.
- **Dependency missing**: run `uv pip install youtube-transcript-api` and retry.

### Common Pitfalls

- **No subtitles available**: Some videos have no auto-generated subtitles. Check with `yt-dlp --list-subs` first
- **Language mismatch**: Auto-subtitles may be in a different language than expected. Use `--sub-lang` to specify
- **Long videos**: Transcripts for 1-hour+ videos can exceed context limits. Summarize in chunks

---

## Songwriting & AI Music

Generate AI music using Suno AI and craft songwriting prompts.

### When to use

- User asks to create music, a song, or audio track
- User wants to generate AI music with specific lyrics or style
- User asks about songwriting techniques or music production

### Suno AI Workflow

#### 1. Craft the Prompt

```
Style: [genre, mood, tempo]
Lyrics: [custom lyrics or "instrumental"]
Title: [song title]
```

#### 2. Generate

Use the Suno API or web interface with the crafted prompt.

#### 3. Iterate

- Adjust genre/mood if the result doesn't match
- Refine lyrics for better flow
- Try different tempo or instrumentation

### Songwriting Tips

- **Structure**: Verse → Chorus → Verse → Chorus → Bridge → Chorus
- **Rhyme schemes**: AABB, ABAB, or free verse depending on genre
- **Hook**: Make the chorus memorable and repeatable
- **Meter**: Keep syllable counts consistent within verses

### Common Pitfalls

- **Too generic prompts**: "Make a pop song" produces mediocre results. Be specific: "Upbeat indie pop, female vocals, 120 BPM, about summer road trips"
- **Lyrics too long**: Suno has character limits. Keep lyrics under 3000 characters
- **Style conflicts**: Don't mix incompatible genres (e.g., "death metal lullaby")

---

## Notes

- `vision_analyze` does NOT support audio — use Whisper for transcription
- GIF search requires `TENOR_API_KEY` — check `.env` before attempting
- YouTube transcript extraction requires `yt-dlp` — install with `pip install yt-dlp`
- Suno AI requires API access — check credentials before generating
