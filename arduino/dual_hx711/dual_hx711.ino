/*
 * dual_hx711.ino
 *
 * Streams raw 24-bit readings from two HX711 load-cell amplifiers over the
 * USB serial link at 115200 baud in the form:
 *
 *     LC,<raw1>,<raw2>\n
 *
 * Calibration (tare offset and scale) is intentionally performed on the
 * host side so that the Arduino firmware never has to be re-flashed when
 * the load cells are recalibrated.
 *
 * Wiring (defaults - change the constants below to match your board):
 *
 *     HX711 #1   DT  -> D2     SCK -> D3
 *     HX711 #2   DT  -> D4     SCK -> D5
 *     Both HX711 VCC -> 5V     GND -> GND
 *
 * Requires the "HX711" library by Bogdan Necula (Library Manager).
 */

#include <HX711.h>

static const uint8_t LC1_DOUT_PIN = 2;
static const uint8_t LC1_SCK_PIN  = 3;
static const uint8_t LC2_DOUT_PIN = 4;
static const uint8_t LC2_SCK_PIN  = 5;

// HX711 channel A gain 128 -> ~80 SPS depending on the module strap.
static const uint8_t HX711_GAIN = 128;

HX711 lc1;
HX711 lc2;

void setup() {
    Serial.begin(115200);
    while (!Serial) {
        // Wait for USB CDC on boards that need it (e.g. Leonardo, Nano33).
    }

    lc1.begin(LC1_DOUT_PIN, LC1_SCK_PIN, HX711_GAIN);
    lc2.begin(LC2_DOUT_PIN, LC2_SCK_PIN, HX711_GAIN);

    // Print a one-line banner so the host can confirm the link.
    Serial.println(F("# dual_hx711 ready"));
}

void loop() {
    // read() blocks until the chip signals data ready, so simply alternating
    // between channels keeps both load cells at their natural sample rate.
    if (lc1.is_ready() && lc2.is_ready()) {
        long r1 = lc1.read();
        long r2 = lc2.read();

        Serial.print(F("LC,"));
        Serial.print(r1);
        Serial.print(',');
        Serial.println(r2);
    }
}
