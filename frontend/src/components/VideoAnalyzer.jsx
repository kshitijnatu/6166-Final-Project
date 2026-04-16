import React from 'react'
import { useEffect, useRef, useState } from "react";

function createStreamId() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID();
  }

  return `stream-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function VideoAnalyzer() {
  const [videoFile, setVideoFile] = useState(null);
  const [videoURL, setVideoURL] = useState(null);
  const [streamUrl, setStreamUrl] = useState("");
  const [predictions, setPredictions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [streamActive, setStreamActive] = useState(false);
  const [streamStatus, setStreamStatus] = useState("");

  const fileInputRef = useRef(null);
  const streamSocketRef = useRef(null);
  const streamIdRef = useRef(null);
  const analyzeEndpoint = "http://localhost:5000/analyze";
  const streamSocketEndpoint = "ws://localhost:5000/ws/analyze-stream";
  const stopStreamEndpoint = "http://localhost:5000/stop-stream";
  
  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (!file) return;

    setVideoFile(file);
    setVideoURL(URL.createObjectURL(file));
    setPredictions([]);
  };

  const submitAnalysisRequest = async (requestOptions) => {
    setLoading(true);
    setPredictions([]);

    try {
      const response = await fetch(analyzeEndpoint, {
        method: "POST",
        ...requestOptions,
      });

      if (!response.ok) {
        throw new Error("Network response was not ok");
      }

      const data = await response.json();
      setPredictions(Array.isArray(data) ? data : []);
      
    } catch (error) {
      console.error("Error analyzing video:", error);
      alert("Failed to connect to the backend server. Is server.py running?");
    } finally {
      setLoading(false);
    }
  };

  const stopStreamAnalysis = async (statusMessage = "Stream analysis stopped.") => {
    const socket = streamSocketRef.current;
    const streamId = streamIdRef.current;

    if (streamId) {
      try {
        await fetch(stopStreamEndpoint, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ stream_id: streamId }),
        });
      } catch (error) {
        console.error("Error sending stop request:", error);
      }
    }

    if (socket) {
      socket.close();
      streamSocketRef.current = null;
    }

    streamIdRef.current = null;

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

    setPredictions([]);
    setLoading(true);
    setStreamStatus("Connecting to live stream analysis...");

    const socket = new WebSocket(streamSocketEndpoint);
    const streamId = createStreamId();
    streamSocketRef.current = socket;
    streamIdRef.current = streamId;

    socket.onopen = () => {
      setStreamActive(true);
      setStreamStatus("Stream connected. Waiting for updates every 15 seconds...");
      socket.send(JSON.stringify({ stream_url: trimmedStreamUrl, stream_id: streamId }));
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
          setPredictions((currentActions) => [...currentActions, ...nextActions]);
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
      streamIdRef.current = null;
      setStreamActive(false);
      setLoading(false);
      setStreamStatus((currentStatus) =>
        currentStatus === "Stream connection failed."
          ? currentStatus
          : "Stream analysis disconnected."
      );
    };
  };

  const groupedStreamPredictions = predictions.reduce((groups, prediction) => {
    const groupKey = prediction.segmentLabel || "Uploaded Video";

    if (!groups[groupKey]) {
      groups[groupKey] = [];
    }

    groups[groupKey].push(prediction);
    return groups;
  }, {});

  const uploadPredictions = predictions.filter((prediction) => !prediction.segmentLabel);
  const streamSegmentEntries = Object.entries(groupedStreamPredictions).filter(
    ([segmentLabel]) => segmentLabel !== "Uploaded Video"
  );

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

      {uploadPredictions.length > 0 && (
        <div className="results">
          <h2>Most Probable Predictions:</h2>
          <div className="actions-list">
            {uploadPredictions.map((prediction, index) => (
              <div key={`${prediction.label}-${index}`} className="action-item">
                <span className="label">{prediction.label}</span>
                <span className="confidence">
                  {prediction.confidence == null ? "N/A" : `${prediction.confidence}%`}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {streamSegmentEntries.length > 0 && (
        <div className="results">
          <h2>Stream Predictions By Interval:</h2>
          {streamSegmentEntries.map(([segmentLabel, segmentPredictions]) => (
            <div key={segmentLabel} className="stream-segment">
              <h3>{segmentLabel}</h3>
              <div className="actions-list">
                {segmentPredictions.map((prediction, index) => (
                  <div
                    key={`${segmentLabel}-${prediction.label}-${index}`}
                    className="action-item"
                  >
                    <span className="label">{prediction.label}</span>
                    <span className="confidence">
                      {prediction.confidence == null ? "N/A" : `${prediction.confidence}%`}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default VideoAnalyzer;
