#include <Servo.h>

// -----------------------------
// Pin mapping
// -----------------------------
const uint8_t PIR_PIN = 2;
const uint8_t SERVO_PIN = 3;
const uint8_t LEFT_EYE_LED_PIN = 5;
const uint8_t RIGHT_EYE_LED_PIN = 6;
const uint8_t BUZZER_PIN = 8;
const uint8_t ULTRASONIC_TRIG_PIN = 9;
const uint8_t ULTRASONIC_ECHO_PIN = 10;

// -----------------------------
// Motion and sensor settings
// -----------------------------
const int SERVO_LEFT_ANGLE = 60;
const int SERVO_CENTER_ANGLE = 90;
const int SERVO_RIGHT_ANGLE = 120;
const int SERVO_DEAD_BAND = 2;              // Reduce jitter
const unsigned long SERVO_UPDATE_MS = 120;  // Limit write frequency

const float ENGAGE_MIN_CM = 30.0;
const float ENGAGE_MAX_CM = 150.0;
const unsigned long ULTRASONIC_INTERVAL_MS = 220;

// -----------------------------
// Runtime state
// -----------------------------
Servo headServo;

bool wakeSent = false;
bool engageSent = false;
bool speakBlinkEnabled = false;

int currentServoAngle = SERVO_CENTER_ANGLE;
unsigned long lastServoWriteMs = 0;
unsigned long lastUltrasonicMs = 0;
unsigned long lastBlinkToggleMs = 0;

bool blinkState = false;

String serialBuffer = "";

// -----------------------------
// Helper functions
// -----------------------------
void setEyes(bool on) {
  uint8_t level = on ? HIGH : LOW;
  digitalWrite(LEFT_EYE_LED_PIN, level);
  digitalWrite(RIGHT_EYE_LED_PIN, level);
}

void beep(unsigned int frequency, unsigned long durationMs) {
  tone(BUZZER_PIN, frequency, durationMs);
}

float readDistanceCm() {
  digitalWrite(ULTRASONIC_TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(ULTRASONIC_TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(ULTRASONIC_TRIG_PIN, LOW);

  unsigned long duration = pulseIn(ULTRASONIC_ECHO_PIN, HIGH, 30000UL);
  if (duration == 0) {
    return -1.0;  // Timeout / invalid read
  }

  return duration * 0.0343f / 2.0f;
}

void setServoTarget(int targetAngle) {
  targetAngle = constrain(targetAngle, 0, 180);

  unsigned long now = millis();
  if (abs(targetAngle - currentServoAngle) <= SERVO_DEAD_BAND) {
    return;
  }

  if (now - lastServoWriteMs < SERVO_UPDATE_MS) {
    return;
  }

  headServo.write(targetAngle);
  currentServoAngle = targetAngle;
  lastServoWriteMs = now;
}

void resetSystem() {
  wakeSent = false;
  engageSent = false;
  speakBlinkEnabled = false;
  blinkState = false;
  serialBuffer = "";

  setEyes(false);
  noTone(BUZZER_PIN);
  setServoTarget(SERVO_CENTER_ANGLE);
}

void processCommand(const String &cmdRaw) {
  String cmd = cmdRaw;
  cmd.trim();
  cmd.toUpperCase();

  if (cmd == "LEFT") {
    setServoTarget(SERVO_LEFT_ANGLE);
  } else if (cmd == "CENTER") {
    setServoTarget(SERVO_CENTER_ANGLE);
  } else if (cmd == "RIGHT") {
    setServoTarget(SERVO_RIGHT_ANGLE);
  } else if (cmd == "SPEAK_START") {
    speakBlinkEnabled = true;
    lastBlinkToggleMs = millis();
    blinkState = true;
    setEyes(true);
  } else if (cmd == "SPEAK_STOP") {
    speakBlinkEnabled = false;
    setEyes(false);
  } else if (cmd == "RESET") {
    resetSystem();
  }
}

void handleSerial() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (serialBuffer.length() > 0) {
        processCommand(serialBuffer);
        serialBuffer = "";
      }
    } else {
      serialBuffer += c;
      if (serialBuffer.length() > 64) {
        serialBuffer = "";
      }
    }
  }
}

void setup() {
  pinMode(PIR_PIN, INPUT);
  pinMode(ULTRASONIC_TRIG_PIN, OUTPUT);
  pinMode(ULTRASONIC_ECHO_PIN, INPUT);
  pinMode(LEFT_EYE_LED_PIN, OUTPUT);
  pinMode(RIGHT_EYE_LED_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);

  Serial.begin(115200);

  headServo.attach(SERVO_PIN);
  headServo.write(SERVO_CENTER_ANGLE);

  resetSystem();
}

void loop() {
  handleSerial();

  unsigned long now = millis();

  // 1) PIR-based wake event (one-shot until reset)
  if (!wakeSent && digitalRead(PIR_PIN) == HIGH) {
    wakeSent = true;
    Serial.println("WAKE");
    beep(1800, 120);
  }

  // 2) Distance confirmation after wake (one-shot until reset)
  if (wakeSent && !engageSent && (now - lastUltrasonicMs >= ULTRASONIC_INTERVAL_MS)) {
    lastUltrasonicMs = now;
    float distanceCm = readDistanceCm();

    if (distanceCm >= ENGAGE_MIN_CM && distanceCm <= ENGAGE_MAX_CM) {
      engageSent = true;
      Serial.println("ENGAGE");
      beep(2400, 100);
    }
  }

  // 3) LED blinking during speech window
  if (speakBlinkEnabled && (now - lastBlinkToggleMs >= 250)) {
    lastBlinkToggleMs = now;
    blinkState = !blinkState;
    setEyes(blinkState);
  }
}
