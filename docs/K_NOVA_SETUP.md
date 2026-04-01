# K-NOVA Interactive Welcome Robot

## SECTION 1: System Overview

K-NOVA is built as a two-part system:

1. **Arduino Uno (hardware controller)**
   - Reads PIR motion sensor and HC-SR04 distance sensor.
   - Controls servo head movement, eye LEDs, and buzzer.
   - Sends serial events to PC: `WAKE`, `ENGAGE`.
   - Receives serial commands from PC: `LEFT`, `CENTER`, `RIGHT`, `SPEAK_START`, `SPEAK_STOP`, `RESET`.

2. **PC (Python brain)**
   - Handles state machine: `IDLE -> WAKE -> ENGAGE -> RESET -> IDLE`.
   - Runs webcam at 640x480.
   - Detects largest face using OpenCV Haar cascade.
   - Converts face center to `LEFT/CENTER/RIGHT` zones and sends movement commands.
   - Plays a 35-second welcome audio once per cycle.
   - Draws fullscreen robot face UI on monitor.

---

## SECTION 2: Wiring Connections

### Power and Ground
- Arduino `5V` to PIR `VCC`
- Arduino `GND` to PIR `GND`
- Arduino `GND` to Ultrasonic `GND`
- Arduino `5V` to Ultrasonic `VCC`
- Arduino `GND` to LED/Buzzer ground rail
- Servo power should use a stable 5V source (common ground with Arduino).

### Exact Pin Mapping

#### PIR (HC-SR501)
- `VCC -> 5V`
- `GND -> GND`
- `OUT -> D2`

#### Ultrasonic (HC-SR04)
- `TRIG -> D9`
- `ECHO -> D10`
- `VCC -> 5V`
- `GND -> GND`

#### Servo (MG996R)
- `Signal -> D3`
- `VCC -> 5V external supply` (recommended)
- `GND -> Common GND`

#### LEDs (eyes)
- `Left eye anode -> D5` through 220 ohm resistor
- `Right eye anode -> D6` through 220 ohm resistor
- LED cathodes -> `GND`

#### Buzzer
- `+ -> D8`
- `- -> GND`

#### PC and Display
- Arduino USB -> PC USB
- Webcam USB -> PC USB
- 15-inch monitor -> PC HDMI/DisplayPort

---

## SECTION 3: Arduino Code

Use: `arduino/k_nova_controller.ino`

This sketch implements:
- PIR wake trigger and one-shot `WAKE` serial message.
- Ultrasonic engage validation (30-150 cm) and one-shot `ENGAGE` message.
- Servo movement commands with jitter protection.
- LED blinking while speech is active.
- Buzzer chirps for status cues.
- `RESET` logic to return to idle cleanly.

---

## SECTION 4: Python Code

Use: `pc/k_nova_brain.py`

This script implements:
- Full state machine (`IDLE`, `WAKE`, `ENGAGE`, `RESET`).
- Serial communication with Arduino.
- Webcam capture at 640x480.
- Largest-face tracking using Haar cascade.
- 3-zone split logic (`LEFT`, `CENTER`, `RIGHT`).
- Audio playback only once per cycle.
- Fullscreen robot face UI on monitor.
- Timed reset after 35 seconds.

---

## SECTION 5: How It Works (Step-by-step runtime)

1. **IDLE**
   - Arduino waits for PIR motion.
   - PC waits for `WAKE` on serial.
   - UI window is closed (screen can remain dark or display standby content).

2. **WAKE**
   - PIR goes HIGH -> Arduino sends `WAKE`.
   - PC starts camera and opens fullscreen robot UI.
   - Arduino checks distance repeatedly using HC-SR04.

3. **ENGAGE**
   - If distance is 30-150 cm -> Arduino sends `ENGAGE`.
   - PC starts 35-second interaction timer.
   - PC sends `SPEAK_START`, then plays welcome audio once.
   - PC detects largest face each frame and computes zone:
     - Left third -> `LEFT`
     - Center third -> `CENTER`
     - Right third -> `RIGHT`
   - PC sends direction only when changed (anti-spam).
   - Arduino moves servo and blinks eye LEDs during speaking.

4. **RESET**
   - After 35 seconds, PC sends `SPEAK_STOP` and `RESET`.
   - Arduino turns LEDs off, recenters servo, clears wake/engage flags.
   - PC closes camera/UI and returns to `IDLE`.

---

## SECTION 6: Setup Instructions

### A) Arduino IDE Setup
1. Install Arduino IDE.
2. Connect Arduino Uno by USB.
3. Open `arduino/k_nova_controller.ino`.
4. Ensure **Servo** library is available (built-in).
5. Select board: **Arduino Uno**.
6. Select correct COM port.
7. Upload sketch.

### B) Python Environment Setup
1. Install Python 3.10+.
2. In project root, create virtual env (optional but recommended):
   ```bash
   python -m venv .venv
   source .venv/bin/activate   # Linux/macOS
   # .venv\Scripts\activate   # Windows PowerShell
   ```
3. Install dependencies:
   ```bash
   pip install opencv-python pyserial
   ```

### C) Prepare Audio
1. Place your 35-second audio file as `welcome.wav` in project root
   - OR pass a custom path using `--audio`.

### D) Run the System
1. Keep Arduino connected.
2. Start Python app:
   ```bash
   python pc/k_nova_brain.py --port COM3 --audio welcome.wav --duration 35
   ```
   Linux example:
   ```bash
   python pc/k_nova_brain.py --port /dev/ttyACM0 --audio welcome.wav --duration 35
   ```
3. Trigger PIR by approaching robot.
4. Stand 30-150 cm in front for ENGAGE cycle.

---

## SECTION 7: Troubleshooting

1. **No serial events (`WAKE`/`ENGAGE`)**
   - Verify baud: 115200 on both sides.
   - Confirm PIR output LED changes when motion is detected.
   - Check ultrasonic wiring and common ground.

2. **Servo jitters**
   - Use external 5V supply for MG996R.
   - Ensure all grounds are common.
   - Keep signal wires short and away from motor power cables.

3. **Face detection is slow**
   - Confirm camera is 640x480.
   - Improve lighting.
   - Use USB 2.0/3.0 direct connection instead of hub.

4. **Audio not playing**
   - Confirm file exists and format is valid WAV.
   - Linux may require `aplay` package.
   - macOS uses `afplay`; Windows uses built-in `winsound`.

5. **Repeated retriggering**
   - This implementation uses one-shot event flags.
   - Only `RESET` re-arms the cycle.

