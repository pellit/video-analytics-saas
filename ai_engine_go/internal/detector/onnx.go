package detector

import (
	"fmt"
	"image"
	"image/color"
	"math"
	"path/filepath"
	"sort"
	"strings"

	ort "github.com/yalue/onnxruntime_go"
)

// Detection represents a single object detection
type Detection struct {
	ClassID    int       `json:"class_id"`
	ClassName  string    `json:"class_name"`
	Confidence float32   `json:"confidence"`
	BBox       [4]int    `json:"bbox"` // x1, y1, x2, y2
}

// ONNXDetector handles ONNX model inference
type ONNXDetector struct {
	session      *ort.AdvancedSession
	inputTensor  *ort.Tensor[float32]
	outputTensor *ort.Tensor[float32]
	inputShape   []int64
	modelName    string
	classNames   []string
	threshold    float32
	nmsThreshold float32
}

// COCO class names
var cocoClasses = []string{
	"person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat",
	"traffic light", "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat",
	"dog", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe", "backpack",
	"umbrella", "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball",
	"kite", "baseball bat", "baseball glove", "skateboard", "surfboard", "tennis racket",
	"bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple",
	"sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair",
	"couch", "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse",
	"remote", "keyboard", "cell phone", "microwave", "oven", "toaster", "sink", "refrigerator",
	"book", "clock", "vase", "scissors", "teddy bear", "hair drier", "toothbrush",
}

// NewONNXDetector creates a new ONNX detector
func NewONNXDetector(modelPath string) (*ONNXDetector, error) {
	// Initialize ONNX Runtime
	if err := ort.InitializeEnvironment(); err != nil {
		return nil, fmt.Errorf("failed to initialize ONNX Runtime: %w", err)
	}

	// Get model name from path
	modelName := strings.TrimSuffix(filepath.Base(modelPath), filepath.Ext(modelPath))

	// Input shape for YOLOv8 nano: [1, 3, 640, 640]
	inputShape := ort.NewShape(1, 3, 640, 640)
	inputTensor, err := ort.NewEmptyTensor[float32](inputShape)
	if err != nil {
		return nil, fmt.Errorf("failed to create input tensor: %w", err)
	}

	// Output shape: [1, 84, 8400] for YOLOv8
	outputShape := ort.NewShape(1, 84, 8400)
	outputTensor, err := ort.NewEmptyTensor[float32](outputShape)
	if err != nil {
		inputTensor.Destroy()
		return nil, fmt.Errorf("failed to create output tensor: %w", err)
	}

	// Create advanced session
	session, err := ort.NewAdvancedSession(
		modelPath,
		[]string{"images"},
		[]string{"output0"},
		[]ort.ArbitraryTensor{inputTensor},
		[]ort.ArbitraryTensor{outputTensor},
		nil, // Use default options
	)
	if err != nil {
		inputTensor.Destroy()
		outputTensor.Destroy()
		return nil, fmt.Errorf("failed to create session: %w", err)
	}

	return &ONNXDetector{
		session:      session,
		inputTensor:  inputTensor,
		outputTensor: outputTensor,
		inputShape:   []int64{1, 3, 640, 640},
		modelName:    modelName,
		classNames:   cocoClasses,
		threshold:    0.25,
		nmsThreshold: 0.45,
	}, nil
}

// Close releases resources
func (d *ONNXDetector) Close() {
	if d.session != nil {
		d.session.Destroy()
	}
	if d.inputTensor != nil {
		d.inputTensor.Destroy()
	}
	if d.outputTensor != nil {
		d.outputTensor.Destroy()
	}
	ort.DestroyEnvironment()
}

// ModelName returns the model name
func (d *ONNXDetector) ModelName() string {
	return d.modelName
}

// SetThreshold sets the detection threshold
func (d *ONNXDetector) SetThreshold(threshold float32) {
	d.threshold = threshold
}

// Detect runs inference on an image
func (d *ONNXDetector) Detect(img image.Image) ([]Detection, error) {
	// Preprocess image
	inputData := d.preprocess(img)

	// Copy data to input tensor
	inputSlice := d.inputTensor.GetData()
	copy(inputSlice, inputData)

	// Run inference
	if err := d.session.Run(); err != nil {
		return nil, fmt.Errorf("inference failed: %w", err)
	}

	// Get output data
	outputData := d.outputTensor.GetData()

	// Postprocess results
	detections := d.postprocess(outputData, img.Bounds().Dx(), img.Bounds().Dy())

	return detections, nil
}

// preprocess converts image to NCHW float32 tensor normalized to [0, 1]
func (d *ONNXDetector) preprocess(img image.Image) []float32 {
	targetW := int(d.inputShape[3])
	targetH := int(d.inputShape[2])
	
	// Resize image
	resized := resizeImage(img, targetW, targetH)
	
	// Convert to NCHW format and normalize
	size := targetW * targetH
	data := make([]float32, 3*size)
	
	for y := 0; y < targetH; y++ {
		for x := 0; x < targetW; x++ {
			r, g, b, _ := resized.At(x, y).RGBA()
			idx := y*targetW + x
			data[idx] = float32(r>>8) / 255.0         // R channel
			data[size+idx] = float32(g>>8) / 255.0   // G channel
			data[2*size+idx] = float32(b>>8) / 255.0 // B channel
		}
	}
	
	return data
}

// resizeImage resizes an image using simple nearest-neighbor (fast)
func resizeImage(img image.Image, targetW, targetH int) image.Image {
	bounds := img.Bounds()
	srcW := bounds.Dx()
	srcH := bounds.Dy()
	
	dst := image.NewRGBA(image.Rect(0, 0, targetW, targetH))
	
	xRatio := float64(srcW) / float64(targetW)
	yRatio := float64(srcH) / float64(targetH)
	
	for y := 0; y < targetH; y++ {
		for x := 0; x < targetW; x++ {
			srcX := int(float64(x) * xRatio)
			srcY := int(float64(y) * yRatio)
			dst.Set(x, y, img.At(bounds.Min.X+srcX, bounds.Min.Y+srcY))
		}
	}
	
	return dst
}

// postprocess converts raw output to detections
func (d *ONNXDetector) postprocess(output []float32, imgWidth, imgHeight int) []Detection {
	// YOLOv8 output: [1, 84, 8400]
	// 84 = 4 (bbox) + 80 (class scores)
	// 8400 = number of predictions
	
	numClasses := 80
	numPredictions := 8400
	targetW := int(d.inputShape[3])
	targetH := int(d.inputShape[2])
	
	scaleX := float32(imgWidth) / float32(targetW)
	scaleY := float32(imgHeight) / float32(targetH)
	
	var candidates []Detection
	
	for i := 0; i < numPredictions; i++ {
		// Get bbox (center format)
		cx := output[i]
		cy := output[numPredictions+i]
		w := output[2*numPredictions+i]
		h := output[3*numPredictions+i]
		
		// Get class scores
		maxScore := float32(0)
		maxClass := 0
		for c := 0; c < numClasses; c++ {
			score := output[(4+c)*numPredictions+i]
			if score > maxScore {
				maxScore = score
				maxClass = c
			}
		}
		
		if maxScore < d.threshold {
			continue
		}
		
		// Convert from center to corner format and scale to original image
		x1 := int((cx - w/2) * scaleX)
		y1 := int((cy - h/2) * scaleY)
		x2 := int((cx + w/2) * scaleX)
		y2 := int((cy + h/2) * scaleY)
		
		// Clamp to image bounds
		x1 = maxInt(0, minInt(x1, imgWidth-1))
		y1 = maxInt(0, minInt(y1, imgHeight-1))
		x2 = maxInt(0, minInt(x2, imgWidth-1))
		y2 = maxInt(0, minInt(y2, imgHeight-1))
		
		className := "unknown"
		if maxClass < len(d.classNames) {
			className = d.classNames[maxClass]
		}
		
		candidates = append(candidates, Detection{
			ClassID:    maxClass,
			ClassName:  className,
			Confidence: maxScore,
			BBox:       [4]int{x1, y1, x2, y2},
		})
	}
	
	// Apply NMS
	return d.nms(candidates)
}

// nms applies Non-Maximum Suppression
func (d *ONNXDetector) nms(detections []Detection) []Detection {
	if len(detections) == 0 {
		return detections
	}
	
	// Sort by confidence (descending)
	sort.Slice(detections, func(i, j int) bool {
		return detections[i].Confidence > detections[j].Confidence
	})
	
	var result []Detection
	used := make([]bool, len(detections))
	
	for i := range detections {
		if used[i] {
			continue
		}
		
		result = append(result, detections[i])
		
		for j := i + 1; j < len(detections); j++ {
			if used[j] {
				continue
			}
			
			if iou(detections[i].BBox, detections[j].BBox) > d.nmsThreshold {
				used[j] = true
			}
		}
	}
	
	return result
}

// iou calculates Intersection over Union
func iou(box1, box2 [4]int) float32 {
	x1 := maxInt(box1[0], box2[0])
	y1 := maxInt(box1[1], box2[1])
	x2 := minInt(box1[2], box2[2])
	y2 := minInt(box1[3], box2[3])
	
	if x2 <= x1 || y2 <= y1 {
		return 0
	}
	
	intersection := float32((x2 - x1) * (y2 - y1))
	area1 := float32((box1[2] - box1[0]) * (box1[3] - box1[1]))
	area2 := float32((box2[2] - box2[0]) * (box2[3] - box2[1]))
	union := area1 + area2 - intersection
	
	if union == 0 {
		return 0
	}
	
	return intersection / union
}

// DrawDetections draws bounding boxes on an image
func (d *ONNXDetector) DrawDetections(img *image.RGBA, detections []Detection) {
	for _, det := range detections {
		c := getColorForClass(det.ClassID)
		drawRect(img, det.BBox, c, 2)
		
		label := fmt.Sprintf("%s: %.1f%%", det.ClassName, det.Confidence*100)
		drawLabel(img, det.BBox[0], det.BBox[1]-12, label, c)
	}
}

func getColorForClass(classID int) color.RGBA {
	colors := []color.RGBA{
		{255, 0, 0, 255},     // Red
		{0, 255, 0, 255},     // Green
		{0, 0, 255, 255},     // Blue
		{255, 255, 0, 255},   // Yellow
		{255, 0, 255, 255},   // Magenta
		{0, 255, 255, 255},   // Cyan
		{255, 128, 0, 255},   // Orange
		{128, 0, 255, 255},   // Purple
	}
	return colors[classID%len(colors)]
}

func drawRect(img *image.RGBA, bbox [4]int, c color.RGBA, thickness int) {
	x1, y1, x2, y2 := bbox[0], bbox[1], bbox[2], bbox[3]
	bounds := img.Bounds()
	
	for t := 0; t < thickness; t++ {
		// Top and bottom edges
		for x := x1; x <= x2; x++ {
			if x >= bounds.Min.X && x < bounds.Max.X {
				if y1+t >= bounds.Min.Y && y1+t < bounds.Max.Y {
					img.Set(x, y1+t, c)
				}
				if y2-t >= bounds.Min.Y && y2-t < bounds.Max.Y {
					img.Set(x, y2-t, c)
				}
			}
		}
		// Left and right edges
		for y := y1; y <= y2; y++ {
			if y >= bounds.Min.Y && y < bounds.Max.Y {
				if x1+t >= bounds.Min.X && x1+t < bounds.Max.X {
					img.Set(x1+t, y, c)
				}
				if x2-t >= bounds.Min.X && x2-t < bounds.Max.X {
					img.Set(x2-t, y, c)
				}
			}
		}
	}
}

func drawLabel(img *image.RGBA, x, y int, label string, bgColor color.RGBA) {
	// Simple text background
	textWidth := len(label) * 7
	textHeight := 12
	
	bounds := img.Bounds()
	
	// Draw background
	for py := y; py < y+textHeight && py < bounds.Max.Y; py++ {
		for px := x; px < x+textWidth && px < bounds.Max.X; px++ {
			if px >= bounds.Min.X && py >= bounds.Min.Y {
				img.Set(px, py, bgColor)
			}
		}
	}
}

func minInt(a, b int) int {
	if a < b {
		return a
	}
	return b
}

func maxInt(a, b int) int {
	if a > b {
		return a
	}
	return b
}

func sqrt(x float32) float32 {
	return float32(math.Sqrt(float64(x)))
}
