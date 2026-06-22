import cv2
import numpy as np


def make_topo_colormap():
    # Colors in BGR order (OpenCV convention)
    colors = [
        (0,   [80,  0,   0  ]),  # dark blue
        (60,  [180, 60,  0  ]),  # blue
        (100, [200, 160, 0  ]),  # cyan
        (140, [80,  180, 0  ]),  # green
        (180, [0,   210, 180]),  # yellow-green
        (210, [0,   160, 255]),  # orange
        (240, [0,   0,   200]),  # red
        (255, [255, 255, 255]),  # white
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


def apply_colormap(gray):
    return cv2.applyColorMap(gray, topo_lut)
