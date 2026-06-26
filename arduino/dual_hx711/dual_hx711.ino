/*
 * dual_hx711.ino
 *
 * Streams raw 24-bit readings from two HX711 load-cell amplifiers and
 * drives a throttle servo over the USB serial link at 115200 baud.
 *
 * Outgoing lines (Arduino -> host):
 *
 *     LC,<raw1>,<raw2>\n           // every fresh HX711 sample pair
 *     SV,<angle>\n                 // current servo angle after a write
 *     # <text>\n                   // human-readable banner / status
 *
 * Incoming commands (host -> Arduino), one per line, terminated by '\n':
 *
 *     S:<angle>\n                  // set servo angle in whole degrees,
 *                                  //   clamped to [SERVO_MIN_DEG, SERVO_MAX_DEG]
 *
 * Calibration of the load cells (tare offset and scale) and the mapping
 * from "throttle percent" to "servo angle" are intentionally performed
 * on the host side so that the Arduino firmware never has to be
 * re-flashed when anything is retuned.
 *
 * Wiring (defaults - change the constants below to match your board):
 *
 *     HX711 #1   DT  -> D2     SCK -> D3
 *     HX711 #2   DT  -> D4     SCK -> D5
 *     Throttle servo  signal -> D9   (any PWM-capable pin works)
 *     Both HX711 VCC -> 5V     GND -> GND
 *     Servo VCC -> external 5 V supply, GND tied to Arduino GND.
 *
 * Requires the "HX711" library by Bogdan Necula (Library Manager) and
 * the bundled "Servo" library.
 */

#include <HX711.h>
#include <Servo.h>

static const uint8_t LC1_DOUT_PIN = 2;
static const uint8_t LC1_SCK_PIN  = 3;
static const uint8_t LC2_DOUT_PIN = 4;
static const uint8_t LC2_SCK_PIN  = 5;
static const uint8_t SERVO_PIN    = 9;

// HX711 channel A gain 128 -> ~80 SPS depending on the module strap.
static const uint8_t HX711_GAIN = 128;

// Hardware limits of a hobby servo. The host applies its own calibration
// (0% / 100% throttle angles) on top of this range.
static const uint8_t SERVO_MIN_DEG = 0;
static const uint8_t SERVO_MAX_DEG = 180;

// Power-on position: middle of the travel. The host should send an
// explicit S:<angle> as soon as it connects to put the throttle at a
// known safe value (typically the calibrated 0% angle).
static const uint8_t SERVO_BOOT_DEG = 0;

HX711 lc1;
HX711 lc2;
Servo throttle;
uint8_t servo_angle = SERVO_BOOT_DEG;

// Line-assembly buffer for incoming serial commands.
static const uint8_t RX_BUF_LEN = 32;
char rx_buf[RX_BUF_LEN];
uint8_t rx_len = 0;

// Watchdog for the load-cell stream. When the motor runs hard, electrical
// noise and a brief sag on the shared 5 V rail can latch an HX711 into a
// power-down / stuck state. After that, is_ready() never returns true again
// and the LC stream dies. If no fresh sample pair has been read for this
// long, attempt a recovery (and report which channel is not responding).
static const unsigned long LC_STALL_TIMEOUT_MS = 500;
unsigned long last_sample_ms = 0;
// Throttle the diagnostic output so a persistently-faulty channel does not
// flood the serial link (which would also drown out real LC/SV lines).
static const unsigned long LC_REPORT_INTERVAL_MS = 2000;
unsigned long last_report_ms = 0;

static void apply_servo_angle(long deg) {
    if (deg < SERVO_MIN_DEG) deg = SERVO_MIN_DEG;
    if (deg > SERVO_MAX_DEG) deg = SERVO_MAX_DEG;
    servo_angle = (uint8_t)deg;
    throttle.write(servo_angle);

    Serial.print(F("SV,"));
    Serial.println(servo_angle);
}

static void handle_command(const char *line) {
    // Only one command for now: "S:<angle>".
    if (line[0] == 'S' && line[1] == ':') {
        long deg = atol(line + 2);
        apply_servo_angle(deg);
    }
}

static void poll_serial() {
    while (Serial.available() > 0) {
        char c = (char)Serial.read();
        if (c == '\r') {
            continue;
        }
        if (c == '\n') {
            rx_buf[rx_len] = '\0';
            if (rx_len > 0) {
                handle_command(rx_buf);
            }
            rx_len = 0;
            continue;
        }
        if (rx_len < RX_BUF_LEN - 1) {
            rx_buf[rx_len++] = c;
        } else {
            // Overflow: drop the line so we resync on the next newline.
            rx_len = 0;
        }
    }
}

void setup() {
    Serial.begin(115200);
    while (!Serial) {
        // Wait for USB CDC on boards that need it (e.g. Leonardo, Nano33).
    }

    lc1.begin(LC1_DOUT_PIN, LC1_SCK_PIN, HX711_GAIN);
    lc2.begin(LC2_DOUT_PIN, LC2_SCK_PIN, HX711_GAIN);

    throttle.attach(SERVO_PIN);
    throttle.write(SERVO_BOOT_DEG);

    // Boot self-test: give each amplifier up to 1 s to produce its first
    // data-ready. A channel that reports NO RESPONSE here has a wiring,
    // power, or module fault (the data line never goes low) — no amount of
    // host-side or firmware retrying can invent data for a dead channel.
    Serial.print(F("# lc1 boot: "));
    Serial.println(lc1.wait_ready_timeout(1000) ? F("OK") : F("NO RESPONSE"));
    Serial.print(F("# lc2 boot: "));
    Serial.println(lc2.wait_ready_timeout(1000) ? F("OK") : F("NO RESPONSE"));

    // Print a one-line banner so the host can confirm the link.
    Serial.println(F("# dual_hx711 ready"));
    Serial.print(F("SV,"));
    Serial.println(servo_angle);

    last_sample_ms = millis();
    last_report_ms = millis();
}

// Called when the paired read has stalled. Reports which channel is not
// asserting data-ready (the key diagnostic), then toggles both amplifiers
// through the power-down / power-up sequence to recover from a recoverable
// (noise / brownout) lockup. Output is rate-limited so a hard-faulted
// channel cannot flood the serial link.
static void on_stall() {
    unsigned long now = millis();
    if (now - last_report_ms >= LC_REPORT_INTERVAL_MS) {
        Serial.print(F("# HX711 stall: lc1_ready="));
        Serial.print(lc1.is_ready() ? 1 : 0);
        Serial.print(F(" lc2_ready="));
        Serial.print(lc2.is_ready() ? 1 : 0);
        Serial.println(F(" (check wiring/power on the not-ready channel)"));
        last_report_ms = now;
    }

    lc1.power_down();
    lc2.power_down();
    delay(1);
    lc1.power_up();
    lc2.power_up();
    last_sample_ms = millis();
}

void loop() {
    // Service incoming throttle commands first so the servo responds
    // promptly even when the HX711s are streaming at their full rate.
    poll_serial();

    // read() blocks until the chip signals data ready, so simply alternating
    // between channels keeps both load cells at their natural sample rate.
    if (lc1.is_ready() && lc2.is_ready()) {
        // Disable interrupts for the duration of each bit-banged read so the
        // Servo library's timer ISR can't stretch an SCK pulse mid-read. A
        // clock line held high for >60 us pushes the HX711 into power-down
        // and yields a corrupt sample that the host then silently discards,
        // which looks like "no load-cell data" while the motor/servo runs.
        noInterrupts();
        long r1 = lc1.read();
        interrupts();

        noInterrupts();
        long r2 = lc2.read();
        interrupts();

        last_sample_ms = millis();

        Serial.print(F("LC,"));
        Serial.print(r1);
        Serial.print(',');
        Serial.println(r2);
    } else if (millis() - last_sample_ms > LC_STALL_TIMEOUT_MS) {
        on_stall();
    }
}
