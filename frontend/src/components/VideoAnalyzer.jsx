import React from 'react'
import { useEffect, useRef, useState } from "react";

function VideoAnalyzer() {
  const [videoFile, setVideoFile] = useState(null);
  const [videoURL, setVideoURL] = useState(null);
  const [streamUrl, setStreamUrl] = useState("");
  const [actions, setActions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [streamActive, setStreamActive] = useState(false);
  const [streamStatus, setStreamStatus] = useState("");

  const fileInputRef = useRef(null);
  const streamSocketRef = useRef(null);
  const analyzeEndpoint = "http://localhost:5000/analyze";
  const streamSocketEndpoint = "ws://localhost:5000/ws/analyze-stream";
  
  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (!file) return;

    setVideoFile(file);
    setVideoURL(URL.createObjectURL(file));
    setActions([]);
  };

  const submitAnalysisRequest = async (requestOptions) => {
    setLoading(true);
    setActions([]);

    try {
      const response = await fetch(analyzeEndpoint, {
        method: "POST",
        ...requestOptions,
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

  const stopStreamAnalysis = (statusMessage = "Stream analysis stopped.") => {
    const socket = streamSocketRef.current;

    if (socket) {
      socket.close();
      streamSocketRef.current = null;
    }

    setStreamActive(false);
    setLoading(false);
    setStreamStatus(statusMessage);
  };

  useEffect(() => {
    return () => {
      if (streamSocketRef.current) {
        streamSocketRef.current.close();
      }
    };
  }, []);

  const handleAnalyze = async () => {
    if (!videoFile) return;

    const formData = new FormData();
    formData.append("video", videoFile);

    await submitAnalysisRequest({ body: formData });
  };

  const handleStreamAnalyze = () => {
    const trimmedStreamUrl = streamUrl.trim();
    if (!trimmedStreamUrl || streamActive) return;

    setActions([]);
    setLoading(true);
    setStreamStatus("Connecting to live stream analysis...");

    const socket = new WebSocket(streamSocketEndpoint);
    streamSocketRef.current = socket;

    socket.onopen = () => {
      setStreamActive(true);
      setStreamStatus("Stream connected. Waiting for updates every 15 seconds...");
      socket.send(JSON.stringify({ stream_url: trimmedStreamUrl }));
    };

    socket.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        const nextActions = Array.isArray(payload)
          ? payload
          : Array.isArray(payload.actions)
            ? payload.actions
            : payload.action
              ? [payload.action]
              : [];

        if (nextActions.length > 0) {
          setActions((currentActions) => [...currentActions, ...nextActions]);
        }

        if (payload.message) {
          setStreamStatus(payload.message);
        } else {
          setStreamStatus("Received latest stream analysis update.");
        }
      } catch (error) {
        console.error("Error parsing stream analysis update:", error);
        setStreamStatus("Received an unreadable stream update.");
      } finally {
        setLoading(false);
      }
    };

    socket.onerror = (error) => {
      console.error("WebSocket stream analysis error:", error);
      stopStreamAnalysis("Stream connection failed.");
      alert("Failed to connect to the stream analysis WebSocket.");
    };

    socket.onclose = () => {
      streamSocketRef.current = null;
      setStreamActive(false);
      setLoading(false);
      setStreamStatus((currentStatus) =>
        currentStatus === "Stream connection failed."
          ? currentStatus
          : "Stream analysis disconnected."
      );
    };
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

      <div className="stream-controls">
        <input
          type="text"
          className="stream-input"
          placeholder="Enter RTSP, HLS (.m3u8), or direct stream URL"
          value={streamUrl}
          onChange={(e) => setStreamUrl(e.target.value)}
          disabled={streamActive}
        />

        <button
          className="primary-btn"
          onClick={handleStreamAnalyze}
          disabled={!streamUrl.trim() || loading || streamActive}
        >
          Analyze Stream
        </button>

        <button
          className="secondary-btn"
          onClick={() => stopStreamAnalysis()}
          disabled={!streamActive}
        >
          Stop Analysis
        </button>
      </div>

      {loading && <p className="processing-text">Processing on local backend...</p>}
      {streamStatus && <p className="processing-text">{streamStatus}</p>}

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