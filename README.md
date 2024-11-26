# Python script for realtime ECG aquisitin from PC80B-BLE

Example command to stream to youtube:

```
$ pc80b-bleak \
  | ecgtovideo -r 30 \
  | ffmpeg -r 30 -f image2pipe -c:v png -i - \
                 -f pulse -ac 2 -i default \
                    -codec:a libmp3lame -ar 44100 -threads 6 -b:a 11025 \
           -r 30 -f flv rtmp://a.rtmp.youtube.com/live2/<KEY>
```
