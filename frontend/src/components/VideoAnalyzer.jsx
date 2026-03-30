import React from 'react'
import { useState, useRef } from "react";

function VideoAnalyzer() {
  const [videoFile, setVideoFile] = useState(null);
  const [videoURL, setVideoURL] = useState(null);
  const [actions, setActions] = useState([]);
  const [loading, setLoading] = useState(false);

  const fileInputRef = useRef(null);

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (!file) return;

    setVideoFile(file);
    setVideoURL(URL.createObjectURL(file));
    setActions([]);
  };

  const handleAnalyze = async () => {
    if (!videoFile) return;

    setLoading(true);
    setActions([]);

    try {
      const formData = new FormData();
      formData.append("video", videoFile);
    
      // Calling the LOCAL Python backend
      const response = await fetch("http://localhost:5000/analyze", {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        throw new Error("Network response was not ok");
      }

      const data = await response.json();
      setActions(data);
      
    } catch (error) {
      console.error("Error analyzing video:", error);
      alert("Failed to connect to the backend server. Is server.py running?");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="analyzer-container">
      <h1>Video Action Analyzer</h1>

      <div className="controls">
        <input
          type="file"
          accept="video/*"
          ref={fileInputRef}
          onChange={handleFileChange}
          hidden
        />

        <button
          className="secondary-btn"
          onClick={() => fileInputRef.current.click()}
        >
          Select Video File
        </button>

        <button
          className="primary-btn"
          onClick={handleAnalyze}
          disabled={!videoFile || loading}
        >
          Analyze
        </button>
      </div>

      {loading && <p className="processing-text">Processing on local backend...</p>}

      {videoURL && (
        <div className="video-container">
          <video controls src={videoURL} />
        </div>
      )}

      {actions.length > 0 && (
        <div className="results">
          <h2>Detected Actions:</h2>
          <div className="actions-list">
            {actions.map((action, index) => (
              <div key={index} className="action-item">
                <span className="timestamp">{action.time}</span>
                <span className="label">{action.label}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default VideoAnalyzer;