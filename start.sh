#!/bin/bash
# FFmpeg ডাউনলোড ও সেটআপ
if [ ! -f "ffmpeg" ]; then
  wget https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz
  tar -xf ffmpeg-release-amd64-static.tar.xz
  cp ffmpeg-*-static/ffmpeg ./
  cp ffmpeg-*-static/ffprobe ./
  rm -rf ffmpeg-*-static*
fi
chmod +x ffmpeg ffprobe
export PATH=$PATH:$(pwd)

# বট রান করা
python main.py
