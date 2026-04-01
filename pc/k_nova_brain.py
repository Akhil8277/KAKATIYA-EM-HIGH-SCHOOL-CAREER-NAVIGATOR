#!/usr/bin/env python3
"""
K-NOVA Interactive Welcome Robot - PC Brain

State machine:
IDLE -> WAKE -> ENGAGE -> RESET -> IDLE
"""

import argparse
import enum
import os
import platform
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Optional, Tuple

import cv2
import serial


class SystemState(enum.Enum):
    IDLE = "IDLE"
    WAKE = "WAKE"
    ENGAGE = "ENGAGE"
    RESET = "RESET"


@dataclass
class Config:
    serial_port: str
    baud_rate: int = 115200
    camera_index: int = 0
    interaction_seconds: int = 35
    audio_path: str = "welcome.wav"


class AudioPlayer:
    """Cross-platform best-effort one-shot audio player."""

    def __init__(self, audio_path: str) -> None:
        self.audio_path = audio_path

    def play_once_async(self) -> None:
        thread = threading.Thread(target=self._play_blocking, daemon=True)
        thread.start()

    def _play_blocking(self) -> None:
        if not os.path.exists(self.audio_path):
            print(f"[WARN] Audio file not found: {self.audio_path}")
            return

        system_name = platform.system().lower()
        try:
            if "windows" in system_name:
                import winsound

                winsound.PlaySound(self.audio_path, winsound.SND_FILENAME)
            elif "darwin" in system_name:
                subprocess.run(["afplay", self.audio_path], check=False)
            else:
                subprocess.run(["aplay", self.audio_path], check=False)
        except Exception as exc:
            print(f"[WARN] Audio playback failed: {exc}")


class KNovaBrain:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.state = SystemState.IDLE
        self.previous_state = None

        self.serial_conn = serial.Serial(cfg.serial_port, cfg.baud_rate, timeout=0.05)
        time.sleep(2.0)  # allow Arduino reset on serial open

        self.camera: Optional[cv2.VideoCapture] = None
        self.face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )

        self.interaction_start_ts: Optional[float] = None
        self.last_direction_sent: Optional[str] = None
        self.last_direction_sent_ts: float = 0.0
        self.direction_interval_s = 0.18

        self.audio_player = AudioPlayer(cfg.audio_path)
        self.audio_started_this_cycle = False

        self.frame_width = 640
        self.frame_height = 480

    # ---------- Serial helpers ----------
    def send_command(self, cmd: str) -> None:
        self.serial_conn.write((cmd + "\n").encode("utf-8"))

    def read_serial_line(self) -> Optional[str]:
        raw = self.serial_conn.readline().decode("utf-8", errors="ignore").strip()
        return raw if raw else None

    # ---------- Camera/UI ----------
    def start_camera(self) -> None:
        if self.camera is not None:
            return

        cap = cv2.VideoCapture(self.cfg.camera_index)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.frame_width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.frame_height)
        if not cap.isOpened():
            raise RuntimeError("Unable to open webcam")

        self.camera = cap

    def stop_camera(self) -> None:
        if self.camera is not None:
            self.camera.release()
            self.camera = None

    def draw_robot_ui(self, frame, direction: str, engaged: bool) -> None:
        h, w = frame.shape[:2]
        overlay = frame.copy()

        # Zone guides: LEFT | CENTER | RIGHT
        cv2.line(overlay, (w // 3, 0), (w // 3, h), (80, 80, 80), 1)
        cv2.line(overlay, (2 * w // 3, 0), (2 * w // 3, h), (80, 80, 80), 1)

        # Simple robot face overlay
        cv2.circle(overlay, (w // 2 - 100, h // 2 - 80), 30, (255, 255, 255), -1)
        cv2.circle(overlay, (w // 2 + 100, h // 2 - 80), 30, (255, 255, 255), -1)
        cv2.rectangle(overlay, (w // 2 - 120, h // 2 + 40), (w // 2 + 120, h // 2 + 70), (255, 255, 255), -1)

        status_txt = f"State: {self.state.value}"
        direction_txt = f"Head: {direction}"
        engage_txt = "Greeting Active" if engaged else "Waiting"

        cv2.putText(overlay, status_txt, (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 220, 0), 2)
        cv2.putText(overlay, direction_txt, (20, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 220, 0), 2)
        cv2.putText(overlay, engage_txt, (20, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 220, 0), 2)

        cv2.imshow("K-NOVA Face UI", overlay)

    # ---------- Face tracking ----------
    def detect_largest_face(self, frame) -> Optional[Tuple[int, int, int, int]]:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.2,
            minNeighbors=5,
            minSize=(60, 60),
            flags=cv2.CASCADE_SCALE_IMAGE,
        )
        if len(faces) == 0:
            return None

        return max(faces, key=lambda f: f[2] * f[3])

    def face_to_zone(self, face_box: Tuple[int, int, int, int], frame_width: int) -> str:
        x, _, w, _ = face_box
        cx = x + w // 2

        left_boundary = frame_width // 3
        right_boundary = 2 * frame_width // 3

        if cx < left_boundary:
            return "LEFT"
        if cx > right_boundary:
            return "RIGHT"
        return "CENTER"

    def maybe_send_direction(self, direction: str) -> None:
        now = time.time()
        if (
            direction != self.last_direction_sent
            and (now - self.last_direction_sent_ts) >= self.direction_interval_s
        ):
            self.send_command(direction)
            self.last_direction_sent = direction
            self.last_direction_sent_ts = now

    # ---------- State transitions ----------
    def transition(self, new_state: SystemState) -> None:
        if new_state == self.state:
            return
        print(f"[STATE] {self.state.value} -> {new_state.value}")
        self.previous_state = self.state
        self.state = new_state

        if new_state == SystemState.WAKE:
            self.start_camera()
            cv2.namedWindow("K-NOVA Face UI", cv2.WINDOW_NORMAL)
            cv2.setWindowProperty(
                "K-NOVA Face UI", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN
            )

        elif new_state == SystemState.ENGAGE:
            self.interaction_start_ts = time.time()
            self.audio_started_this_cycle = False
            self.last_direction_sent = None

        elif new_state == SystemState.RESET:
            self.send_command("SPEAK_STOP")
            self.send_command("RESET")
            self.stop_camera()
            cv2.destroyAllWindows()
            self.interaction_start_ts = None
            self.audio_started_this_cycle = False
            self.last_direction_sent = None
            time.sleep(0.7)
            self.transition(SystemState.IDLE)

    def run(self) -> None:
        print("[INFO] K-NOVA brain started")
        print("[INFO] Waiting for WAKE from Arduino...")

        try:
            while True:
                serial_msg = self.read_serial_line()
                if serial_msg:
                    print(f"[SERIAL] {serial_msg}")

                if self.state == SystemState.IDLE:
                    if serial_msg == "WAKE":
                        self.transition(SystemState.WAKE)

                elif self.state == SystemState.WAKE:
                    if serial_msg == "ENGAGE":
                        self.transition(SystemState.ENGAGE)

                    # Keep UI active even before engagement
                    if self.camera is not None:
                        ok, frame = self.camera.read()
                        if ok:
                            self.draw_robot_ui(frame, direction="CENTER", engaged=False)
                    cv2.waitKey(1)

                elif self.state == SystemState.ENGAGE:
                    if not self.audio_started_this_cycle:
                        self.send_command("SPEAK_START")
                        self.audio_player.play_once_async()
                        self.audio_started_this_cycle = True

                    if self.camera is not None:
                        ok, frame = self.camera.read()
                        if ok:
                            direction = "CENTER"
                            largest_face = self.detect_largest_face(frame)

                            if largest_face is not None:
                                x, y, w, h = largest_face
                                direction = self.face_to_zone(largest_face, frame.shape[1])
                                cv2.rectangle(
                                    frame,
                                    (x, y),
                                    (x + w, y + h),
                                    (0, 255, 0),
                                    2,
                                )

                            self.maybe_send_direction(direction)
                            self.draw_robot_ui(frame, direction=direction, engaged=True)

                    cv2.waitKey(1)

                    if (
                        self.interaction_start_ts is not None
                        and (time.time() - self.interaction_start_ts) >= self.cfg.interaction_seconds
                    ):
                        self.transition(SystemState.RESET)

                time.sleep(0.01)

        except KeyboardInterrupt:
            print("\n[INFO] Shutting down...")
        finally:
            try:
                self.send_command("SPEAK_STOP")
                self.send_command("RESET")
            except Exception:
                pass
            self.stop_camera()
            cv2.destroyAllWindows()
            self.serial_conn.close()


def parse_args() -> Config:
    parser = argparse.ArgumentParser(description="K-NOVA Interactive Welcome Robot Brain")
    parser.add_argument("--port", required=True, help="Arduino serial port (e.g., COM3 or /dev/ttyACM0)")
    parser.add_argument("--baud", type=int, default=115200, help="Serial baud rate")
    parser.add_argument("--camera", type=int, default=0, help="Webcam index")
    parser.add_argument("--audio", default="welcome.wav", help="Path to 35-second welcome audio")
    parser.add_argument("--duration", type=int, default=35, help="Interaction duration in seconds")
    args = parser.parse_args()

    return Config(
        serial_port=args.port,
        baud_rate=args.baud,
        camera_index=args.camera,
        interaction_seconds=args.duration,
        audio_path=args.audio,
    )


if __name__ == "__main__":
    config = parse_args()
    brain = KNovaBrain(config)
    brain.run()
