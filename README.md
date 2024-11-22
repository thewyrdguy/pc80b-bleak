# Python script for realtime ECG aquisitin from PC80B-BLE

Example command to stream to youtube:

```
$ ecgtovideo -r 30 </tmp/pc80b.sock \
  | ffmpeg -y -r 30 -f image2pipe -c:v png -i - \
           -f lavfi -i anullsrc=channel_layout=stereo:sample_rate=44100 \
           -r 30 -f flv rtmp://a.rtmp.youtube.com/live2/<KEY>
```
