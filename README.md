# JabloPy - Simple interface for Jablotron alarm systems
This service enables 2-way communication with a Jablotron alarm system without relying on cloud services or reverse-engineered APIs.

It exposes:
- The alarm system itself (supports arming and disarming of sections)
- Sensors (motion sensors, contact sensors, smoke and fire alarm, sirens, ...)
- System flags (arming delay, entry delay, ...)
- System state (armed, disarmed, alarm, ...)

## Requirements
- A JA-121-T interface module must be installed
- A bridge device that can translate the RS-485 bus to tcp (For instance: A Waveshare RS485 to WiFi/Ethernet Module)

## Installing and running
TODO


