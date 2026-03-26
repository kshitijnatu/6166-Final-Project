import torch
import numpy as np
import json
import os
import random
from MSTCT.MSTCT_Model import MSTCT

device = "cuda" if torch.cuda.is_available() else "cpu"

# ---- MODEL CONFIG (same as your script) ----
inter_channels=[256,384,576,864]
num_block=3
head=8
mlp_ratio=8
in_feat_dim=1024
final_embedding_dim=512
num_classes=157

model = MSTCT(
    inter_channels,
    num_block,
    head,
    mlp_ratio,
    in_feat_dim,
    final_embedding_dim,
    num_classes
)

model.load_state_dict(torch.load("./save_logit/mstct_best_model.pth"))
model.to(device)
model.eval()

# ---- PATHS ----
feature_root = "/home/mtrifonov/test-model-2/Charades_i3d_features"
json_file = "./data/charades.json"

# ---- LOAD GROUND TRUTH ----
with open(json_file,"r") as f:
    charades = json.load(f)

all_files = [f.replace(".npy","") for f in os.listdir(feature_root) if f.endswith(".npy")]

# only videos in JSON AND in testing subset
valid_videos = [
    v for v in all_files
    if v in charades and charades[v]["subset"] == "testing"
]

print("Total testing videos available:", len(valid_videos))

sample_videos = random.sample(valid_videos, min(4500, len(valid_videos)))

total_pred_overlap = []
total_gt_overlap = []

for vid in sample_videos:

    # ---- LOAD FEATURES ----
    feat = np.load(os.path.join(feature_root, vid + ".npy"))

    feat = torch.tensor(feat, dtype=torch.float32)

    feat = feat.squeeze(1).squeeze(1)
    feat = feat.permute(1,0)
    feat = feat.unsqueeze(0)
    feat = feat.to(device)

    with torch.no_grad():
        outputs,_ = model(feat)

    probs = torch.sigmoid(outputs)
    video_scores = probs.max(dim=1).values

    threshold = 0.25
    pred = set(torch.where(video_scores[0] > threshold)[0].cpu().numpy().tolist())

    # ---- GROUND TRUTH ----
    gt = set([a[0] for a in charades[vid]["actions"]])

    overlap = pred & gt

    pred_overlap = len(overlap)/len(pred) if len(pred)>0 else 0
    gt_overlap = len(overlap)/len(gt) if len(gt)>0 else 0

    total_pred_overlap.append(pred_overlap)
    total_gt_overlap.append(gt_overlap)

    print(f"{vid}")
    print("Predicted:",sorted(pred))
    print("GroundTruth:",sorted(gt))
    print("Overlap:",sorted(overlap))
    print(f"Intersection(pred) {pred_overlap*100:.2f}%")
    print(f"Intersection(gt)   {gt_overlap*100:.2f}%")
    print()

# ---- FINAL STATS ----
avg_pred = np.mean(total_pred_overlap)*100
avg_gt = np.mean(total_gt_overlap)*100

print("===================================")
print(f"Average overlap vs predictions: {avg_pred:.2f}%")
print(f"Average ground truth coverage:  {avg_gt:.2f}%")
print("===================================")