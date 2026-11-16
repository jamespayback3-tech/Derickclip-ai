import os, uuid, re, json, subprocess, shutil
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_from_directory, url_for
from werkzeug.utils import secure_filename

BASE = Path(__file__).resolve().parent
UPLOADS = BASE / "uploads"
OUTPUTS = BASE / "outputs"
UPLOADS.mkdir(exist_ok=True)
OUTPUTS.mkdir(exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024
ALLOWED = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}

def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout or "Command failed")[-2500:])
    return p.stdout

def duration_of(path):
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "default=noprint_wrappers=1:nokey=1", str(path)])
    return float(out.strip())

def transcribe(path):
    # Local, open-source speech recognition. First run downloads the tiny model.
    from faster_whisper import WhisperModel
    model = WhisperModel("tiny", device="cpu", compute_type="int8")
    segments, info = model.transcribe(str(path), vad_filter=True, word_timestamps=False)
    return [{"start": float(s.start), "end": float(s.end), "text": s.text.strip()}
            for s in segments if s.text.strip()]

def choose_moments(segments, total_duration, max_clips=5, clip_len=35):
    if not segments:
        # If no speech is detected, create evenly spaced sample clips.
        starts = [max(0, min(total_duration-clip_len, i*(total_duration-clip_len)/max(1,max_clips-1)))
                  for i in range(min(max_clips, max(1, int(total_duration // max(clip_len, 1)))))]
        return [{"start": s, "end": min(total_duration, s+clip_len), "title": f"Moment {i+1}"}
                for i, s in enumerate(starts)]

    keywords = {
        "important": 2.2, "secret": 2.0, "never": 1.4, "always": 1.2,
        "amazing": 1.8, "crazy": 1.8, "shocking": 2.2, "best": 1.3,
        "worst": 1.3, "why": 0.8, "how": 0.8, "because": 0.7,
        "money": 1.1, "win": 1.1, "fail": 1.4, "wrong": 1.2,
        "truth": 1.5, "believe": 0.8, "problem": 0.9, "solution": 1.0
    }
    scored = []
    for seg in segments:
        text = seg["text"].lower()
        words = re.findall(r"[a-z']+", text)
        score = min(len(words), 24) / 12
        score += sum(weight for word, weight in keywords.items()
                     if re.search(r"\b" + re.escape(word) + r"\b", text))
        score += 0.7 if "?" in seg["text"] else 0
        score += 0.8 if "!" in seg["text"] else 0
        if len(words) >= 5:
            scored.append((score, seg["start"], seg["end"], seg["text"]))

    if not scored:
        scored = [(1, s["start"], s["end"], s["text"]) for s in segments]

    # Select high-scoring moments while keeping clips reasonably separated.
    scored.sort(reverse=True)
    selected = []
    half = clip_len / 2
    for score, start, end, text in scored:
        center = (start + end) / 2
        a = max(0, center-half)
        b = min(total_duration, a+clip_len)
        a = max(0, b-clip_len)
        if b-a < 4:
            continue
        if any(abs(center - ((x["start"]+x["end"])/2)) < clip_len*0.75 for x in selected):
            continue
        selected.append({"start": a, "end": b, "title": " ".join(text.split()[:8])})
        if len(selected) >= max_clips:
            break
    selected.sort(key=lambda x: x["start"])
    return selected

def make_srt(segments, start, end, output_path):
    def stamp(sec):
        ms = int(round(sec * 1000))
        h, ms = divmod(ms, 3600000)
        m, ms = divmod(ms, 60000)
        s, ms = divmod(ms, 1000)
        return f"{h:02}:{m:02}:{s:02},{ms:03}"
    lines, idx = [], 1
    for seg in segments:
        a, b = max(seg["start"], start), min(seg["end"], end)
        if b <= a:
            continue
        lines += [str(idx), f"{stamp(a-start)} --> {stamp(b-start)}", seg["text"], ""]
        idx += 1
    output_path.write_text("\n".join(lines), encoding="utf-8")

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/clip", methods=["POST"])
def create_clips():
    file = request.files.get("video")
    if not file or not file.filename:
        return jsonify(error="Choose a video file first."), 400
    ext = Path(secure_filename(file.filename)).suffix.lower()
    if ext not in ALLOWED:
        return jsonify(error="Supported formats: MP4, MOV, MKV, WEBM and M4V."), 400

    job = uuid.uuid4().hex[:10]
    source = UPLOADS / f"{job}{ext}"
    file.save(source)

    try:
        total = duration_of(source)
        if total < 5:
            raise ValueError("Video is too short. Upload a video at least 5 seconds long.")
        segments = transcribe(source)
        moments = choose_moments(segments, total, max_clips=5, clip_len=35)
        if not moments:
            raise ValueError("Could not identify suitable moments in this video.")

        results = []
        for i, moment in enumerate(moments, 1):
            out_name = f"{job}_clip_{i}.mp4"
            out_path = OUTPUTS / out_name
            length = moment["end"] - moment["start"]
            # Vertical 9:16 centre crop; audio is retained when present.
            vf = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
            run(["ffmpeg", "-y", "-ss", str(moment["start"]), "-i", str(source),
                 "-t", str(length), "-vf", vf, "-c:v", "libx264", "-preset", "veryfast",
                 "-crf", "23", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
                 str(out_path)])
            srt_name = f"{job}_clip_{i}.srt"
            make_srt(segments, moment["start"], moment["end"], OUTPUTS / srt_name)
            results.append({
                "title": moment["title"] or f"Clip {i}",
                "start": round(moment["start"], 1),
                "end": round(moment["end"], 1),
                "video": url_for("download_file", filename=out_name),
                "captions": url_for("download_file", filename=srt_name)
            })
        return jsonify(clips=results, note="AI-selected moments are suggestions. Review clips before publishing.")
    except Exception as e:
        return jsonify(error=str(e)), 500
    finally:
        try:
            source.unlink(missing_ok=True)
        except Exception:
            pass

@app.route("/downloads/<path:filename>")
def download_file(filename):
    return send_from_directory(OUTPUTS, filename, as_attachment=True)

@app.errorhandler(413)
def too_large(_):
    return jsonify(error="File is too large. Maximum upload size is 500 MB."), 413

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
