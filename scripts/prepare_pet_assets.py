#!/usr/bin/env python3
"""Build Retina video assets from the attributed 1280x720 original clips.

Dev-only: Pillow, numpy, imageio-ffmpeg; native HEVC encoder compiled separately.
Keeps the original 24 fps and complete clip. Never scales a web thumbnail back up.
"""
from pathlib import Path
import json
import subprocess
import numpy as np
from scipy import ndimage
from PIL import Image
import imageio_ffmpeg

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / '.setup/references/dsh-pet/original'
DEST = ROOT / 'ui/public/pet'
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
SIZE = (640, 720)
NAMES = json.loads((ROOT / 'config/pet-sources.json').read_text())

def key(frame):
    rgb = frame.astype(np.int16)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    dominance = g - np.maximum(r, b)
    chroma = rgb.max(axis=2) - rgb.min(axis=2)
    # Saturation condition preserves white lace, skin and neutral greys.
    green = (dominance > 2) & (chroma > 20)
    alpha = np.where(green, np.clip((14 - dominance) / 12, 0, 1) * 255, 255).astype(np.uint8)
    rgba = np.dstack((frame, alpha))
    labels, _ = ndimage.label(alpha > 100)
    areas = np.bincount(labels.ravel()); areas[0] = 0
    main = int(areas.argmax())
    objects = ndimage.find_objects(labels)
    body = objects[main - 1]
    keep = np.zeros(len(areas), dtype=bool); keep[main] = True
    for index, region in enumerate(objects, 1):
        if region and areas[index] >= 250 and region[1].start < body[1].stop + 180 and region[1].stop > body[1].start - 180 and region[0].start < body[0].stop + 180 and region[0].stop > body[0].start - 180: keep[index] = True
    support = ndimage.binary_dilation(keep[labels], iterations=2)
    rgba[..., 3] = np.where(support, alpha, 0)
    # Despill only semitransparent edge pixels; preserve opaque costume colours.
    rgba[..., 1] = np.where((rgba[..., 3] > 0) & (rgba[..., 3] < 250), np.minimum(g, np.maximum(r, b)), g).astype(np.uint8)
    return rgba

def bounds(rgba):
    mask = rgba[..., 3] > 80
    xs = np.where(mask.sum(axis=0) > 16)[0]
    ys = np.where(mask.sum(axis=1) > 30)[0]
    if not len(xs) or not len(ys): raise RuntimeError('No character found')
    return (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)

def read_exact(stream, count):
    data = bytearray()
    while len(data) < count:
        part = stream.read(count - len(data))
        if not part: break
        data.extend(part)
    return data

def build(name, title):
    source = SOURCE / (name + '.mp4')
    sample = subprocess.check_output([FFMPEG, '-loglevel', 'error', '-i', str(source), '-vf', 'fps=3', '-an', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'])
    frames = np.frombuffer(sample, np.uint8).reshape((-1, 720, 1280, 3))
    boxes = [bounds(key(f)) for f in frames]
    first = boxes[0]
    box = (max(0, min(b[0] for b in boxes) - 12), max(0, min(b[1] for b in boxes) - 12), min(1280, max(b[2] for b in boxes) + 12), min(720, max(b[3] for b in boxes) + 12))
    width, height = box[2] - box[0], box[3] - box[1]
    scale = min(570 / (first[3] - first[1]), 624 / width, 704 / height, 1.0)
    resized = (round(width * scale), round(height * scale))
    x = round(320 - ((first[0] + first[2]) / 2 - box[0]) * scale)
    y = round(680 - (first[3] - box[1]) * scale)
    x = min(max(x, 8), 632 - resized[0]); y = min(max(y, 8), 712 - resized[1])
    decoder = subprocess.Popen([FFMPEG, '-loglevel', 'error', '-i', str(source), '-an', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], stdout=subprocess.PIPE)
    movie = subprocess.Popen([str(ROOT / '.setup/media-tools/pet-video-encoder'), str(DEST / (name + '.mov')), '640', '720', '24'], stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    webm = subprocess.Popen([FFMPEG, '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pixel_format', 'bgra', '-video_size', '640x720', '-framerate', '24', '-i', '-', '-an', '-c:v', 'libvpx-vp9', '-pix_fmt', 'yuva420p', '-crf', '22', '-b:v', '0', '-row-mt', '1', '-cpu-used', '4', str(DEST / (name + '.webm'))], stdin=subprocess.PIPE)
    count = 0
    try:
        while data := read_exact(decoder.stdout, 1280 * 720 * 3):
            if len(data) != 1280 * 720 * 3: raise RuntimeError('Partial video frame')
            image = Image.fromarray(key(np.frombuffer(data, np.uint8).reshape((720, 1280, 3))), 'RGBA').crop(box).resize(resized, Image.Resampling.LANCZOS)
            stage = Image.new('RGBA', SIZE); stage.paste(image, (x, y))
            if count == 0: stage.save(DEST / (name + '-poster.png'))
            if count == 72: stage.save(DEST / (name + '-preview.png'))
            bgra = np.asarray(stage)[..., [2, 1, 0, 3]].tobytes()
            movie.stdin.write(bgra); webm.stdin.write(bgra); count += 1
    finally:
        decoder.stdout.close(); movie.stdin.close(); webm.stdin.close()
    if decoder.wait() or movie.wait() or webm.wait(): raise RuntimeError(movie.stderr.read().decode())
    print(name, count, 'frames', 'source crop', box, 'standing pixels', round((first[3]-first[1])*scale), flush=True)
    return {'label': title, 'width': 640, 'height': 720, 'fps': 24, 'frames': count, 'duration': count / 24, 'poster': name + '-poster.png', 'preview': name + '-preview.png', 'mov': name + '.mov', 'webm': name + '.webm', 'source': title + '.mp4'}

if __name__ == '__main__':
    DEST.mkdir(exist_ok=True)
    animations = {}
    for name, title in NAMES.items(): animations[name] = build(name, title)
    (DEST / 'manifest.json').write_text(json.dumps({'version': 2, 'source': 'https://github.com/PC2005-cloud/dsh-pet/releases/tag/assets-videos', 'license': 'CC BY-NC-SA 4.0 / noncommercial; see ATTRIBUTION.md', 'animations': animations}, ensure_ascii=False, indent=2))
