import os
import tempfile
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Import the custom ML pipeline
from ml_pipeline import process_video_pipeline

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

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=5000, reload=True)