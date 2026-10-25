# Cached announcer clips (Scenario A)

MP3s for `VOICE_MODE=cached` (`0.mp3` … `4.mp3`), speak order: PRESN alert,
SN_BURST alert, localization, top candidate, breakout countdown.

```bash
python -m backend.voice.announcer --prerender scenario_a_galactic_ccsn --force
```

Silent placeholders may ship so offline preflight passes without calling xAI;
replace with real Grok TTS audio before demo day.
