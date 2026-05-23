import freenect
import numpy as np
import cv2

def get_depth():
    depth, _ = freenect.sync_get_depth()
    depth = depth.astype(np.float32)
    return depth

def colorize(depth):
    depth_min = 500
    depth_max = 1500
    depth = np.clip(depth, depth_min, depth_max)
    depth = (depth - depth_min) / (depth_max - depth_min)
    depth = (depth * 255).astype(np.uint8)
    color = cv2.applyColorMap(depth, cv2.COLORMAP_JET)
    return color

while True:
    depth = get_depth()
    color = colorize(depth)
    cv2.imshow('Sandbox', color)
    if cv2.waitKey(1) == 27:
        break

cv2.destroyAllWindows()
