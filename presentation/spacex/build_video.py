#!/usr/bin/env python3
"""Compose pitch video: SpaceX slides + voiceover + demo walkthrough."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ART = Path("/opt/cursor/artifacts/presentation")
SLIDES = ART / "slides"
AUDIO = ART / "audio"
WORK = ART / "work" / "segments"
SCRIPT = json.loads((ROOT / "script.json").read_text())

W, H = 1920, 1080


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd[:8]), "...")
    subprocess.check_call(cmd)


def probe_duration(path: Path) -> float:
    out = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        text=True,
    ).strip()
    return float(out)


def slide_segment(png: Path, mp3: Path, out: Path, pad: float = 0.45) -> Path:
    dur = probe_duration(mp3) + pad
    # still image + audio → h264
    run(
        [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-i",
            str(png),
            "-i",
            str(mp3),
            "-c:v",
            "libx264",
            "-tune",
            "stillimage",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            "-t",
            f"{dur:.3f}",
            "-vf",
            f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2",
            "-r",
            "30",
            str(out),
        ]
    )
    return out


def walkthrough_segment(video: Path, intro_mp3: Path, out: Path) -> Path:
    vdur = probe_duration(video)
    adur = probe_duration(intro_mp3)
    # Mix: play intro VO at start; keep walkthrough visuals for full length; pad silence after VO
    # If walkthrough shorter than needed, slow slightly; if longer, keep as-is with VO only at front.
    filter_complex = (
        f"[1:a]apad=whole_dur={vdur:.3f}[a];"
        f"[0:v]scale={W}:{H}:force_original_aspect_ratio=decrease,"
        f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,fps=30,setsar=1[v]"
    )
    run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video),
            "-i",
            str(intro_mp3),
            "-filter_complex",
            filter_complex,
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            "-t",
            f"{max(vdur, adur):.3f}",
            str(out),
        ]
    )
    return out


def concat(segments: list[Path], dest: Path) -> None:
    lst = WORK / "concat.txt"
    lines = []
    for s in segments:
        lines.append(f"file '{s}'")
    lst.write_text("\n".join(lines) + "\n")
    run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(lst),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(dest),
        ]
    )


def main() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    segments: list[Path] = []

    # Slides 1–9, then walkthrough, then 10–11
    walk_insert_after = 9  # after About slide

    for i, slide in enumerate(SCRIPT["slides"], start=1):
        png = SLIDES / f"{i:02d}-{slide['id']}.png"
        mp3 = AUDIO / f"{i:02d}-{slide['id']}.mp3"
        if not png.is_file() or not mp3.is_file():
            raise SystemExit(f"missing {png} or {mp3}")
        seg = WORK / f"seg-{i:02d}.mp4"
        slide_segment(png, mp3, seg)
        segments.append(seg)
        if i == walk_insert_after:
            walk = ART / "spacex-demo-usage-walkthrough.mp4"
            intro = AUDIO / "00-walkthrough-intro.mp3"
            if walk.is_file() and intro.is_file():
                wseg = WORK / "seg-walkthrough.mp4"
                walkthrough_segment(walk, intro, wseg)
                segments.append(wseg)
            else:
                print("WARN: walkthrough missing, skipping insert", walk)

    dest = ART / "Project_Supernova_SpaceX_Pitch_voiceover.mp4"
    concat(segments, dest)
    # also copy into repo
    repo = ROOT / "Project_Supernova_SpaceX_Pitch_voiceover.mp4"
    repo.write_bytes(dest.read_bytes())
    print("video", dest, "duration", probe_duration(dest))


if __name__ == "__main__":
    main()
