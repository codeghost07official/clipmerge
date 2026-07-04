import gc
import logging
import math
import random
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import requests

from keyword_engine import prompt_terms


LOGGER = logging.getLogger(__name__)

PEXELS_VIDEO_SEARCH_URL = "https://api.pexels.com/v1/videos/search"
TARGET_FPS = 24
MAX_SEGMENT_SECONDS = 8.0
DEFAULT_ORIENTATION = "portrait"
ORIENTATION_PRESETS = {
    "portrait": {
        "label": "Portrait (9:16)",
        "pexels": "portrait",
        "width": 720,
        "height": 1280,
    },
    "landscape": {
        "label": "Landscape (16:9)",
        "pexels": "landscape",
        "width": 1280,
        "height": 720,
    },
}


class ClipMergeError(Exception):
    def __init__(self, message, detail=None):
        super().__init__(message)
        self.message = message
        self.detail = detail


def normalize_orientation(value):
    orientation = str(value or DEFAULT_ORIENTATION).strip().lower()
    if orientation not in ORIENTATION_PRESETS:
        raise ClipMergeError("Choose a valid video orientation.")
    return orientation


def orientation_label(orientation):
    return ORIENTATION_PRESETS[orientation]["label"]


def target_size(orientation):
    preset = ORIENTATION_PRESETS[orientation]
    return preset["width"], preset["height"]


def score_candidate_relevance(candidate_terms, prompt_terms_input, prompt_terms_set=None):
    prompt_terms_value = prompt_terms_input
    if isinstance(prompt_terms_input, str):
        prompt_terms_value = {term for term in prompt_terms_input.split() if term and len(term) > 2}
    elif prompt_terms_input is None:
        prompt_terms_value = set()
    else:
        prompt_terms_value = {term for term in prompt_terms_input if term}

    if prompt_terms_set is not None:
        prompt_terms_value = set(prompt_terms_set)

    normalized_prompt_terms = {term.strip("'-").lower() for term in prompt_terms_value}
    if not normalized_prompt_terms:
        return 0.0

    normalized_candidate_terms = set()
    for term in candidate_terms if isinstance(candidate_terms, (list, tuple, set)) else [candidate_terms]:
        cleaned = str(term).strip("'-").lower()
        if cleaned:
            normalized_candidate_terms.add(cleaned)

    overlap = normalized_candidate_terms & normalized_prompt_terms
    score = len(overlap) * 4.0
    score += sum(1 for term in normalized_candidate_terms if term in normalized_prompt_terms and len(term) > 3)
    return score


@dataclass(frozen=True)
class VideoCandidate:
    video_id: int
    duration: float
    download_url: str
    source_url: str
    photographer: str
    query: str
    width: int
    height: int


@dataclass(frozen=True)
class DownloadedClip:
    candidate: VideoCandidate
    path: Path


class PexelsClient:
    def __init__(self, api_key):
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({"Authorization": api_key})
        self.rng = random.SystemRandom()

    def search_videos(self, keywords, target_duration, orientation, prompt=None):
        orientation = normalize_orientation(orientation)
        prompt_terms_set = set(prompt_terms(prompt or "")) if prompt else set()
        requested, failures = self._collect_videos(
            keywords,
            target_duration,
            request_orientation=orientation,
            preferred_orientation=orientation,
            prompt_terms_set=prompt_terms_set,
        )

        if self._has_enough_coverage(requested, target_duration):
            selected = self._rank_candidates(requested.values(), prompt_terms_set)
            return selected, False

        fallback, fallback_failures = self._collect_videos(
            keywords,
            target_duration,
            request_orientation=None,
            preferred_orientation=orientation,
            prompt_terms_set=prompt_terms_set,
        )
        candidates = {**requested, **fallback}
        failures.extend(fallback_failures)

        if not candidates:
            detail = "; ".join(failures[-3:]) if failures else None
            if failures:
                raise ClipMergeError("Pexels could not return usable video results. Please try again.", detail)
            raise ClipMergeError("No suitable Pexels videos were found for this prompt.", detail)

        selected = self._rank_candidates(candidates.values(), prompt_terms_set)
        return selected, True

    def _collect_videos(self, keywords, target_duration, request_orientation, preferred_orientation, prompt_terms_set):
        candidates = {}
        failures = []
        per_page = min(24, max(12, math.ceil(target_duration / 3)))

        for keyword in keywords:
            pages = [self.rng.randint(1, 3)]
            if pages[0] != 1:
                pages.append(1)

            for page in pages:
                params = {
                    "query": keyword,
                    "size": "small",
                    "per_page": per_page,
                    "page": page,
                    "locale": "en-US",
                }
                if request_orientation:
                    params["orientation"] = ORIENTATION_PRESETS[request_orientation]["pexels"]

                LOGGER.debug("Pexels search query=%s orientation=%s page=%s", keyword, request_orientation, page)
                try:
                    response = self.session.get(PEXELS_VIDEO_SEARCH_URL, params=params, timeout=20)
                except requests.RequestException as exc:
                    failures.append(str(exc))
                    continue

                if response.status_code in {401, 403}:
                    raise ClipMergeError("Your Pexels API key was rejected. Check the key in .env.")

                if response.status_code == 429:
                    raise ClipMergeError("Pexels rate limit reached. Please wait and try again.")

                if not response.ok:
                    failures.append(f"Pexels returned HTTP {response.status_code} for '{keyword}'.")
                    continue

                try:
                    data = response.json()
                except ValueError:
                    failures.append(f"Pexels returned an invalid response for '{keyword}'.")
                    continue

                videos = data.get("videos", [])
                LOGGER.info("Pexels query=%s page=%s returned %s results", keyword, page, len(videos))
                for video in videos:
                    candidate = self._candidate_from_video(video, keyword, preferred_orientation, prompt_terms_set)
                    if candidate:
                        candidates[candidate.video_id] = candidate

                if videos:
                    break

        return candidates, failures

    def _has_enough_coverage(self, candidates, target_duration):
        covered = 0.0
        max_clips = min(80, max(3, math.ceil(target_duration / MAX_SEGMENT_SECONDS) + 4))

        for candidate in list(candidates.values())[:max_clips]:
            covered += min(candidate.duration, MAX_SEGMENT_SECONDS)
            if covered >= target_duration * 0.8:
                return True

        return False

    def _rank_candidates(self, candidates, prompt_terms_set):
        ranked = sorted(candidates, key=lambda item: self._candidate_relevance_score(item, prompt_terms_set), reverse=True)
        if len(ranked) <= 1:
            return ranked

        top_candidates = [candidate for candidate in ranked if self._candidate_relevance_score(candidate, prompt_terms_set) > 0]
        if not top_candidates:
            top_candidates = ranked

        self.rng.shuffle(top_candidates)
        if len(top_candidates) > 6:
            top_candidates = top_candidates[:6]
        return top_candidates

    def _candidate_relevance_score(self, candidate, prompt_terms_set):
        if not prompt_terms_set:
            return 0.0

        candidate_terms = set()
        for term in candidate.query.split():
            cleaned = term.strip("'-").lower()
            if cleaned:
                candidate_terms.add(cleaned)

        score = score_candidate_relevance(candidate_terms, prompt_terms_set)
        title_terms = set()
        for term in (candidate.photographer or "").lower().split():
            cleaned = term.strip("'-").lower()
            if cleaned:
                title_terms.add(cleaned)
        score += 0.2 * len(title_terms & prompt_terms_set)
        return score

    def _candidate_from_video(self, video, query, preferred_orientation, prompt_terms_set):
        video_id = video.get("id")
        duration = float(video.get("duration") or 0)
        video_files = video.get("video_files") or []

        if not video_id or duration < 1 or not video_files:
            return None

        mp4_files = [
            item for item in video_files
            if item.get("file_type") == "video/mp4" and item.get("link")
            and int(item.get("width") or 0) > 0
            and int(item.get("height") or 0) > 0
        ]

        if not mp4_files:
            return None

        target_width, target_height = target_size(preferred_orientation)
        target_ratio = target_width / target_height

        def matches_orientation(item):
            width = int(item.get("width") or 0)
            height = int(item.get("height") or 0)
            return width < height if preferred_orientation == "portrait" else width >= height

        def file_score(item):
            width = int(item.get("width") or 0)
            height = int(item.get("height") or 0)
            ratio = width / height
            ratio_distance = abs(ratio - target_ratio)
            target_coverage = min(width / target_width, height / target_height)
            pixel_area = width * height
            return (
                matches_orientation(item),
                -ratio_distance,
                -pixel_area,
                target_coverage,
            )

        chosen_file = sorted(
            mp4_files,
            key=file_score,
            reverse=True,
        )[0]
        LOGGER.info("Selected file for video %s: width=%s height=%s url=%s", video_id, chosen_file.get("width"), chosen_file.get("height"), chosen_file.get("link"))
        width = int(chosen_file.get("width") or 0)
        height = int(chosen_file.get("height") or 0)

        candidate = VideoCandidate(
            video_id=int(video_id),
            duration=duration,
            download_url=chosen_file["link"],
            source_url=video.get("url", ""),
            photographer=video.get("user", {}).get("name", "Pexels creator"),
            query=query,
            width=width,
            height=height,
        )
        relevance = self._candidate_relevance_score(candidate, prompt_terms_set)
        if relevance > 0:
            LOGGER.debug("Candidate %s query=%s relevance=%s", candidate.video_id, query, relevance)
        return candidate


class VideoBuilder:
    def __init__(self, temp_dir, output_dir):
        self.temp_dir = Path(temp_dir)
        self.output_dir = Path(output_dir)
        self.rng = random.SystemRandom()
        self.ffmpeg_path = shutil.which("ffmpeg")

    @staticmethod
    def ffmpeg_available():
        return shutil.which("ffmpeg") is not None

    def build(self, candidates, duration, job_id, orientation, progress: Callable[[str, int], None]):
        if not self.ffmpeg_path:
            raise ClipMergeError("FFmpeg is not installed or is not available on PATH.")

        orientation = normalize_orientation(orientation)
        job_temp = self.temp_dir / job_id
        job_temp.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        try:
            selected = self._select_candidates(candidates, duration)
            LOGGER.info("Low-memory build started for job %s with %s selected clips and target %sx%s", job_id, len(selected), target_size(orientation)[0], target_size(orientation)[1])
            downloaded = self._download_clips(selected, job_temp, progress)
            output_path = self.output_dir / f"clipmerge_{job_id}.mp4"
            progress("Processing videos...", 60)
            self._assemble_video(downloaded, output_path, duration, orientation, job_temp, progress)
            progress("Preparing output...", 96)
            progress("Finished.", 100)
            return output_path, selected
        finally:
            shutil.rmtree(job_temp, ignore_errors=True)

    def _select_candidates(self, candidates, duration):
        ranked_candidates = list(candidates)
        self.rng.shuffle(ranked_candidates)
        selected = []
        covered = 0.0
        max_clips = min(80, max(3, math.ceil(duration / MAX_SEGMENT_SECONDS) + 4))

        for candidate in ranked_candidates:
            if candidate.video_id in {item.video_id for item in selected}:
                continue
            selected.append(candidate)
            covered += min(candidate.duration, MAX_SEGMENT_SECONDS)
            if covered >= duration + 0.5 or len(selected) >= max_clips:
                break

        if covered < duration * 0.8:
            raise ClipMergeError("Pexels did not return enough usable footage for that duration.")

        LOGGER.debug("Final clip selection: %s", [(item.video_id, item.query) for item in selected])
        return selected

    def _download_clips(self, candidates, job_temp, progress):
        downloaded = []
        total = len(candidates)

        for index, candidate in enumerate(candidates, start=1):
            progress(f"Downloading clips... ({index}/{total})", 22 + int((index - 1) / total * 28))
            target = job_temp / f"source_{index:03d}_{candidate.video_id}.mp4"

            try:
                LOGGER.info("Downloading clip %s/%s for video %s from %s", index, total, candidate.video_id, candidate.download_url)
                with requests.get(candidate.download_url, stream=True, timeout=(10, 90)) as response:
                    response.raise_for_status()
                    with target.open("wb") as file_handle:
                        for chunk in response.iter_content(chunk_size=1024 * 512):
                            if chunk:
                                file_handle.write(chunk)
                LOGGER.info("Saved clip %s/%s to %s (%s bytes)", index, total, target, target.stat().st_size)
            except requests.RequestException as exc:
                LOGGER.exception("Clip download failed for video %s", candidate.video_id)
                raise ClipMergeError("A stock clip could not be downloaded. Please try again.", str(exc))

            if target.stat().st_size < 1024:
                LOGGER.error("Downloaded clip %s was empty or invalid at %s", candidate.video_id, target)
                raise ClipMergeError("A downloaded stock clip was empty or invalid.")

            downloaded.append(DownloadedClip(candidate=candidate, path=target))

        progress("Downloading clips...", 50)
        LOGGER.info("Finished clip download phase with %s temporary files in %s", len(downloaded), job_temp)
        return downloaded

    def _assemble_video(self, downloaded, output_path, duration, orientation, job_temp, progress):
        segments = self._build_segments(downloaded, duration, progress)
        if not segments:
            raise ClipMergeError("No clips could be processed into video segments.")

        target_width, target_height = target_size(orientation)
        command = [
            self.ffmpeg_path,
            "-y",
            "-loglevel", "error",
            "-hide_banner",
            "-nostdin",
        ]

        for segment in segments:
            command.extend(["-i", str(segment["clip"].path)])

        filter_parts = []
        for index, segment in enumerate(segments):
            source_width = segment["clip"].candidate.width
            source_height = segment["clip"].candidate.height
            filter_parts.append(
                f"[{index}:v]{self._segment_filter(source_width, source_height, target_width, target_height, segment['start_at'], segment['length'])}[v{index}]"
            )

        if len(segments) == 1:
            filter_complex = filter_parts[0]
            output_label = "v0"
        else:
            concat_inputs = "".join(f"[v{index}]" for index in range(len(segments)))
            filter_complex = ";".join(filter_parts) + f";{concat_inputs}concat=n={len(segments)}:v=1:a=0[v]"
            output_label = "v"

        command.extend([
            "-filter_complex", filter_complex,
            "-map", f"[{output_label}]",
            "-an",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "24",
            "-threads", "0",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(output_path),
        ])

        LOGGER.info("FFmpeg single-pass command for %s segments: %s", len(segments), " ".join(command))
        self._run_ffmpeg(command, "FFmpeg could not process the clips.")

        if not output_path.exists() or output_path.stat().st_size < 1024:
            raise ClipMergeError("The final MP4 could not be created.")

        for segment in segments:
            try:
                segment["clip"].path.unlink(missing_ok=True)
            except OSError as exc:
                LOGGER.warning("Could not remove temporary source clip %s: %s", segment["clip"].path, exc)
        gc.collect()

    def _build_segments(self, downloaded, duration, progress):
        segments = []
        remaining = float(duration)
        clip_index = 0
        total_expected = max(1, math.ceil(duration / MAX_SEGMENT_SECONDS))

        while remaining > 0.25 and clip_index < len(downloaded) * 2:
            clip = downloaded[clip_index % len(downloaded)]
            segment_length = min(MAX_SEGMENT_SECONDS, remaining, max(1.0, clip.candidate.duration))
            max_start = max(0.0, clip.candidate.duration - segment_length - 0.1)
            start_at = self.rng.uniform(0, max_start) if max_start > 0 else 0
            progress(
                f"Processing videos... ({len(segments) + 1}/{total_expected})",
                min(78, 52 + int(len(segments) / total_expected * 26)),
            )
            LOGGER.info("Processing segment %s for clip %s from %.3f for %.3f seconds", len(segments) + 1, clip.candidate.video_id, start_at, segment_length)
            segments.append({"clip": clip, "start_at": start_at, "length": segment_length})
            remaining -= segment_length
            clip_index += 1

        return segments

    def _segment_filter(self, source_width, source_height, target_width, target_height, start_at, segment_length):
        base_filter = self._normalization_filter(source_width, source_height, target_width, target_height)
        return f"trim=start={start_at:.3f}:duration={segment_length:.3f},setpts=PTS-STARTPTS,{base_filter}"

    def _normalization_filter(self, source_width, source_height, target_width, target_height):
        source_ratio = source_width / source_height if source_width and source_height else target_width / target_height
        target_ratio = target_width / target_height
        source_is_landscape = source_ratio >= 1
        target_is_landscape = target_ratio >= 1
        ratio_delta = abs(source_ratio - target_ratio) / target_ratio

        if source_is_landscape == target_is_landscape and ratio_delta <= 0.35:
            return (
                f"scale={target_width}:{target_height}:force_original_aspect_ratio=decrease,"
                f"crop={target_width}:{target_height},fps={TARGET_FPS},"
                "format=yuv420p"
            )

        return (
            f"scale={target_width}:{target_height}:force_original_aspect_ratio=decrease,"
            f"pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2,"
            f"fps={TARGET_FPS},format=yuv420p"
        )

    def _run_ffmpeg(self, command, user_message):
        try:
            completed = subprocess.run(
                command,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                timeout=900,
            )
        except subprocess.TimeoutExpired as exc:
            LOGGER.exception("FFmpeg timed out while running command: %s", command)
            raise ClipMergeError("FFmpeg took too long while processing the video.", str(exc))
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or "").strip()
            LOGGER.exception("FFmpeg command failed: %s\n%s", command, detail[-1200:])
            raise ClipMergeError(user_message, detail[-1200:])

        return completed
