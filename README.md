# React + Vite

This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Babel](https://babeljs.io/) (or [oxc](https://oxc.rs) when used in [rolldown-vite](https://vite.dev/guide/rolldown)) for Fast Refresh
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/) for Fast Refresh

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the ESLint configuration

If you are developing a production application, we recommend using TypeScript with type-aware lint rules enabled. Check out the [TS template](https://github.com/vitejs/vite/tree/main/packages/create-vite/template-react-ts) for information on how to integrate TypeScript and [`typescript-eslint`](https://typescript-eslint.io) in your project.

## Running this project locally

After cloning the repository:

1. Install dependencies (uses the scripts in [`package.json`](package.json)):

   ```sh
   npm install
   ```

2. Start the dev server:

   ```sh
   npm run dev
   ```

3. Open the printed local URL in your browser (by default it is usually `http://localhost:5173/`).

## Model Weights
https://drive.google.com/file/d/1dBiVs7q9fJRd7FIWCh7vs4x_5cEvASpB/view?usp=drive_link


# Serving a Local Video as a Live Stream
To simulate a live stream locally, convert a video file into an HLS stream with ffmpeg and serve it over HTTP.

## Requirements
ffmpeg 
   -powershell download: (winget install --id Gyan.FFmpeg -e)
python

### Create an output folder
mkdir "C:\path\to\folder\hls-stream"
In all commands below: 

Replace C:\path\to\file.mp4 with path to the file you want to loop.

Replace C:\path\to\folder\hls-stream\live.m3u8 with the path to the folder you create with livie.m3u8 ath the end

### Start the looping HLS stream

Leave this running in a powershell terminal:
ffmpeg -re -stream_loop -1 -i "C:\path\to\file.mp4" -c:v libx264 -preset veryfast -tune zerolatency -c:a aac -f hls -hls_time 15 -hls_list_size 4 -hls_flags delete_segments+append_list "C:\path\to\folder\hls-stream\live.m3u8"

### Serve the stream folder
Run this in a second powershell terminal:

python -m http.server 8000 --directory "C:\path\to\folder\hls-stream"

#### Use this URL in the app
http://127.0.0.1:8000/live.m3u8
