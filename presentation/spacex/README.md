# Project Supernova — SpaceX-track pitch deck

Complete Cal Hacks / SpaceXAI presentation built from:

1. The plan Page **2-minute demo script** (`script.json`, from the hackathon plan “Pitch and why it wins” + demo table)
2. Live SpaceX-theme product screenshots at `https://supernova.lylinks.com/spacex/`
3. A SpaceX-theme usage walkthrough clip

## Deliverables

| Artifact | Location |
| --- | --- |
| PowerPoint | `Project_Supernova_SpaceX_Pitch.pptx` (also `/opt/cursor/artifacts/`) |
| Individual slides (1920×1080) | `slides/*.png` |
| Voiceover video (~2:43) | `Project_Supernova_SpaceX_Pitch_voiceover.mp4` |
| Raw product shots | `/opt/cursor/artifacts/presentation/shots/` |
| Walkthrough only | `/opt/cursor/artifacts/spacex-demo-usage-walkthrough.mp4` |

## Slide order (script)

1. Title — Nobel hook  
2. The race — neutrinos first  
3. Idle webcast stage (product shot)  
4. Replay event cards (product shot)  
5. IceCube AOI localization (product shot)  
6. Ranked progenitors / literature (product shot)  
7. Betelgeuse SIM honesty (product shot)  
8. Subscribe endpoints (product shot)  
9. About / mission brief (product shot)  
10. **Walkthrough insert** (live UI demo + VO intro)  
11. Built with Cursor + Grok Bot  
12. Close / URL  

## Rebuild

```bash
# 1) Capture production shots + walkthrough
node presentation/spacex/capture_shots.mjs
npx playwright install ffmpeg   # once
node presentation/spacex/capture_walkthrough.mjs

# 2) Render slides + PPTX
python3 presentation/spacex/build_slides.py

# 3) TTS (edge-tts) then compose video
export PATH="$HOME/.local/bin:$PATH"
# (re-run edge-tts loop in build notes, or reuse audio/)
python3 presentation/spacex/build_video.py
```

Voice: `en-US-ChristopherNeural` via `edge-tts`. Narration text lives in `script.json` (`say` per slide).
