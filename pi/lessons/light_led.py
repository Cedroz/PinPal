"""
The one lesson: light an LED.

ROI tuning: run `python camera.py --calibrate` to overlay these boxes on
the live preview and adjust (x, y, w, h) to match your physical rig.
All coordinates are in pixels at FRAME_WIDTH x FRAME_HEIGHT (1280x720).
"""

# Each step:
#   id          - unique slug
#   instruction - what the tutor says / displays
#   roi         - (x, y, w, h) crop sent to Claude vision; TUNE TO YOUR RIG
#   check_q     - narrow yes/no question for Claude vision on the cropped ROI
STEPS = [
    {
        "id": "place_led",
        "instruction": (
            "Grab the LED — it's the small clear bulb with two metal legs. "
            "Push it into the breadboard so it bridges the center gap, "
            "with the longer leg on the left side."
        ),
        "roi": (540, 280, 200, 160),  # center of breadboard — TUNE ME
        "check_q": (
            "Is there an LED component (small bulb with two legs) "
            "bridging the center gap of the breadboard? Answer YES, NO, or UNSURE."
        ),
    },
    {
        "id": "place_resistor",
        "instruction": (
            "Now pick up the resistor — the small striped cylinder. "
            "Place one leg in the same row as the LED's long leg, "
            "and the other leg two rows to the left."
        ),
        "roi": (440, 280, 200, 160),  # anode-side rows — TUNE ME
        "check_q": (
            "Is there a resistor (small striped component) placed in the "
            "breadboard rows near the LED's longer leg? Answer YES, NO, or UNSURE."
        ),
    },
    {
        "id": "jumper_power_to_resistor",
        "instruction": (
            "Take a red jumper wire. Connect one end to the red plus rail "
            "at the top of the breadboard, and the other end to the same "
            "row as the free end of the resistor."
        ),
        "roi": (360, 100, 320, 260),  # power rail + resistor row — TUNE ME
        "check_q": (
            "Is there a wire connecting the red power rail at the top to "
            "the breadboard rows in this region? Answer YES, NO, or UNSURE."
        ),
    },
    {
        "id": "jumper_cathode_to_ground",
        "instruction": (
            "Take a black jumper wire. Connect one end to the row where "
            "the LED's short leg sits, and the other end to the blue "
            "minus rail at the top."
        ),
        "roi": (540, 100, 280, 300),  # cathode row + ground rail — TUNE ME
        "check_q": (
            "Is there a wire connecting the blue or black ground rail to "
            "the breadboard rows near the LED's short leg? Answer YES, NO, or UNSURE."
        ),
    },
    {
        "id": "led_lit",
        "instruction": (
            "Great — now plug in the power supply or flip the switch. "
            "The LED should light up. If it doesn't, don't worry — "
            "I'll check what's going on."
        ),
        "roi": (540, 280, 200, 160),  # LED position — same as step 1, TUNE ME
        "check_q": (
            "Is the LED glowing or emitting visible light right now? "
            "Answer YES, NO, or UNSURE."
        ),
    },
]


def get_step(index: int) -> dict:
    return STEPS[index]


def total_steps() -> int:
    return len(STEPS)
