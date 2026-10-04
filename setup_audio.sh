#!/bin/bash
# Creates a virtual source "combined" that carries BOTH the speakers and the MV7.
pactl load-module module-null-sink sink_name=combined sink_properties=device.description=CombinedCapture
pactl load-module module-loopback source=alsa_output.pci-0000_0f_00.6.analog-stereo.monitor sink=combined latency_msec=50
pactl load-module module-loopback source=alsa_input.usb-Shure_Inc_Shure_MV7__MV7__12-8fdbb045a1a2325098a8ef7f70efdb39-01.mono-fallback sink=combined latency_msec=50
echo "Combined source ready: combined.monitor"
