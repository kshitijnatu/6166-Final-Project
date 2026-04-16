import os
import tempfile
import json
from threading import Event
from fastapi import FastAPI, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import cv2

# Import the custom ML pipeline
from ml_pipeline import process_video_pipeline, stream_capture_intervals

app = FastAPI()

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


@app.websocket("/ws/analyze-stream")
async def analyze_stream(websocket: WebSocket):
    await websocket.accept()
    print("WebSocket client connected for stream analysis.")
    stop_event = Event()

    try:
        initial_message = await websocket.receive_text()
        payload = json.loads(initial_message)
        stream_url = payload.get("stream_url", "").strip()

        if not stream_url:
            await websocket.send_json({"error": "A stream_url value is required."})
            await websocket.close(code=1003)
            return

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

        for interval_result in stream_capture_intervals(
            stream_url,
            interval_seconds=15,
            stop_event=stop_event,
        ):
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
        stop_event.set()

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=5000, reload=True)