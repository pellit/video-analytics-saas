import cv2
import numpy as np
from PIL import Image

# Lazy imports for torch/transformers (optional dependencies)
torch = None
pipeline = None

def _load_torch_deps():
    """Load torch and transformers on demand."""
    global torch, pipeline
    if torch is None:
        try:
            import torch as _torch
            from transformers import pipeline as _pipeline
            torch = _torch
            pipeline = _pipeline
            return True
        except ImportError as e:
            print(f"⚠️ Depth estimation requires torch and transformers: {e}")
            print("   Install with: pip install torch torchvision transformers")
            return False
    return True


class DepthService:
    def __init__(self):
        self.pipe = None
        self.device = -1  # Will be set when model loads
        self._available = None  # Will check on first use
        print(f"DepthService initialized (lazy loading)")
    
    def is_available(self) -> bool:
        """Check if depth estimation is available (torch installed)."""
        if self._available is None:
            self._available = _load_torch_deps()
            if self._available and torch is not None:
                self.device = 0 if torch.cuda.is_available() else -1
        return self._available

    def load_model(self):
        if self.pipe is None:
            if not self.is_available():
                print("❌ Cannot load depth model - torch/transformers not installed")
                return False
            print("⏳ Loading Depth Anything V2 model...")
            # Using the small version for performance
            self.pipe = pipeline(task="depth-estimation", model="depth-anything/Depth-Anything-V2-Small-hf", device=self.device)
            print("✅ Depth model loaded.")
        return True

    def estimate_depth(self, frame):
        if self.pipe is None:
            if not self.load_model():
                # Return a dummy depth map if not available
                return np.zeros((frame.shape[0], frame.shape[1]), dtype=np.uint8)
        
        # Convert cv2 frame (BGR) to PIL Image (RGB)
        image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        
        # Inference
        depth = self.pipe(image)["depth"]
        
        # Convert to numpy array (it returns a PIL image of depth)
        depth_map = np.array(depth)
        
        # Resize depth map to match frame size if needed (pipeline usually handles it but returns original size)
        if depth_map.shape[:2] != frame.shape[:2]:
            depth_map = cv2.resize(depth_map, (frame.shape[1], frame.shape[0]))
            
        return depth_map

    def process_3d_view(self, frame, detections, enable_bev=False):
        """
        Draws pseudo-3D boxes on the frame and optionally returns a BEV image.
        detections: list of dicts { 'label': str, 'bbox': [x1, y1, x2, y2], 'score': float, 'track_id': int (optional) }
        Returns: (annotated_frame, bev_map, bev_data)
        bev_data: dict with objects and their positions for frontend rendering
        """
        depth_map = self.estimate_depth(frame)
        
        # Normalize depth map for visualization/calculation (0-255)
        # Depth Anything returns relative depth (inverse depth usually, or metric depending on model)
        # For visualization, we want near objects bright, far objects dark? 
        # Actually Depth Anything usually returns disparity or inverse depth.
        # Let's normalize to 0-1 for calculations.
        
        depth_min = depth_map.min()
        depth_max = depth_map.max()
        # Avoid div by zero
        if depth_max - depth_min == 0:
            depth_norm = depth_map
        else:
            depth_norm = (depth_map - depth_min) / (depth_max - depth_min)

        # Create a color map for depth visualization (optional overlay)
        # depth_colormap = cv2.applyColorMap((depth_norm * 255).astype(np.uint8), cv2.COLORMAP_INFERNO)
        # frame = cv2.addWeighted(frame, 0.7, depth_colormap, 0.3, 0)

        bev_map = None
        bev_data = {'objects': [], 'nearest_distance': float('inf')}
        
        if enable_bev:
            bev_h, bev_w = 500, 500
            bev_map = np.zeros((bev_h, bev_w, 3), dtype=np.uint8)
            # Draw grid
            cv2.line(bev_map, (0, bev_h//2), (bev_w, bev_h//2), (50, 50, 50), 1)
            cv2.line(bev_map, (bev_w//2, 0), (bev_w//2, bev_h), (50, 50, 50), 1)
            cv2.putText(bev_map, "Bird's Eye View", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 1)

        for det in detections:
            bbox = det['bbox'] # [x1, y1, x2, y2]
            x1, y1, x2, y2 = map(int, bbox)
            
            # Clamp coordinates
            h, w = frame.shape[:2]
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)
            
            if x1 >= x2 or y1 >= y2: continue

            # Get depth for this object
            # We take the median depth of the center area of the bbox
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
            w_box, h_box = x2 - x1, y2 - y1
            
            # Sample center region (20% of box)
            sx1 = max(x1, cx - w_box // 10)
            sx2 = min(x2, cx + w_box // 10)
            sy1 = max(y1, cy - h_box // 10)
            sy2 = min(y2, cy + h_box // 10)
            
            obj_depth_region = depth_norm[sy1:sy2, sx1:sx2]
            if obj_depth_region.size == 0:
                obj_depth = 0.5
            else:
                obj_depth = np.median(obj_depth_region)

            # Draw Pseudo-3D Box
            # Depth is 0..1. Let's assume 1 is close, 0 is far (usually).
            # Actually Depth Anything: Higher value = Closer.
            
            # Shift for back face
            # The closer the object, the larger the shift? Or perspective?
            # Simple perspective: vanish point at center image.
            
            img_cx, img_cy = w // 2, h // 2
            
            # Depth factor for shift (arbitrary scaling)
            # If depth is high (close), shift is larger?
            # Let's use a simple factor.
            depth_factor = 0.3 * (1.0 - obj_depth) # Far objects shift less? 
            # Actually, usually we project towards vanishing point.
            
            # Simplified 3D box:
            # Front face: (x1, y1, x2, y2)
            # Back face scale: 
            scale = 0.8 + (0.2 * obj_depth) # Close objects (high depth) -> scale ~ 1. Far -> scale ~ 0.8
            
            # Vector to center
            vx = img_cx - cx
            vy = img_cy - cy
            
            # Back face center
            bx = cx + int(vx * 0.15) # 15% towards center
            by = cy + int(vy * 0.15)
            
            bw = int(w_box * scale)
            bh = int(h_box * scale)
            
            bx1 = bx - bw // 2
            bx2 = bx + bw // 2
            by1 = by - bh // 2
            by2 = by + bh // 2
            
            color = (0, 255, 255) # Yellow
            
            # Draw back face
            cv2.rectangle(frame, (bx1, by1), (bx2, by2), color, 1)
            
            # Draw connectors
            cv2.line(frame, (x1, y1), (bx1, by1), color, 1)
            cv2.line(frame, (x2, y1), (bx2, by1), color, 1)
            cv2.line(frame, (x1, y2), (bx1, by2), color, 1)
            cv2.line(frame, (x2, y2), (bx2, by2), color, 1)
            
            # Draw front face (already drawn by YOLO usually, but we redraw to match style)
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            
            # BEV Plotting
            if enable_bev and bev_map is not None:
                # Map X (screen x) to BEV X
                # Map Depth (0..1) to BEV Y
                
                # Screen X: 0..w -> 0..bev_w
                bev_x = int((cx / w) * bev_w)
                
                # Depth: 1 (Close) -> bev_h (Bottom), 0 (Far) -> 0 (Top)
                # Depth Anything: High = Close.
                # So 1.0 -> y=bev_h, 0.0 -> y=0
                bev_y = int((1.0 - obj_depth) * bev_h)
                
                # Estimate distance in meters (rough approximation)
                # obj_depth is 0-1 where 1 is closest
                # Map to 0-10 meters range (configurable)
                max_distance = 10.0  # metros
                estimated_distance = (1.0 - obj_depth) * max_distance
                
                # X position relative to center (-5m to +5m)
                x_relative = ((cx / w) - 0.5) * max_distance
                
                # Add to BEV data for frontend
                bev_obj = {
                    'label': det['label'],
                    'x': round(x_relative, 2),  # metros desde el centro
                    'distance': round(estimated_distance, 2),  # metros de profundidad
                    'score': det['score'],
                    'trackId': det.get('track_id')
                }
                bev_data['objects'].append(bev_obj)
                
                # Update nearest distance
                if estimated_distance < bev_data['nearest_distance']:
                    bev_data['nearest_distance'] = estimated_distance
                
                # Draw point on BEV map
                cv2.circle(bev_map, (bev_x, bev_y), 5, color, -1)
                label_text = f"{det['label']} {estimated_distance:.1f}m"
                cv2.putText(bev_map, label_text, (bev_x + 5, bev_y), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

        # Convert inf to a large number for JSON serialization
        if bev_data['nearest_distance'] == float('inf'):
            bev_data['nearest_distance'] = 999

        return frame, bev_map, bev_data
