import os
import tempfile
import json
import asyncio
from threading import Event, Thread
from fastapi import FastAPI, UploadFile, File, WebSocket, WebSocketDisconnect, Body
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import cv2

# Import the custom ML pipeline
from ml_pipeline import process_video_pipeline, stream_capture_intervals

app = FastAPI()
active_streams = {}
STREAM_COMPLETE = {"type": "stream_complete"}

# Allow the local React app to talk to this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/analyze")
async def analyze_video(video: UploadFile = File(...)):
    temp_video_path = None
    
    try:
        # Save uploaded video locally
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_video:
            content = await video.read()
            temp_video.write(content)
            temp_video_path = temp_video.name

        print(f"Received video locally at: {temp_video_path}")

        # Run the ML Pipeline
        print("Starting ML Pipeline...")
        results = process_video_pipeline(temp_video_path)

        print("Sending results to frontend!")
        return results

    except Exception as e:
        print(f"Error processing video: {e}")
        return {"error": str(e)}
    
    finally:
        # Clean up temp file
        if temp_video_path and os.path.exists(temp_video_path):
            os.remove(temp_video_path)
            print("Cleaned up temporary file.")


@app.post("/stop-stream")
async def stop_stream(stream_id: str = Body(..., embed=True)):
    stop_event = active_streams.get(stream_id)

    if stop_event:
        stop_event.set()
        print(f"Stop requested for stream session {stream_id}.")
        return {"status": "stopping"}

    return {"status": "not_found"}


def _stream_worker(stream_url, stop_event, output_queue, loop):
    try:
        for interval_result in stream_capture_intervals(
            stream_url,
            interval_seconds=15,
            stop_event=stop_event,
        ):
            if stop_event.is_set():
                break
            loop.call_soon_threadsafe(output_queue.put_nowait, interval_result)
    except Exception as e:
        loop.call_soon_threadsafe(output_queue.put_nowait, {"error": str(e), "actions": []})
    finally:
        loop.call_soon_threadsafe(output_queue.put_nowait, STREAM_COMPLETE)


@app.websocket("/ws/analyze-stream")
async def analyze_stream(websocket: WebSocket):
    await websocket.accept()
    print("WebSocket client connected for stream analysis.")
    stop_event = None
    stream_id = None
    worker_thread = None

    try:
        initial_message = await websocket.receive_text()
        payload = json.loads(initial_message)
        stream_url = payload.get("stream_url", "").strip()
        stream_id = payload.get("stream_id", "").strip()

        if not stream_url:
            await websocket.send_json({"error": "A stream_url value is required."})
            await websocket.close(code=1003)
            return

        if not stream_id:
            await websocket.send_json({"error": "A stream_id value is required."})
            await websocket.close(code=1003)
            return

        stop_event = Event()
        active_streams[stream_id] = stop_event

        cap = cv2.VideoCapture(stream_url)
        if not cap.isOpened():
            cap.release()
            await websocket.send_json({
                "error": "Cannot open video stream with the provided stream_url.",
                "actions": [],
            })
            await websocket.close(code=1003)
            return

        print("Opened stream successfully.")
        cap.release()

        await websocket.send_json({
            "message": "Stream connection accepted. Processing 15-second intervals.",
            "actions": [],
        })

        loop = asyncio.get_running_loop()
        output_queue = asyncio.Queue()
        worker_thread = Thread(
            target=_stream_worker,
            args=(stream_url, stop_event, output_queue, loop),
            daemon=True,
        )
        worker_thread.start()

        while True:
            interval_result = await output_queue.get()

            if interval_result is STREAM_COMPLETE:
                break

            if stop_event.is_set():
                print(f"Stream session {stream_id} stopped before sending interval results.")
                break

            await websocket.send_json(interval_result)

        if not stop_event.is_set():
            await websocket.send_json({
                "message": "Stream ended or no more frames were available.",
                "actions": [],
            })
    except WebSocketDisconnect:
        stop_event.set()
        print("WebSocket client disconnected from stream analysis.")
    except json.JSONDecodeError:
        stop_event.set()
        await websocket.send_json({"error": "Invalid JSON payload."})
        await websocket.close(code=1003)
    except Exception as e:
        stop_event.set()
        print(f"Error during stream analysis: {e}")
        try:
            await websocket.send_json({"error": str(e), "actions": []})
        except RuntimeError:
            pass
        try:
            await websocket.close(code=1011)
        except RuntimeError:
            pass
    finally:
        if stop_event:
            stop_event.set()
        if worker_thread and worker_thread.is_alive():
            worker_thread.join(timeout=1.0)
        if stream_id:
            active_streams.pop(stream_id, None)

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=5000, reload=True)
