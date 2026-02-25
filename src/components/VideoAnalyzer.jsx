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
    
      /* TODO [MT] uncomment when MS-TCT service ready
      const response = await fetch("http://localhost:5000/analyze", {
        method: "POST",
        body: formData,
      });

      const data = await response.json();
      */

        const mockResponse = [
            { time: "00:01.2", label: "Walking" },
            { time: "00:03.4", label: "Sitting" },
            { time: "00:07.8", label: "Standing" },
            { time: "00:12.5", label: "Running" }
        ];

        setActions(mockResponse);
    } 
    catch (error) {
      console.error("Error analyzing video:", error);
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

      {loading && <p className="processing-text">Processing...</p>}

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