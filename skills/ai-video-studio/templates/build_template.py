#!/usr/bin/env python3
"""
Centralized montage build (copy & adapt per project).
Usage: edit BASE/CLIPS/TOTAL_DURATION, then python3 build.py

Each rebuild:
1. Extract video segments (no audio) and SFX
2. Concat all segments
3. Pre-mix each SFX with its delay into full-duration silent tracks
4. Final mix: music + SFX
5. Verify audio levels per span
6. Clean temp files
"""
import subprocess
import os
import sys
import glob

BASE = "/root/workspace/<project>"          # EDIT
VIDEOS = os.path.join(BASE, "videos")
MUSIC = os.path.join(BASE, "music")

TOTAL_DURATION = 270.0                       # exact seconds (EDIT)
OUTPUT_NAME = "project_final_v1.mp4"         # EDIT

# Each clip: {seg, src, start, dur, sfx}
# - seg: segment file name
# - src: source file in videos/ (or a .png for the still)
# - start: offset in the source
# - dur: segment duration (0 for the still — computed automatically)
# - sfx: None, or {"delay": seconds, "vol": dB}
# IMPORTANT: the still is ALWAYS the LAST element with src ending ".png".
CLIPS = [
    {"seg": "_seg1",  "src": "clip1.mp4", "start": 0,   "dur": 12.0,  "sfx": None},
    {"seg": "_seg2",  "src": "clip2.mp4", "start": 3,   "dur": 7.0,   "sfx": {"delay": 46.0, "vol": 4}},
    {"seg": "_seg3",  "src": "clip3.mp4", "start": 0,   "dur": 6.0,   "sfx": {"delay": 53.0, "vol": -2}},
    # ... more clips ...
    {"seg": "_seg_still", "src": "final_ref.png", "start": 0, "dur": 0, "sfx": None},
]

def run(cmd, description=""):
    print(f"  > {description}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ERROR: {result.stderr[-500:]}")
        sys.exit(1)
    return result

def extract_segments():
    print("\n[1] Extracting segments...")
    sfx_count = 0
    for i, clip in enumerate(CLIPS):
        src_path = os.path.join(VIDEOS, clip["src"])
        if clip["src"].endswith(".png"):
            continue  # still generated later
        seg_path = os.path.join(VIDEOS, clip["seg"])
        run(
            f'ffmpeg -y -i "{src_path}" -ss {clip["start"]} -t {clip["dur"]} '
            f'-an -c:v libx264 -pix_fmt yuv420p "{seg_path}.mp4"',
            f"Clip {i+1}: {clip['src'][:30]}...",
        )
        if clip["sfx"]:
            sfx_count += 1
            sfx_path = os.path.join(VIDEOS, f"_sfx{sfx_count}.wav")
            run(
                f'ffmpeg -y -i "{src_path}" -ss {clip["start"]} -t {clip["dur"]} '
                f'-vn -acodec pcm_s16le -ar 48000 "{sfx_path}"',
                f"SFX {sfx_count}: delay={clip['sfx']['delay']}s, vol={clip['sfx']['vol']}dB",
            )
            clip["sfx_file"] = f"_sfx{sfx_count}.wav"
    return sfx_count

def create_concat_list():
    concat_path = os.path.join(VIDEOS, "_concat_list.txt")
    with open(concat_path, "w") as f:
        for clip in CLIPS:
            f.write(f"file '{clip['seg']}.mp4'\n")
    return concat_path

def concat_video(concat_path):
    print("\n[2] Concatenating video...")
    output = os.path.join(VIDEOS, "_full_concat.mp4")
    run(
        f'ffmpeg -y -f concat -safe 0 -i "{concat_path}" '
        f'-c:v libx264 -pix_fmt yuv420p "{output}"',
        "Concat all segments",
    )
    return output

def create_still(image_path, duration):
    print(f"\n[3] Still ({duration:.1f}s)...")
    still_path = os.path.join(VIDEOS, "_seg_still.mp4")
    run(
        f'ffmpeg -y -loop 1 -i "{image_path}" -t {duration} '
        f'-c:v libx264 -pix_fmt yuv420p -r 24 "{still_path}"',
        f"Still {duration:.1f}s",
    )
    return still_path

def build_sfx_track():
    """One full-duration silent track per delayed SFX, then one merge."""
    print("\n[4] Building SFX track...")
    sfx_clips = [c for c in CLIPS if c.get("sfx") and c.get("sfx_file")]
    if not sfx_clips:
        print("  (no SFX configured)")
        return None
    for clip in sfx_clips:
        sfx_path = os.path.join(VIDEOS, clip["sfx_file"])
        delay_ms = int(clip["sfx"]["delay"] * 1000)
        vol = clip["sfx"]["vol"]
        delayed_path = os.path.join(VIDEOS, clip["sfx_file"].replace(".wav", "_delayed.wav"))
        filter_str = (
            f"[1:a]adelay={delay_ms}|{delay_ms},volume={vol}dB[a_sfx];"
            f"[0:a][a_sfx]amix=inputs=2:duration=first:normalize=0"
        )
        run(
            f'ffmpeg -y '
            f'-f lavfi -i "anullsrc=r=48000:cl=stereo:d={TOTAL_DURATION}" '
            f'-i "{sfx_path}" '
            f'-filter_complex "{filter_str}" '
            f'-c:a pcm_s16le "{delayed_path}"',
            f"Delay SFX: {clip['sfx_file']} @ {clip['sfx']['delay']}s",
        )
    sfx_delayed_files = [
        os.path.join(VIDEOS, c["sfx_file"].replace(".wav", "_delayed.wav")) for c in sfx_clips
    ]
    inputs = " ".join([f'-i "{f}"' for f in sfx_delayed_files])
    filter_parts = "".join([f"[{i}:a]" for i in range(len(sfx_delayed_files))])
    sfx_merged = os.path.join(VIDEOS, "_sfx_merged.wav")
    run(
        f'ffmpeg -y {inputs} '
        f'-filter_complex "{filter_parts}amix=inputs={len(sfx_delayed_files)}:duration=first:normalize=0" '
        f'-c:a pcm_s16le "{sfx_merged}"',
        f"Merge {len(sfx_delayed_files)} delayed SFX into one track",
    )
    return sfx_merged

def final_mix(video_path, music_path, sfx_path):
    print("\n[5] Final mix (video + music + SFX)...")
    output_path = os.path.join(VIDEOS, OUTPUT_NAME)
    if sfx_path:
        filter_str = (
            "[1:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[a_music];"
            "[2:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[a_sfx];"
            "[a_music][a_sfx]amix=inputs=2:duration=first:normalize=0[audio_out]"
        )
        audio_inputs = f'-i "{music_path}" -i "{sfx_path}"'
    else:
        filter_str = "[1:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[audio_out]"
        audio_inputs = f'-i "{music_path}"'
    run(
        f'ffmpeg -y -i "{video_path}" {audio_inputs} '
        f'-filter_complex "{filter_str}" '
        f'-map "0:v" -map "[audio_out]" '
        f'-c:v libx264 -pix_fmt yuv420p -c:a aac -b:a 192k '
        f'-t {TOTAL_DURATION} -movflags +faststart "{output_path}"',
        "Render final with audio",
    )
    return output_path

def verify(output_path):
    print("\n[6] Verification:")
    result = subprocess.run(
        f'ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "{output_path}"',
        shell=True, capture_output=True, text=True)
    duration = float(result.stdout.strip())
    print(f"  Duration: {duration:.2f}s (target {TOTAL_DURATION}s)")
    result = subprocess.run(
        f'ffprobe -v error -show_entries stream=codec_name,width,height -of default "{output_path}"',
        shell=True, capture_output=True, text=True)
    print(f"  Streams:\n{result.stdout}")
    print("  Audio levels:")
    for t in [0, 30, 60, 90, 120, 180, 240, 260]:
        result = subprocess.run(
            f'ffmpeg -ss {t} -t 5 -i "{output_path}" -af volumedetect -f null -',
            shell=True, capture_output=True, text=True)
        for line in result.stderr.split("\n"):
            if "mean_volume" in line:
                print(f"    t={t:3d}s: {line.split('mean_volume:')[1].strip()}")
                break
    print(f"  Size: {os.path.getsize(output_path) / 1024 / 1024:.1f} MB")
    return duration

def cleanup_temp():
    print("\n[7] Cleaning temp files...")
    for pattern in [
        os.path.join(VIDEOS, "_sfx*_delayed.wav"),
        os.path.join(VIDEOS, "_sfx_merged.wav"),
        os.path.join(VIDEOS, "_concat_list.txt"),
    ]:
        for f in glob.glob(pattern):
            try:
                os.remove(f)
                print(f"  Removed: {os.path.basename(f)}")
            except OSError:
                pass

def main():
    print("=" * 60)
    print("Montaje — build system")
    print("=" * 60)
    clip_duration = sum(c["dur"] for c in CLIPS if not c["src"].endswith(".png"))
    still_duration = TOTAL_DURATION - clip_duration
    print(f"Clips: {len(CLIPS)} | clip time: {clip_duration:.2f}s | still: {still_duration:.2f}s")
    sfx_count = extract_segments()
    still_clip = CLIPS[-1]
    assert still_clip["src"].endswith(".png"), "last CLIPS entry must be the still (.png)"
    create_still(os.path.join(BASE, still_clip.get("still_dir", ""), still_clip["src"]).replace("//", "/"), still_duration)
    still_clip["dur"] = still_duration
    full_video = concat_video(create_concat_list())
    sfx_track = build_sfx_track()
    music_path = os.path.join(MUSIC, sorted(os.listdir(MUSIC))[-1])  # EDIT: pick your song
    output = final_mix(full_video, music_path, sfx_track)
    verify(output)
    cleanup_temp()
    print(f"\nBUILD DONE: {output}")

if __name__ == "__main__":
    main()
