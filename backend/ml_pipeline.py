import torch
import cv2
import numpy as np
import sys
import os
import pickle
import tempfile

# --- PATH SETUP ---
# Ensure Python can find both cloned repositories
sys.path.append(os.path.join(os.path.dirname(__file__), 'pytorch-i3d'))
sys.path.append(os.path.join(os.path.dirname(__file__), 'MS-TCT'))

try:
    from pytorch_i3d import InceptionI3d
except ImportError:
    print("WARNING: Could not import pytorch_i3d. Check your folder structure.")

try:
    # Importing the model and aliasing it to match our code
    from MSTCT.MSTCT_Model import MSTCT as MS_TCT 
except Exception as e:
    print(f"❌ FATAL ERROR IMPORTING MS-TCT: {e}")

# Automatically use CPU if a local GPU isn't available
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Local ML Pipeline initialized on: {device}")

# --- INITIALIZE I3D MODEL ---
i3d_model = None
try:
    i3d_model = InceptionI3d(400, in_channels=3)
    i3d_weights_path = os.path.join(os.path.dirname(__file__), 'pytorch-i3d', 'models', 'rgb_imagenet.pt')
    
    if os.path.exists(i3d_weights_path):
        # weights_only=False suppresses a PyTorch security warning for older model files
        i3d_model.load_state_dict(torch.load(i3d_weights_path, map_location=device, weights_only=False))
        i3d_model.eval()
        i3d_model = i3d_model.to(device)
        print("I3D Model loaded successfully.")
    else:
        print(f"WARNING: I3D Weights not found at {i3d_weights_path}")
except Exception as e:
    print(f"Error initializing I3D: {e}")


def extract_features(video_path, target_size=224):
    """Reads video, formats tensor, and extracts I3D features."""
    if i3d_model is None:
        raise ValueError("I3D Model is not loaded.")

    cap = cv2.VideoCapture(video_path)
    frames = []
    
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret: break
        frame = cv2.resize(frame, (target_size, target_size))
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frames.append(frame)
    cap.release()

    if not frames:
        raise ValueError("Could not read video frames.")

    frames_np = np.array(frames, dtype=np.float32)
    frames_np = (frames_np / 255.0) * 2.0 - 1.0 
    tensor = torch.from_numpy(frames_np).permute(3, 0, 1, 2).unsqueeze(0).to(device)
    
    with torch.no_grad():
        features = i3d_model.extract_features(tensor)
        features = features.view(1024, -1).transpose(0, 1)
        
    return features


def run_ms_tct(features, weights_filename="charades_model.pth", top_k=5):
    """Runs MS-TCT and returns the most probable action classes for a clip."""
    print(f"I3D Features extracted: {features.shape}") 
    
    # 1. Reshape for MS-TCT ([Time, 1024] -> [Batch, Time, Channels])
    ms_tct_input = features.transpose(0, 1).unsqueeze(0).to(device)
    
    num_action_classes = 157 
    weights_path = os.path.join(os.path.dirname(__file__), 'MS-TCT', weights_filename)
    
    try:
        # 2. Initialize the Model (Using the exact architecture from train.py)
        model = MS_TCT(
            in_feat_dim=1024,          
            num_classes=num_action_classes, 
            inter_channels=[256, 384, 576, 864], # 4-scale architecture
            num_block=3,                         # 3 encoder blocks
            head=8,                              # 8 attention heads
            mlp_ratio=8,                         # MLP multiplier
            final_embedding_dim=512              # 512 final dimension
        ).to(device)
        
        print(f"Loading MS-TCT weights from {weights_path} using PyTorch...")
        
        # 3. Load the standard PyTorch .pth file!
        checkpoint = torch.load(weights_path, map_location=device, weights_only=False)
            
        # Extract the actual weights if they are nested inside a checkpoint dictionary
        if isinstance(checkpoint, dict) and "state_dict" in checkpoint:
            state_dict = checkpoint["state_dict"]
        elif isinstance(checkpoint, dict) and "model_state" in checkpoint:
            state_dict = checkpoint["model_state"]
        else:
            state_dict = checkpoint
            
        # Load weights into the model
        model.load_state_dict(state_dict)
        model.eval()
        
        # 4. Run Inference
        with torch.no_grad():
            # Model returns logits (x) and a heatmap (x_hm). We ignore the heatmap.
            predictions, _ = model(ms_tct_input) 

    except Exception as e:
        print(f"Error running MS-TCT: {e}")
        return [{"label": f"MS-TCT failed to run: {e}", "confidence": None}]

    # 5. Automatically load all 157 Charades class text labels
    charades_classes = {}
    classes_path = os.path.join(os.path.dirname(__file__), 'MS-TCT', 'Charades_v1_classes.txt')

    # Download the official classes file if we don't have it yet
    if not os.path.exists(classes_path):
        import urllib.request
        print("Downloading official Charades class labels...")
        try:
            url = "https://raw.githubusercontent.com/gsig/charades-algorithms/master/data/Charades_v1_classes.txt"
            urllib.request.urlretrieve(url, classes_path)
        except Exception as e:
            print(f"Failed to download classes: {e}")

    # Parse the text file into our dictionary
    try:
        with open(classes_path, 'r') as f:
            for line in f:
                # Example line: "c011 Putting a book somewhere"
                parts = line.strip().split(' ', 1)
                if len(parts) == 2:
                    class_id = int(parts[0].replace('c', '')) # converts 'c011' -> 11
                    charades_classes[class_id] = parts[1]
    except Exception as e:
        print(f"Warning: Could not read classes file: {e}")

    probabilities = torch.softmax(predictions.squeeze(0), dim=-1)
    if probabilities.dim() == 1:
        probabilities = probabilities.unsqueeze(0)

    if probabilities.shape[0] == 0:
        return []

    averaged_probabilities = probabilities.mean(dim=0)
    prediction_count = min(top_k, averaged_probabilities.shape[0])
    top_probabilities, top_indices = torch.topk(averaged_probabilities, k=prediction_count)

    results = []
    for probability, class_idx in zip(top_probabilities, top_indices):
        class_id = class_idx.item()
        action_name = charades_classes.get(class_id, f"Charades Action c{class_id:03d}")
        results.append({
            "label": action_name,
            "confidence": round(float(probability.item()) * 100, 2),
        })

    return results


def process_video_pipeline(video_path, top_k=5, stop_event=None):
    """Main orchestration function called by server.py."""
    if stop_event and stop_event.is_set():
        print("Skipping pipeline because the stream was stopped before feature extraction.")
        return []

    print("1. Extracting I3D features...")
    features = extract_features(video_path)

    if stop_event and stop_event.is_set():
        print("Skipping MS-TCT inference because the stream was stopped after feature extraction.")
        return []
    
    print("2. Running MS-TCT inference...")
    results = run_ms_tct(features, top_k=top_k)
    
    return results


def format_segment_label(start_seconds, end_seconds):
    """Build human-readable labels for streamed clip intervals."""
    rounded_start = int(round(start_seconds))
    rounded_end = max(int(round(end_seconds)), rounded_start)

    if rounded_start <= 0:
        return f"First {rounded_end} seconds"

    return f"Next {max(rounded_end - rounded_start, 1)} seconds ({rounded_start}s-{rounded_end}s)"


def stream_capture_intervals(stream_url, interval_seconds=15, target_size=224, stop_event=None):
    """Capture a live stream in fixed intervals and run the existing pipeline per chunk."""
    cap = cv2.VideoCapture(stream_url)
    if not cap.isOpened():
        raise ValueError("Could not open the provided video stream.")

    fps = cap.get(cv2.CAP_PROP_FPS)
    if not fps or fps <= 0:
        fps = 30.0

    frames_per_interval = max(int(fps * interval_seconds), 1)
    stream_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or target_size
    stream_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or target_size
    interval_index = 0
    frames = []

    try:
        while True:
            if stop_event and stop_event.is_set():
                print("Stopping stream capture because the client disconnected.")
                break

            ret, frame = cap.read()
            if not ret:
                break

            frames.append(frame)

            if len(frames) < frames_per_interval:
                continue

            if stop_event and stop_event.is_set():
                print("Skipping interval processing because the client disconnected.")
                break

            interval_index += 1
            yield _process_stream_interval(
                frames=frames,
                fps=fps,
                width=stream_width,
                height=stream_height,
                interval_index=interval_index,
                interval_seconds=interval_seconds,
                stop_event=stop_event,
            )
            frames = []

        if frames and not (stop_event and stop_event.is_set()):
            interval_index += 1
            yield _process_stream_interval(
                frames=frames,
                fps=fps,
                width=stream_width,
                height=stream_height,
                interval_index=interval_index,
                interval_seconds=interval_seconds,
                is_partial=True,
                stop_event=stop_event,
            )
    finally:
        cap.release()


def _process_stream_interval(
    frames,
    fps,
    width,
    height,
    interval_index,
    interval_seconds,
    is_partial=False,
    stop_event=None,
):
    """Write one captured interval to disk temporarily and reuse the video pipeline."""
    temp_video_path = None

    try:
        if stop_event and stop_event.is_set():
            return {
                "message": f"Stopped before processing interval {interval_index}.",
                "actions": [],
            }

        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_video:
            temp_video_path = temp_video.name

        writer = cv2.VideoWriter(
            temp_video_path,
            cv2.VideoWriter_fourcc(*"mp4v"),
            fps,
            (width, height),
        )

        if not writer.isOpened():
            raise ValueError("Could not create a temporary video file for stream processing.")

        try:
            for frame in frames:
                if frame.shape[1] != width or frame.shape[0] != height:
                    frame = cv2.resize(frame, (width, height))
                writer.write(frame)
        finally:
            writer.release()

        clip_duration_seconds = len(frames) / fps if fps > 0 else interval_seconds
        interval_start_seconds = (interval_index - 1) * interval_seconds
        interval_end_seconds = interval_start_seconds + clip_duration_seconds
        actions = process_video_pipeline(temp_video_path, stop_event=stop_event)
        interval_label = "partial interval" if is_partial else "interval"
        segment_label = format_segment_label(interval_start_seconds, interval_end_seconds)

        for action in actions:
            action["segmentLabel"] = segment_label
            action["intervalIndex"] = interval_index

        return {
            "message": f"Processed {interval_label} {interval_index} (~{interval_seconds} seconds).",
            "actions": actions,
            "segmentLabel": segment_label,
        }
    except Exception as e:
        return {
            "message": f"Failed to process stream interval {interval_index}.",
            "error": str(e),
            "actions": [],
        }
    finally:
        if temp_video_path and os.path.exists(temp_video_path):
            os.remove(temp_video_path)
