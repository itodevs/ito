import cv2
from dotenv import load_dotenv
import os

load_dotenv()

pi_ip = os.getenv('ROBOT_IP')
cap = cv2.VideoCapture(f'http://{pi_ip}:8080/stream?topic=/image_raw')

while True:
    ret, frame = cap.read()
    if not ret:
        continue
    # feed to MAST3R-SLAM here
    cv2.imshow('frame', frame)
    if cv2.waitKey(1) == ord('q'):
        break