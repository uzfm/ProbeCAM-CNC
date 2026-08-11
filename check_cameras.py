import cv2

backends = [
    ("dshow", cv2.CAP_DSHOW),
    ("msmf", cv2.CAP_MSMF),
    ("any", cv2.CAP_ANY),
]

print("Scanning for cameras with OpenCV...")
found = False
for index in range(0, 8):
    for backend_name, backend_id in backends:
        cap = cv2.VideoCapture(index, backend_id)
        if cap.isOpened():
            ok, _ = cap.read()
            cap.release()
            print(f"Camera found: index={index}, backend={backend_name}, frame_read_ok={ok}")
            found = True
            break

if not found:
    print("No cameras detected. Make sure the device is connected and not used by another app.")
