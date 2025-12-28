# PrusaConnectUploader
Uploads Snapshoots to Prusa Connect and supports Enclosure Temp. 
This is a solution for everyone who switched from OctoPrint to Prusa Connect.
With the MK3.5 Upgrade I started to use Prusa Connect but I couldn't show my Enclosure Temp any more and I needed to upload Snapshots from my two Webcams to PrusaConnect somehow so this is what I came up with.

## Disclaimer
This Docu is mainly made for my future self. But please feel free to add and improve!

## How it works
Basically I use fswebcam to get snapshoots from my usb cams and since there is sadly no Enclosure Temp Endpoint in Prusa Connect I simply add and Overlay in the Snapshots. Furthermore I added a "Flashlight" function to it. The Script turns on the LED lights before it takes the snapshots and than turns it off again. There is also a Button connected to the Pi which can overwrite this so it stays on.

## Dependencies
* fswebcam
* python3-requests
* python3-rpi.gpio
* python3-pil

> sudo apt install python3-requests python3-rpi.gpio python3-pil fswebcam
</br>

or pip
</br>

> pip3 install requests RPi.GPIO Pillow

## Systemd
I added a simple systemd service to start and stop the service
Just add the prusa-uploader.service. file to your systemd config.

> systemctl enabled prusa-uploader.service
</br>
> systemctl start/stop prusa-uploader.service

## Get Camera Ids
> ls /dev/v4l/by-id/

## Test Cam
> fswebcam -d /dev/v4l/by-id/usb-Logitech_Webcam_C270_ABC123-video-index0 image.jpg

## Circuit Schematic

### LED/Flashlight Control (GPIO 26 with MOSFET)

```
                           +12V (or appropriate voltage for LED)
                            |
                            |
                     [LED/Flashlight]
                            |
                            |
                            D (Drain)
GPIO 26 ----[1kΩ]---------- G (MOSFET - N-Channel)
                     |      S (Source)
                     |      |
                  [10kΩ]    |
                (pull-down) |
                     |      |
                    GND    GND
```

### Momentary Switch/Button (GPIO 2 with Pull-Up)

```
                    +3.3V
                     |
                  [10kΩ]
                 (pull-up)
                     |
    GPIO 2 ----------+
                     |
                    [S] Momentary Switch
                     |
                    GND
```

### Component Notes
- **MOSFET**: Use N-Channel like 2N7000 or IRLZ44N (depending on LED current)
- **Gate Resistor (1kΩ)**: Limits current from GPIO to MOSFET gate
- **Pull-down Resistor (10kΩ)**: Ensures MOSFET is OFF when GPIO is not driven
- **Pull-up Resistor (10kΩ)**: Keeps GPIO 2 HIGH when button not pressed
- **Momentary Switch**: Normally open, connects to GND when pressed
- **LED**: Add appropriate current-limiting resistor in series with LED

### Raspberry Pi Pins
- GPIO 26 (Physical Pin 37)
- GPIO 2 (Physical Pin 3)
- GND (Physical Pin 6, 9, 14, 20, 25, 30, 34, or 39)
- 3.3V (Physical Pin 1 or 17)

### Operation
1. GPIO 26 HIGH → MOSFET ON → LED lights up
2. Button press → GPIO 2 pulled LOW (falling edge) → Toggle override mode

## Configuration
Copy `config.example.json` to `config.json` and edit with your settings:
```bash
cp config.example.json config.json
```

Edit the configuration file with your camera details, tokens, and GPIO pins.