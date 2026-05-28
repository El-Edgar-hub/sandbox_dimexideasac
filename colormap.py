import cv2
import numpy as np

from config import colormap_idx, colormap_names

colormaps_builtin = [cv2.COLORMAP_JET, cv2.COLORMAP_TURBO, cv2.COLORMAP_RAINBOW, cv2.COLORMAP_HOT]


def make_topo_colormap():
    colors = [
        (0,   [0,   0,   80]),
        (60,  [0,   60,  180]),
        (100, [0,   160, 200]),
        (140, [0,   180, 80]),
        (180, [180, 210, 0]),
        (210, [255, 160, 0]),
        (240, [200, 0,   0]),
        (255, [255, 255, 255]),
    ]
    lut = np.zeros((256, 1, 3), dtype=np.uint8)
    for i in range(len(colors) - 1):
        v0, c0 = colors[i]
        v1, c1 = colors[i + 1]
        for v in range(v0, v1):
            t = (v - v0) / (v1 - v0)
            lut[v, 0] = [int(c0[j] + t * (c1[j] - c0[j])) for j in range(3)]
    lut[255, 0] = colors[-1][1]
    return lut


topo_lut = make_topo_colormap()


def apply_colormap(gray, idx):
    if colormap_names[idx] == 'TOPO':
        return cv2.applyColorMap(gray, topo_lut)
    return cv2.applyColorMap(gray, colormaps_builtin[idx])
