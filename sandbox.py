import freenect
import numpy as np
import cv2

def get_depth(dev, data, timestamp):
    depth = data.astype(np.float32)
    depth_min = 500
    depth_max = 1500
    depth = np.clip(depth, depth_min, depth_max)
    depth = (depth - depth_min) / (depth_max - depth_min)
    depth = (depth * 255).astype(np.uint8)
    color = cv2.applyColorMap(depth, cv2.COLORMAP_JET)
    cv2.imshow('Sandbox', color)
    cv2.waitKey(1)

def get_video(dev, data, timestamp):
    pass

freenect.runloop(depth=get_depth, video=get_video)
