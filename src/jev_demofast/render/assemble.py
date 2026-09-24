"""Frames (and optional narration clips) → MP4, optionally a GIF.

Port of our earlier demo kit's assemble.py (same frames.json contract). Each narration clip NN plays over segment NN; a segment whose clip
runs longer than its footage holds its first frame longer, so no sentence is cut off. Long waits are trimmed.
"""
import glob
import json
import os
import subprocess

LEAD, TAIL = 0.35, 0.6  # seconds of quiet before and after each narration line
PENDING_FRAMES_KEPT = 3
MUSIC_UNDER_VOICE, MUSIC_ALONE = 0.4, 0.6  # background music level with and without narration
MUSIC_FADE_IN, MUSIC_FADE_OUT = 0.6, 2.0
MUSIC_INTRO, MUSIC_OUTRO = 2.0, 2.0  # seconds of music alone before the first line and after the last
VOICE_LUFS, VOICE_OVER_MUSIC_LUFS = -16, -19  # narration loudness alone, and softer when it sits in music


def media_length(path):
    out = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path])
    return float(out.strip())


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True)


def segments(frames):
    """Group frames by segment, keeping only the first few frames of a long wait (plus its last)."""
    grouped = []
    for frame in frames:
        if not grouped or grouped[-1][0] != frame["segment"]:
            grouped.append((frame["segment"], []))
        grouped[-1][1].append(dict(frame))
    trimmed = []
    for name, seg in grouped:
        pending = [f for f in seg if f["pending"]]
        drop = {id(f) for f in pending[PENDING_FRAMES_KEPT:-1]}
        trimmed.append((name, [f for f in seg if id(f) not in drop]))
    return trimmed


def stretch(seg, need):
    """Make a step's footage last as long as its narration line by holding its LAST frame, the step's outcome
    (a confirmation, or an error message), so the screen shows what the narrator is describing."""
    visual = sum(f["hold"] for f in seg)
    if need > visual:
        seg[-1]["hold"] += need - visual


def music_filter(total, narration_input, music_input):
    """ffmpeg filter graph ending in [a]: the music looped to the video's length, faded in and out, and ducked under
    the narration (sidechain compression) when there is one."""
    fades = (f"atrim=0:{total:.2f},afade=t=in:d={MUSIC_FADE_IN},"
             f"afade=t=out:st={max(0.0, total - MUSIC_FADE_OUT):.2f}:d={MUSIC_FADE_OUT}")
    if narration_input is None:
        return f"[{music_input}:a]{fades},volume={MUSIC_ALONE}[a]"
    return (f"[{music_input}:a]{fades},volume={MUSIC_UNDER_VOICE},aresample=48000[m];"
            f"[{narration_input}:a]loudnorm=I={VOICE_OVER_MUSIC_LUFS}:TP=-2:LRA=11,aresample=48000,asplit[n][key];"
            f"[m][key]sidechaincompress=threshold=0.03:ratio=2.5:attack=30:release=600[ducked];"
            f"[n][ducked]amix=inputs=2:duration=first:normalize=0[a]")


def music_bookends(frames):
    """Hold the first and last frames longer, so the music plays alone before the narrator starts and after they end."""
    frames[0]["hold"] += MUSIC_INTRO
    frames[-1]["hold"] += MUSIC_OUTRO


def silence(path, seconds):
    ffmpeg("-f", "lavfi", "-i", f"anullsrc=r=48000:cl=stereo", "-t", f"{seconds:.3f}", path)
    return path


def clip_files(folder):
    return sorted(glob.glob(os.path.join(folder, "[0-9][0-9].mp3")) + glob.glob(os.path.join(folder, "[0-9][0-9].aiff")))


def assemble(work, output, clips_dir=None, gif=False, music=None, log=print):
    work, output = os.path.abspath(work), os.path.abspath(output)
    with open(os.path.join(work, "frames.json")) as f:
        segs = segments(json.load(f))
    clips = clip_files(clips_dir) if clips_dir else []
    if clips_dir and len(clips) != len(segs):
        raise SystemExit(f"{len(clips)} narration clips for {len(segs)} segments; narration needs one line per segment")
    concat, padded = [], []
    audio_dir = os.path.join(work, "audio")
    os.makedirs(audio_dir, exist_ok=True)
    for n, (name, seg) in enumerate(segs):
        if clips:
            need = LEAD + media_length(clips[n]) + TAIL
            stretch(seg, need)
            total = sum(f["hold"] for f in seg)
            wav = os.path.join(audio_dir, f"s{n:02d}.wav")
            ffmpeg("-i", clips[n], "-af", f"adelay={int(LEAD * 1000)}:all=1,apad,atrim=0:{total:.3f},aresample=48000", "-ac", "2", wav)
            padded.append(wav)
        concat.extend(seg)
    if music and padded:
        music_bookends(concat)
        padded = [silence(os.path.join(audio_dir, "intro.wav"), MUSIC_INTRO), *padded,
                  silence(os.path.join(audio_dir, "outro.wav"), MUSIC_OUTRO)]
    frame_list = os.path.join(work, "concat.txt")
    with open(frame_list, "w") as f:
        for frame in concat:
            f.write(f"file '{frame['path']}'\nduration {frame['hold']:.3f}\n")
        f.write(f"file '{concat[-1]['path']}'\n")
    video = ["-f", "concat", "-safe", "0", "-i", frame_list]
    encode = ["-vf", "scale=1920:-2:flags=lanczos,fps=30,format=yuv420p", "-c:v", "libx264", "-crf", "20", "-preset", "slow"]
    aac = ["-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-shortest", "-movflags", "+faststart"]
    os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
    total = sum(f["hold"] for f in concat)
    narration = None
    if padded:
        audio_list = os.path.join(work, "audio.txt")
        with open(audio_list, "w") as f:
            f.writelines(f"file '{p}'\n" for p in padded)
        narration = os.path.join(work, "narration.wav")
        ffmpeg("-f", "concat", "-safe", "0", "-i", audio_list, "-c:a", "pcm_s16le", narration)
    if music:
        loop = ["-stream_loop", "-1", "-i", os.path.abspath(music)]
        if narration:
            ffmpeg(*video, "-i", narration, *loop, *encode, "-filter_complex", music_filter(total, 1, 2),
                   "-map", "0:v", "-map", "[a]", *aac, output)
        else:
            ffmpeg(*video, *loop, *encode, "-filter_complex", music_filter(total, None, 1),
                   "-map", "0:v", "-map", "[a]", *aac, output)
    elif narration:
        ffmpeg(*video, "-i", narration, *encode, "-af", f"loudnorm=I={VOICE_LUFS}:TP=-1.5:LRA=11", *aac, output)
    else:
        ffmpeg(*video, *encode, "-movflags", "+faststart", output)
    log(f"video {media_length(output):.1f}s → {output}")
    if gif:
        path = os.path.splitext(output)[0] + ".gif"
        ffmpeg(*video, "-vf", "fps=6,scale=1100:-2:flags=lanczos,split[a][b];[a]palettegen=max_colors=192[p];"
                              "[b][p]paletteuse=dither=bayer:bayer_scale=4", path)
        log(f"gif → {path}")
    return output
