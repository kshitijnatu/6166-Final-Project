import torch
import cv2
import numpy as np
import sys
import os
import pickle

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


def run_ms_tct(features, weights_filename="charades_model.pth"):
    """Runs the MS-TCT action segmentation model on the extracted features."""
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
            # Model returns predictions (x) and a heatmap (x_hm). We ignore the heatmap.
            predictions, _ = model(ms_tct_input) 
            
            # Get the highest scoring class for each time step across the classes dimension
            predicted_classes = torch.argmax(predictions, dim=-1).squeeze()
            
            # Handle edge case for very short videos
            if predicted_classes.dim() == 0:
                predicted_classes = predicted_classes.unsqueeze(0)
                
    except Exception as e:
        print(f"Error running MS-TCT: {e}")
        return [{"time": "Error", "label": f"MS-TCT failed to run: {e}"}]

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

    results = []
    
    # 6. Format the output for the React frontend
    for i, class_idx in enumerate(predicted_classes):
        # Temporal downsampling estimate: ~0.5s per chunk for standard video
        seconds = i * 0.5 
        class_id = class_idx.item()
        
        # Get text label, fallback to generic ID if not in the dictionary
        action_name = charades_classes.get(class_id, f"Charades Action c{class_id:03d}")
        
        # Format time to mm:ss.s
        mins = int(seconds // 60)
        secs = seconds % 60
        time_str = f"{mins:02d}:{secs:04.1f}"

        results.append({
            "time": time_str, 
            "label": action_name
        })
        
    return results


def process_video_pipeline(video_path):
    """Main orchestration function called by server.py."""
    print("1. Extracting I3D features...")
    features = extract_features(video_path)
    
    print("2. Running MS-TCT inference...")
    results = run_ms_tct(features)
    
    return results