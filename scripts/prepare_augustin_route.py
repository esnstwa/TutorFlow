"""Rebuild route sprites from the supplied PNGs; requires Pillow, numpy, scipy.

Usage: python scripts/prepare_augustin_route.py archive.zip [qa-directory]
No generated or redrawn frames. Only the exterior matte is corrected.
"""
import sys
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt, binary_fill_holes


def clean(image):
    rgba = np.asarray(image.convert('RGBA')).astype(float) / 255
    rgb, alpha = rgba[:, :, :3], rgba[:, :, 3]
    # Fill interior holes so white eyes and glossy interior highlights are untouched.
    silhouette = binary_fill_holes(alpha > 0.02)
    depth = distance_transform_edt(silhouette)
    trusted = (depth >= 3) & (alpha > .99)
    _, nearest = distance_transform_edt(~trusted, return_indices=True)
    foreground = rgb[tuple(nearest)]
    edge = (depth < 3) & (alpha > 0)
    # Solve C = a*F + (1-a)*white using the nearest uncontaminated color.
    direction = 1 - foreground
    coverage = np.clip(np.sum((1-rgb)*direction, axis=2)
                       / np.maximum(np.sum(direction**2, axis=2), .001), 0, 1)
    rgb[edge] = foreground[edge]
    alpha[edge] *= coverage[edge]
    alpha[alpha < 1/255] = 0
    rgb[alpha == 0] = 0
    result = Image.fromarray(np.round(rgba*255).astype('uint8'))
    return result.crop(result.getbbox())


def main():
    destination = Path(__file__).resolve().parents[1] / 'app/web/static/images/registration/route'
    destination.mkdir(parents=True, exist_ok=True)
    sources = [('augustin-idle', 'idle'), ('augustin-happy', 'success-end')]
    with zipfile.ZipFile(sys.argv[1]) as archive:
        frames = [
            clean(Image.open(archive.open(f'augustin_route_frames_v2/semantic_png/{source}.png')))
            for _, source in sources
        ]
    size = tuple(max(frame.size[axis] for frame in frames) + 20 for axis in (0, 1))
    canvases = []
    for (name, _), frame in zip(sources, frames):
        canvas = Image.new('RGBA', size)
        canvas.alpha_composite(frame, tuple((size[axis] - frame.size[axis]) // 2 for axis in (0, 1)))
        canvas.save(destination / f'{name}.webp', lossless=True, method=6, exact=True)
        canvases.append(canvas)
        print(name, size, canvas.getbbox())
    if len(sys.argv) > 2:
        qa = Path(sys.argv[2])
        qa.mkdir(parents=True, exist_ok=True)
        for label, background in [('white', '#ffffff'), ('gray', '#777777'), ('color', '#b95339')]:
            sheet = Image.new('RGB', (size[0] * len(canvases), size[1]), background)
            for index, canvas in enumerate(canvases):
                sheet.paste(canvas, (size[0] * index, 0), canvas)
            sheet.save(qa / f'edges-{label}.png')


if __name__ == '__main__':
    main()
