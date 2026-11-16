# DerickClip AI

A free, self-hostable video clipping web app.

## What it does
- Optional YouTube URL preview (does not download YouTube videos).
- Upload a video file you own or have permission to edit.
- Uses Faster-Whisper locally to transcribe speech.
- Scores transcript segments heuristically to suggest up to five moments.
- Uses FFmpeg to render 9:16 vertical MP4 clips.
- Exports SRT subtitles separately.

## Requirements
- Python 3.10+
- FFmpeg and ffprobe installed and available on PATH.
- Internet on first run to download the Whisper `tiny` model.

## Run locally
### Windows
1. Install Python and FFmpeg.
2. Open terminal in this folder.
3. Run `pip install -r requirements.txt`
4. Run `python app.py`
5. Open `http://127.0.0.1:5000`

### Linux / macOS
Install FFmpeg using your package manager, then follow the same pip and run steps.

## Android
The easiest route is to push this folder to GitHub from a browser or Git client, then deploy it to a Python host. For local Android use, install Termux from F-Droid, install Python and FFmpeg, then install requirements and run `python app.py`. Model installation and video processing can be slow on a phone.

## Free hosting caveats
Free hosting plans may sleep, have low RAM/CPU, impose request timeouts, and erase local files when the service restarts. Whisper and FFmpeg are resource-intensive. A free hosted instance may fail on long or large videos. For reliable free use, run locally in Termux on your phone or on your own computer. Do not upload private videos to a public service.

## Limitations
- AI moment selection is transcript-based heuristic scoring, not a human-level editor.
- The current version crops the centre of the frame; it does not track faces.
- Subtitles are downloaded as SRT files and are not burned into the MP4.
- No arbitrary YouTube downloading is implemented. Use your original video file or a file you are authorized to edit.
- This starter version stores generated files on the server and has no user accounts or persistent cloud storage.
