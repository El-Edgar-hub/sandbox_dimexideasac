import os
import cv2
import freenect
import threading

os.environ['LIBUSB_DEBUG'] = '0'

from config import load_config, DISPLAY_WIDTH, DISPLAY_HEIGHT
from kinect import get_depth, get_video
from web import run_flask

load_config()
flask_thread = threading.Thread(target=run_flask, daemon=True)
flask_thread.start()

cv2.namedWindow('Sandbox', cv2.WINDOW_NORMAL)
cv2.moveWindow('Sandbox', 0, 0)
cv2.resizeWindow('Sandbox', DISPLAY_WIDTH, DISPLAY_HEIGHT)
cv2.setWindowProperty('Sandbox', cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
freenect.runloop(depth=get_depth, video=get_video)
