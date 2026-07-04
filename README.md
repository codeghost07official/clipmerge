# ClipMerge

ClipMerge is a Flask web app that creates a stock-footage MP4 from a text prompt. It generates search keywords locally in Python, searches Pexels videos, downloads suitable clips, trims and normalizes them with FFmpeg, merges them into one MP4, and displays the result in the browser.

## Requirements

- Python 3.10+
- FFmpeg installed separately and available on your `PATH`
- A Pexels API key

FFmpeg is not a Python package, so it cannot be installed from `requirements.txt`. If FFmpeg is missing, ClipMerge shows a clear error in the web interface and `/api/health`.

## Setup

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Open `.env` and replace the placeholder:

```env
PEXELS_API_KEY=YOUR_API_KEY_HERE
```

4. Run the Flask server:

```bash
python main.py
```

5. Open:

```text
http://127.0.0.1:5000
```

## Usage

Enter a descriptive prompt, choose the video length in seconds, and pick an orientation before clicking `Preview` or `Download MP4`.

The orientation dropdown defaults to Portrait (9:16) and can be switched to Landscape (16:9). The selected orientation is sent to the backend, used for Pexels search and FFmpeg processing, and respected by both preview and download output.

`Preview` generates a video and displays it in the page. `Download MP4` generates a video and starts a browser download when it is ready.

## Generated Files

Temporary downloads and processed segments are stored under `static/temp/` during generation and deleted after the job finishes. Final MP4 files are saved under `static/output/`.

## API

- `POST /api/generate` starts a background generation job.
- `GET /api/status/<job_id>` returns progress, status, and final video URLs.
- `GET /api/download/<job_id>` downloads the completed MP4.
- `GET /api/health` reports whether the API key and FFmpeg are available.

Videos are provided by Pexels. Follow the Pexels API terms and attribution requirements for your deployment.
