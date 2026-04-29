"""Build a 2x2 comparison video showing CartPole performance at different training steps.

Reads cp_{0,5000,10000,15000}-episode-0.mp4 from videos/checkpoints/ and produces
videos/comparison.mp4 with per-panel Step label, freeze padding to align lengths,
and a final SUCCESS/FAILED overlay (green/red) so the difference is unmistakable.

Compatible with MoviePy 2.x (uses `with_*` API and self-contained freeze padding).
"""
import argparse
import re
from pathlib import Path
from typing import Tuple

import numpy as np
from moviepy import (
    VideoFileClip,
    ColorClip,
    ImageClip,
    CompositeVideoClip,
    concatenate_videoclips,
    clips_array,
)
from PIL import Image, ImageDraw, ImageFont


CHECKPOINT_PATTERN: re.Pattern = re.compile(r"cp_(\d+)-episode-0\.mp4")
DEFAULT_VIDEO_DIR: str = "./videos/checkpoints"
DEFAULT_OUTPUT_PATH: str = "./videos/comparison.mp4"
# CartPole-v1 reaches the 500-step truncation cap at exactly 10s (50 fps).
SUCCESS_THRESHOLD_SEC: float = 9.9
ENV_FPS: int = 50


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video-dir", default=DEFAULT_VIDEO_DIR)
    parser.add_argument("--output", default=DEFAULT_OUTPUT_PATH)
    return parser.parse_args()


def find_checkpoint_videos(video_dir: Path) -> list[Tuple[int, Path]]:
    detected: list[Tuple[int, Path]] = []
    for video_path in video_dir.glob("cp_*-episode-0.mp4"):
        match = CHECKPOINT_PATTERN.match(video_path.name)
        if match:
            detected.append((int(match.group(1)), video_path))
    return sorted(detected)


def load_font(font_size: int) -> ImageFont.ImageFont:
    candidate_font_paths: list[str] = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
    ]
    for path in candidate_font_paths:
        if Path(path).is_file():
            try:
                return ImageFont.truetype(path, font_size)
            except Exception:
                continue
    return ImageFont.load_default()


def render_text_image(
    text: str,
    font_size: int,
    fg_color: Tuple[int, int, int, int] = (255, 255, 255, 255),
    bg_color: Tuple[int, int, int, int] = (0, 0, 0, 0),
    padding: int = 8,
) -> np.ndarray:
    font = load_font(font_size)
    dummy_image = Image.new("RGBA", (1, 1))
    text_bbox = ImageDraw.Draw(dummy_image).textbbox((0, 0), text, font=font)
    text_width: int = text_bbox[2] - text_bbox[0]
    text_height: int = text_bbox[3] - text_bbox[1]
    rendered = Image.new(
        "RGBA",
        (text_width + padding * 2, text_height + padding * 2),
        bg_color,
    )
    ImageDraw.Draw(rendered).text(
        (padding - text_bbox[0], padding - text_bbox[1]),
        text,
        font=font,
        fill=fg_color,
    )
    return np.array(rendered)


def freeze_pad_to_duration(clip: VideoFileClip, target_duration: float) -> VideoFileClip:
    if clip.duration >= target_duration:
        return clip
    source_fps: float = clip.fps if clip.fps else float(ENV_FPS)
    last_frame_time: float = max(0.0, clip.duration - 1.0 / source_fps)
    last_frame: np.ndarray = clip.get_frame(last_frame_time)
    freeze_duration: float = target_duration - clip.duration
    freeze_clip = (
        ImageClip(last_frame).with_duration(freeze_duration).with_fps(source_fps)
    )
    return concatenate_videoclips([clip, freeze_clip])


def build_panel_for_step(
    training_steps: int, video_dir: Path, target_duration: float
) -> CompositeVideoClip:
    video_path: Path = video_dir / f"cp_{training_steps:06d}-episode-0.mp4"
    base_clip: VideoFileClip = VideoFileClip(str(video_path))
    episode_steps: int = int(round(base_clip.duration * ENV_FPS))
    is_success: bool = base_clip.duration >= SUCCESS_THRESHOLD_SEC
    panel_width, panel_height = base_clip.size

    step_label_image: np.ndarray = render_text_image(
        f"Step {training_steps:,}",
        font_size=22,
        fg_color=(255, 255, 255, 255),
        bg_color=(0, 0, 0, 200),
    )
    step_label_clip = (
        ImageClip(step_label_image).with_position((10, 10)).with_duration(target_duration)
    )

    extended_clip = freeze_pad_to_duration(base_clip, target_duration)

    if is_success:
        overlay_rgb: Tuple[int, int, int] = (51, 204, 51)
        verdict_text: str = "✓ SUCCESS"
        sub_text: str = "reward 500"
        overlay_start: float = max(0.0, target_duration - 1.5)
    else:
        overlay_rgb = (255, 51, 51)
        verdict_text = "✗ FAILED"
        sub_text = f"(lasted {episode_steps} steps)"
        overlay_start = base_clip.duration

    overlay_duration: float = target_duration - overlay_start

    color_overlay = (
        ColorClip(size=(panel_width, panel_height), color=overlay_rgb)
        .with_opacity(0.4)
        .with_duration(overlay_duration)
        .with_start(overlay_start)
    )

    verdict_image: np.ndarray = render_text_image(verdict_text, font_size=44)
    sub_image: np.ndarray = render_text_image(sub_text, font_size=22)

    verdict_clip = (
        ImageClip(verdict_image)
        .with_position(("center", panel_height // 2 - 40))
        .with_start(overlay_start)
        .with_duration(overlay_duration)
    )
    sub_clip = (
        ImageClip(sub_image)
        .with_position(("center", panel_height // 2 + 20))
        .with_start(overlay_start)
        .with_duration(overlay_duration)
    )

    return CompositeVideoClip(
        [extended_clip, color_overlay, verdict_clip, sub_clip, step_label_clip],
        size=(panel_width, panel_height),
    ).with_duration(target_duration)


def main() -> None:
    args: argparse.Namespace = parse_args()
    video_dir: Path = Path(args.video_dir)

    detected_checkpoints: list[Tuple[int, Path]] = find_checkpoint_videos(video_dir)
    if len(detected_checkpoints) != 4:
        raise SystemExit(
            f"[make_comparison] Expected exactly 4 checkpoint videos in {video_dir}, "
            f"found {len(detected_checkpoints)}: "
            f"{[steps for steps, _ in detected_checkpoints]}"
        )
    print(
        f"[make_comparison] Detected checkpoints (steps): "
        f"{[steps for steps, _ in detected_checkpoints]}"
    )

    durations: list[float] = []
    for _steps, video_path in detected_checkpoints:
        with VideoFileClip(str(video_path)) as probe_clip:
            durations.append(probe_clip.duration)
    target_duration: float = max(durations)
    print(f"[make_comparison] Target duration: {target_duration:.2f}s")

    panels: list[CompositeVideoClip] = [
        build_panel_for_step(training_steps, video_dir, target_duration)
        for training_steps, _ in detected_checkpoints
    ]
    grid_clip = clips_array([[panels[0], panels[1]], [panels[2], panels[3]]])

    output_path: Path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    grid_clip.write_videofile(str(output_path), codec="libx264", audio=False)
    print(f"[make_comparison] Wrote {output_path}")


if __name__ == "__main__":
    main()
