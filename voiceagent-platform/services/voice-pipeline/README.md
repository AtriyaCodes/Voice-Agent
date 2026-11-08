# voice-pipeline

Streaming voice activity detection, speech to text, text to speech, and
turn-taking policy. STT and TTS providers are pluggable (`stt.py`,
`tts.py` define the interfaces) so a tenant can be configured to use an
on-prem model or a hosted provider without changing `pipeline.py`.

## Test

```bash
python -m pytest
```
