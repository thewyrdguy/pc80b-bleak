# Tool for realtime ECG aquisition from PC80B-BLE device, and live-streaming

The app receives realitime ECG from the bluetooth recorder, composes
moving picture of the ECG trace, mixes it with audio input (typically
from a microphone), and streams it to an RTMP server.
Works with youtube, and should work with twitter/x, twitch, discord,
and others.

Uses Python bindings for GTK4 and Gstreamer.

Note that the recorder must have "wireless" mode enabled
(and it that mode, it does not save recordings in its storage).
