import logging
import os
import sys
import threading
import time
import uuid
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_file, send_from_directory

from keyword_engine import generate_keywords
from media_pipeline import (
    DEFAULT_ORIENTATION,
    ClipMergeError,
    PexelsClient,
    VideoBuilder,
    normalize_orientation,
    orientation_label,
)


BASE_DIR = Path(__file__).resolve().parent
TEMP_DIR = BASE_DIR / "static" / "temp"
OUTPUT_DIR = BASE_DIR / "static" / "output"
ENV_PATH = BASE_DIR / ".env"

load_dotenv(ENV_PATH)

if os.getenv("CLIPMERGE_DEBUG", "").lower() in {"1", "true", "yes", "on"}:
    log_level = logging.DEBUG
else:
    log_level = logging.INFO

logging.basicConfig(level=log_level, format="%(levelname)s:%(name)s:%(message)s", stream=sys.stdout, force=True)

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.logger.setLevel(log_level)
app.logger.propagate = True
app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

jobs = {}
jobs_lock = threading.Lock()


def api_key():
    value = os.getenv("PEXELS_API_KEY", "").strip()
    if not value or value == "YOUR_API_KEY_HERE":
        return None
    return value


def update_job(job_id, **changes):
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            app.logger.warning("Attempted to update missing job %s with %s", job_id, changes)
            return
        job.update(changes)
        job["updated_at"] = time.time()
        app.logger.info("Updated job %s: %s", job_id, {key: job.get(key) for key in ("state", "status", "progress", "error") if key in job})


def public_job(job):
    return {
        "job_id": job["job_id"],
        "state": job["state"],
        "status": job["status"],
        "progress": job["progress"],
        "video_url": job.get("video_url"),
        "download_url": job.get("download_url"),
        "orientation": job.get("orientation", DEFAULT_ORIENTATION),
        "fallback_used": job.get("fallback_used", False),
        "keywords": job.get("keywords", []),
        "sources": job.get("sources", []),
        "error": job.get("error"),
    }


def validate_payload(data):
    prompt = str(data.get("prompt", "")).strip()

    try:
        duration = float(data.get("duration", 0))
    except (TypeError, ValueError):
        duration = 0

    if len(prompt) < 8:
        raise ClipMergeError("Enter a more descriptive prompt.")

    orientation = normalize_orientation(data.get("orientation", DEFAULT_ORIENTATION))

    if duration < 1 or duration > 600:
        raise ClipMergeError("Enter a video length between 1 and 600 seconds.")

    return prompt, duration, orientation


def run_generation_job(job_id, prompt, duration, orientation):
    app.logger.info("Starting background generation job %s for prompt=%r duration=%s orientation=%s", job_id, prompt, duration, orientation)
    try:
        def progress(message, value):
            update_job(job_id, status=message, progress=max(0, min(100, int(value))))

        progress("Generating keywords...", 6)
        keywords = generate_keywords(prompt)
        app.logger.info("Job %s generated keywords: %s", job_id, keywords)
        update_job(job_id, keywords=keywords)

        progress("Searching Pexels...", 14)
        pexels = PexelsClient(api_key())
        app.logger.info("Job %s searching Pexels with %s queries", job_id, len(keywords))
        candidates, fallback_used = pexels.search_videos(keywords, duration, orientation, prompt=prompt)
        app.logger.info("Job %s received %s candidates (fallback_used=%s)", job_id, len(candidates), fallback_used)
        update_job(job_id, fallback_used=fallback_used)
        fallback_notice = ""
        if fallback_used:
            fallback_notice = (
                f"Pexels had limited {orientation_label(orientation)} results, "
                "so suitable fallback clips were used."
            )
            progress(fallback_notice, 18)

        progress("Downloading clips...", 22)
        builder = VideoBuilder(TEMP_DIR, OUTPUT_DIR)
        app.logger.info("Job %s starting clip download/build pipeline with %s candidates", job_id, len(candidates))
        output_path, selected = builder.build(candidates, duration, job_id, orientation, progress)
        app.logger.info("Job %s finished build: output=%s selected=%s", job_id, output_path, [(item.video_id, item.query) for item in selected])

        video_url = f"/static/output/{output_path.name}?v={int(time.time())}"
        download_url = f"/api/download/{job_id}"
        sources = [
            {
                "id": item.video_id,
                "url": item.source_url,
                "photographer": item.photographer,
                "query": item.query,
            }
            for item in selected[:12]
        ]
        status = "Finished."
        if fallback_notice:
            status = f"Finished. {fallback_notice}"

        update_job(
            job_id,
            state="finished",
            status=status,
            progress=100,
            video_url=video_url,
            download_url=download_url,
            output_path=str(output_path),
            sources=sources,
        )
        app.logger.info("Job %s finished successfully", job_id)
    except ClipMergeError as exc:
        app.logger.exception("Generation job %s failed with ClipMergeError", job_id)
        update_job(
            job_id,
            state="error",
            status=exc.message,
            error=exc.message,
            detail=exc.detail,
        )
    except Exception as exc:
        app.logger.exception("Generation job %s failed with an unexpected exception", job_id)
        update_job(
            job_id,
            state="error",
            status="An unexpected error occurred while creating the video.",
            error="An unexpected error occurred while creating the video.",
            detail=str(exc),
        )


def cleanup_old_jobs(max_age_seconds=1 * 60 * 60):
    now = time.time()
    with jobs_lock:
        stale_ids = [
            job_id for job_id, job in jobs.items()
            if now - job.get("created_at", now) > max_age_seconds
        ]
        for job_id in stale_ids:
            jobs.pop(job_id, None)
        if stale_ids:
            app.logger.info("Cleaned up %s stale jobs", len(stale_ids))


@app.route("/")
def home():
    return send_from_directory(BASE_DIR, "index.html")


@app.route("/index.html")
def index_html():
    return send_from_directory(BASE_DIR, "index.html")


@app.route("/style.css")
def style_css():
    return send_from_directory(BASE_DIR, "style.css")


@app.route("/script.js")
def script_js():
    return send_from_directory(BASE_DIR, "script.js")


@app.route("/about/about.html")
def about_html():
    return send_from_directory(BASE_DIR / "about", "about.html")


@app.route("/about/about.css")
def about_css():
    return send_from_directory(BASE_DIR / "about", "about.css")


@app.route("/about/about.js")
def about_js():
    return send_from_directory(BASE_DIR / "about", "about.js")


@app.route("/api/generate", methods=["POST"])
def generate():
    try:
        cleanup_old_jobs()
        data = request.get_json(silent=True) or {}

        try:
            prompt, duration, orientation = validate_payload(data)
        except ClipMergeError as exc:
            return jsonify({"error": exc.message}), 400

        if not api_key():
            return jsonify({"error": "Missing Pexels API key. Add it to .env as PEXELS_API_KEY."}), 400

        if not VideoBuilder.ffmpeg_available():
            return jsonify({"error": "FFmpeg is not installed or is not available on PATH."}), 400

        job_id = uuid.uuid4().hex
        job = {
            "job_id": job_id,
            "state": "running",
            "status": "Generating keywords...",
            "progress": 3,
            "created_at": time.time(),
            "updated_at": time.time(),
            "orientation": orientation,
            "fallback_used": False,
            "keywords": [],
            "sources": [],
        }

        with jobs_lock:
            jobs[job_id] = job

        app.logger.info("Created job %s with initial state=%s status=%s", job_id, job["state"], job["status"])
        thread = threading.Thread(
            target=run_generation_job,
            args=(job_id, prompt, duration, orientation),
            daemon=True,
        )
        thread.start()

        return jsonify(public_job(job)), 202
    except Exception:
        app.logger.exception("Failed to start generation job")
        return jsonify({"error": "An unexpected error occurred while starting video generation."}), 500


@app.route("/api/status/<job_id>")
def job_status(job_id):
    try:
        with jobs_lock:
            job = jobs.get(job_id)

        app.logger.info("Status request for job %s -> %s", job_id, job.get("state") if job else "missing")
        if not job:
            return jsonify({"error": "Generation job was not found."}), 404

        return jsonify(public_job(job))
    except Exception:
        app.logger.exception("Failed to retrieve status for job %s", job_id)
        return jsonify({"error": "An unexpected error occurred while retrieving the job status."}), 500


@app.route("/api/download/<job_id>")
def download(job_id):
    try:
        with jobs_lock:
            job = jobs.get(job_id)

        if not job or job.get("state") != "finished" or not job.get("output_path"):
            return jsonify({"error": "The requested video is not ready for download."}), 404

        output_path = Path(job["output_path"])
        if not output_path.exists():
            return jsonify({"error": "The generated MP4 is no longer available."}), 404

        return send_file(
            output_path,
            mimetype="video/mp4",
            as_attachment=True,
            download_name=output_path.name,
        )
    except Exception:
        app.logger.exception("Failed to download output for job %s", job_id)
        return jsonify({"error": "An unexpected error occurred while preparing the download."}), 500


@app.route("/api/health")
def health():
    try:
        return jsonify({
            "ok": True,
            "pexels_api_key": bool(api_key()),
            "ffmpeg": VideoBuilder.ffmpeg_available(),
        })
    except Exception:
        app.logger.exception("Health check failed")
        return jsonify({"error": "Health check failed."}), 500


if __name__ == "__main__":
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=os.environ.get("FLASK_DEBUG", "false").lower() in {"1", "true", "yes", "on"},
        threaded=True,
    )
