"""
Image Comparison Module for Satellite Monitoring

Provides functions to compare satellite images and detect changes over time.
Uses multiple algorithms for robust change detection:
- SSIM (Structural Similarity Index)
- Histogram comparison
- Pixel-level difference
- Contour detection for change areas
"""

import cv2
import numpy as np
from dataclasses import dataclass
from typing import Optional, List, Tuple, Dict
from datetime import datetime
from pathlib import Path
import base64
from enum import Enum


class ChangeType(str, Enum):
    """Types of detected changes."""
    CONSTRUCTION = "construction"
    VEGETATION = "vegetation"
    WATER = "water"
    DEFORESTATION = "deforestation"
    URBAN_EXPANSION = "urban_expansion"
    AGRICULTURAL = "agricultural"
    UNKNOWN = "unknown"


class ChangeSeverity(str, Enum):
    """Severity levels for detected changes."""
    MINIMAL = "minimal"      # < 5%
    LOW = "low"              # 5-15%
    MODERATE = "moderate"    # 15-30%
    SIGNIFICANT = "significant"  # 30-50%
    CRITICAL = "critical"    # > 50%


@dataclass
class ChangeRegion:
    """Represents a detected change region."""
    x: int
    y: int
    width: int
    height: int
    area: int
    change_percent: float
    centroid: Tuple[int, int]


@dataclass
class ComparisonResult:
    """Complete result of image comparison."""
    overall_change_percent: float
    ssim_score: float
    histogram_correlation: float
    pixel_diff_percent: float
    change_regions: List[ChangeRegion]
    severity: ChangeSeverity
    suggested_change_type: ChangeType
    diff_image_base64: Optional[str] = None
    heatmap_base64: Optional[str] = None
    overlay_base64: Optional[str] = None
    analysis_timestamp: str = ""
    recommendations: List[str] = None
    
    def __post_init__(self):
        if self.analysis_timestamp == "":
            self.analysis_timestamp = datetime.now().isoformat()
        if self.recommendations is None:
            self.recommendations = []


class ImageComparator:
    """
    Compares satellite images to detect changes.
    Optimized for CPU processing.
    """
    
    def __init__(self, min_contour_area: int = 500, blur_kernel: int = 5):
        """
        Initialize the comparator.
        
        Args:
            min_contour_area: Minimum area for a change region to be considered
            blur_kernel: Kernel size for Gaussian blur (noise reduction)
        """
        self.min_contour_area = min_contour_area
        self.blur_kernel = blur_kernel
        print("🔍 ImageComparator initialized")
    
    def _preprocess_image(self, image: np.ndarray) -> np.ndarray:
        """Preprocess image for comparison."""
        # Convert to grayscale if color
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image
        
        # Apply Gaussian blur to reduce noise
        blurred = cv2.GaussianBlur(gray, (self.blur_kernel, self.blur_kernel), 0)
        
        return blurred
    
    def _resize_to_match(self, img1: np.ndarray, img2: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Resize images to match dimensions."""
        h1, w1 = img1.shape[:2]
        h2, w2 = img2.shape[:2]
        
        if h1 != h2 or w1 != w2:
            # Use the smaller dimensions
            target_h = min(h1, h2)
            target_w = min(w1, w2)
            img1 = cv2.resize(img1, (target_w, target_h))
            img2 = cv2.resize(img2, (target_w, target_h))
        
        return img1, img2
    
    def calculate_ssim(self, img1: np.ndarray, img2: np.ndarray) -> float:
        """
        Calculate Structural Similarity Index (SSIM).
        
        Returns value between -1 and 1, where 1 means identical images.
        """
        # Preprocess
        gray1 = self._preprocess_image(img1)
        gray2 = self._preprocess_image(img2)
        gray1, gray2 = self._resize_to_match(gray1, gray2)
        
        # Calculate SSIM using OpenCV
        C1 = (0.01 * 255) ** 2
        C2 = (0.03 * 255) ** 2
        
        img1_f = gray1.astype(np.float64)
        img2_f = gray2.astype(np.float64)
        
        mu1 = cv2.GaussianBlur(img1_f, (11, 11), 1.5)
        mu2 = cv2.GaussianBlur(img2_f, (11, 11), 1.5)
        
        mu1_sq = mu1 ** 2
        mu2_sq = mu2 ** 2
        mu1_mu2 = mu1 * mu2
        
        sigma1_sq = cv2.GaussianBlur(img1_f ** 2, (11, 11), 1.5) - mu1_sq
        sigma2_sq = cv2.GaussianBlur(img2_f ** 2, (11, 11), 1.5) - mu2_sq
        sigma12 = cv2.GaussianBlur(img1_f * img2_f, (11, 11), 1.5) - mu1_mu2
        
        ssim_map = ((2 * mu1_mu2 + C1) * (2 * sigma12 + C2)) / \
                   ((mu1_sq + mu2_sq + C1) * (sigma1_sq + sigma2_sq + C2))
        
        return float(np.mean(ssim_map))
    
    def calculate_histogram_correlation(self, img1: np.ndarray, img2: np.ndarray) -> float:
        """
        Calculate histogram correlation between images.
        
        Returns value between -1 and 1, where 1 means identical histograms.
        """
        # Convert to HSV for better color comparison
        if len(img1.shape) == 3:
            hsv1 = cv2.cvtColor(img1, cv2.COLOR_BGR2HSV)
            hsv2 = cv2.cvtColor(img2, cv2.COLOR_BGR2HSV)
        else:
            hsv1 = img1
            hsv2 = img2
        
        hsv1, hsv2 = self._resize_to_match(hsv1, hsv2)
        
        # Calculate histograms
        hist_size = [50, 60]
        ranges = [0, 180, 0, 256]
        channels = [0, 1]
        
        hist1 = cv2.calcHist([hsv1], channels, None, hist_size, ranges)
        hist2 = cv2.calcHist([hsv2], channels, None, hist_size, ranges)
        
        cv2.normalize(hist1, hist1, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)
        cv2.normalize(hist2, hist2, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)
        
        correlation = cv2.compareHist(hist1, hist2, cv2.HISTCMP_CORREL)
        
        return float(correlation)
    
    def calculate_pixel_difference(self, img1: np.ndarray, img2: np.ndarray, 
                                   threshold: int = 30) -> Tuple[float, np.ndarray]:
        """
        Calculate pixel-level difference percentage.
        
        Args:
            threshold: Minimum difference value to consider a pixel as "changed"
        
        Returns:
            Tuple of (percentage of changed pixels, difference mask)
        """
        gray1 = self._preprocess_image(img1)
        gray2 = self._preprocess_image(img2)
        gray1, gray2 = self._resize_to_match(gray1, gray2)
        
        # Calculate absolute difference
        diff = cv2.absdiff(gray1, gray2)
        
        # Apply threshold to get binary mask of changes
        _, thresh = cv2.threshold(diff, threshold, 255, cv2.THRESH_BINARY)
        
        # Calculate percentage of changed pixels
        total_pixels = thresh.shape[0] * thresh.shape[1]
        changed_pixels = np.count_nonzero(thresh)
        change_percent = (changed_pixels / total_pixels) * 100
        
        return change_percent, thresh
    
    def detect_change_regions(self, img1: np.ndarray, img2: np.ndarray,
                              threshold: int = 30) -> List[ChangeRegion]:
        """
        Detect and locate specific regions of change.
        
        Returns list of ChangeRegion objects with bounding boxes.
        """
        _, diff_mask = self.calculate_pixel_difference(img1, img2, threshold)
        
        # Morphological operations to clean up noise
        kernel = np.ones((5, 5), np.uint8)
        diff_mask = cv2.morphologyEx(diff_mask, cv2.MORPH_CLOSE, kernel)
        diff_mask = cv2.morphologyEx(diff_mask, cv2.MORPH_OPEN, kernel)
        
        # Find contours
        contours, _ = cv2.findContours(diff_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        regions = []
        total_image_area = diff_mask.shape[0] * diff_mask.shape[1]
        
        for contour in contours:
            area = cv2.contourArea(contour)
            if area >= self.min_contour_area:
                x, y, w, h = cv2.boundingRect(contour)
                M = cv2.moments(contour)
                
                if M["m00"] > 0:
                    cx = int(M["m10"] / M["m00"])
                    cy = int(M["m01"] / M["m00"])
                else:
                    cx, cy = x + w // 2, y + h // 2
                
                regions.append(ChangeRegion(
                    x=x, y=y, width=w, height=h,
                    area=int(area),
                    change_percent=round((area / total_image_area) * 100, 2),
                    centroid=(cx, cy)
                ))
        
        # Sort by area (largest first)
        regions.sort(key=lambda r: r.area, reverse=True)
        
        return regions
    
    def generate_diff_visualization(self, img1: np.ndarray, img2: np.ndarray,
                                    threshold: int = 30) -> Dict[str, np.ndarray]:
        """
        Generate visualization images for the differences.
        
        Returns dict with:
            - diff: Raw difference image
            - heatmap: Color-coded heatmap of changes
            - overlay: Original image with change highlights
        """
        img1, img2 = self._resize_to_match(img1, img2)
        
        gray1 = self._preprocess_image(img1)
        gray2 = self._preprocess_image(img2)
        
        # Raw difference
        diff = cv2.absdiff(gray1, gray2)
        
        # Heatmap
        heatmap = cv2.applyColorMap(diff, cv2.COLORMAP_JET)
        
        # Overlay - highlight changes on the newer image
        _, thresh = cv2.threshold(diff, threshold, 255, cv2.THRESH_BINARY)
        
        # Create colored overlay
        if len(img2.shape) == 3:
            overlay = img2.copy()
        else:
            overlay = cv2.cvtColor(img2, cv2.COLOR_GRAY2BGR)
        
        # Create red mask for changes
        red_mask = np.zeros_like(overlay)
        red_mask[:, :, 2] = thresh  # Red channel
        
        # Blend overlay
        overlay = cv2.addWeighted(overlay, 0.7, red_mask, 0.3, 0)
        
        # Draw contours
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(overlay, contours, -1, (0, 255, 255), 2)  # Yellow contours
        
        return {
            "diff": diff,
            "heatmap": heatmap,
            "overlay": overlay
        }
    
    def _determine_severity(self, change_percent: float) -> ChangeSeverity:
        """Determine change severity based on percentage."""
        if change_percent < 5:
            return ChangeSeverity.MINIMAL
        elif change_percent < 15:
            return ChangeSeverity.LOW
        elif change_percent < 30:
            return ChangeSeverity.MODERATE
        elif change_percent < 50:
            return ChangeSeverity.SIGNIFICANT
        else:
            return ChangeSeverity.CRITICAL
    
    def _suggest_change_type(self, regions: List[ChangeRegion], 
                             img1: np.ndarray, img2: np.ndarray) -> ChangeType:
        """
        Suggest the type of change based on image analysis.
        This is a basic heuristic - for accurate classification, use VLM.
        """
        if not regions:
            return ChangeType.UNKNOWN
        
        # Analyze color changes in largest region
        largest = regions[0]
        
        # Extract regions from both images
        img1, img2 = self._resize_to_match(img1, img2)
        
        roi1 = img1[largest.y:largest.y+largest.height, 
                    largest.x:largest.x+largest.width]
        roi2 = img2[largest.y:largest.y+largest.height,
                    largest.x:largest.x+largest.width]
        
        if roi1.size == 0 or roi2.size == 0:
            return ChangeType.UNKNOWN
        
        # Convert to HSV for color analysis
        if len(roi1.shape) == 3:
            hsv1 = cv2.cvtColor(roi1, cv2.COLOR_BGR2HSV)
            hsv2 = cv2.cvtColor(roi2, cv2.COLOR_BGR2HSV)
            
            # Analyze color shifts
            mean_h1, mean_s1, mean_v1 = np.mean(hsv1, axis=(0, 1))
            mean_h2, mean_s2, mean_v2 = np.mean(hsv2, axis=(0, 1))
            
            # Green to brown = potential deforestation
            if mean_h1 > 35 and mean_h1 < 85 and mean_h2 < 30:
                return ChangeType.DEFORESTATION
            
            # Brown/gray to gray = potential construction
            if mean_s2 < mean_s1 and mean_v2 > mean_v1:
                return ChangeType.CONSTRUCTION
            
            # Blue increase = potential water/flooding
            if mean_h2 > 90 and mean_h2 < 130:
                return ChangeType.WATER
            
            # Green increase = vegetation growth
            if mean_h2 > 35 and mean_h2 < 85 and mean_s2 > mean_s1:
                return ChangeType.VEGETATION
        
        return ChangeType.UNKNOWN
    
    def _generate_recommendations(self, severity: ChangeSeverity, 
                                  change_type: ChangeType,
                                  change_percent: float) -> List[str]:
        """Generate actionable recommendations based on analysis."""
        recommendations = []
        
        # Severity-based recommendations
        if severity in [ChangeSeverity.SIGNIFICANT, ChangeSeverity.CRITICAL]:
            recommendations.append("⚠️ Se detectaron cambios significativos. Se recomienda revisión inmediata.")
            recommendations.append("📸 Considere solicitar una imagen de mayor resolución para verificar.")
        
        if severity == ChangeSeverity.CRITICAL:
            recommendations.append("🚨 ALERTA CRÍTICA: Más del 50% del área monitoreada ha cambiado.")
        
        # Type-based recommendations
        type_recommendations = {
            ChangeType.CONSTRUCTION: [
                "🏗️ Posible actividad de construcción detectada.",
                "Verifique si existe permiso de obra para esta zona.",
                "Considere inspección presencial si es área protegida."
            ],
            ChangeType.DEFORESTATION: [
                "🌲 Posible deforestación detectada.",
                "Se recomienda alerta a autoridades ambientales.",
                "Documente con imágenes de alta resolución."
            ],
            ChangeType.WATER: [
                "💧 Cambios en cuerpos de agua detectados.",
                "Posible inundación o cambio en nivel de agua.",
                "Verifique condiciones meteorológicas recientes."
            ],
            ChangeType.VEGETATION: [
                "🌿 Cambios en vegetación detectados.",
                "Puede ser crecimiento estacional o intervención agrícola."
            ],
            ChangeType.AGRICULTURAL: [
                "🚜 Posible actividad agrícola detectada.",
                "Verifique calendario de siembra/cosecha."
            ],
            ChangeType.URBAN_EXPANSION: [
                "🏙️ Posible expansión urbana detectada.",
                "Verifique planes de desarrollo urbano."
            ]
        }
        
        if change_type in type_recommendations:
            recommendations.extend(type_recommendations[change_type])
        
        # Always suggest VLM for detailed analysis
        if change_percent > 5:
            recommendations.append("🤖 Use 'Analizar con IA' para obtener una interpretación detallada.")
        
        return recommendations
    
    def compare(self, img1: np.ndarray, img2: np.ndarray,
                generate_visuals: bool = True,
                threshold: int = 30) -> ComparisonResult:
        """
        Perform complete comparison between two images.
        
        Args:
            img1: Previous/baseline image (numpy array or path)
            img2: Current/new image (numpy array or path)
            generate_visuals: Whether to generate visualization images
            threshold: Pixel difference threshold
        
        Returns:
            ComparisonResult with all analysis data
        """
        print(f"🔍 Comparing images...")
        
        # Calculate metrics
        ssim = self.calculate_ssim(img1, img2)
        hist_corr = self.calculate_histogram_correlation(img1, img2)
        pixel_diff, _ = self.calculate_pixel_difference(img1, img2, threshold)
        
        # Detect change regions
        regions = self.detect_change_regions(img1, img2, threshold)
        
        # Calculate overall change (weighted average)
        # SSIM and histogram correlation are inverted (1 = same, 0 = different)
        ssim_change = (1 - ssim) * 100
        hist_change = (1 - hist_corr) * 100 if hist_corr > 0 else 100
        
        overall_change = (pixel_diff * 0.5 + ssim_change * 0.3 + hist_change * 0.2)
        overall_change = min(100, max(0, overall_change))
        
        # Determine severity and type
        severity = self._determine_severity(overall_change)
        change_type = self._suggest_change_type(regions, img1, img2)
        
        # Generate recommendations
        recommendations = self._generate_recommendations(severity, change_type, overall_change)
        
        # Generate visualizations
        diff_b64 = None
        heatmap_b64 = None
        overlay_b64 = None
        
        if generate_visuals:
            visuals = self.generate_diff_visualization(img1, img2, threshold)
            
            # Encode to base64
            _, diff_encoded = cv2.imencode('.jpg', visuals['diff'])
            diff_b64 = base64.b64encode(diff_encoded).decode('utf-8')
            
            _, heatmap_encoded = cv2.imencode('.jpg', visuals['heatmap'])
            heatmap_b64 = base64.b64encode(heatmap_encoded).decode('utf-8')
            
            _, overlay_encoded = cv2.imencode('.jpg', visuals['overlay'])
            overlay_b64 = base64.b64encode(overlay_encoded).decode('utf-8')
        
        result = ComparisonResult(
            overall_change_percent=round(overall_change, 2),
            ssim_score=round(ssim, 4),
            histogram_correlation=round(hist_corr, 4),
            pixel_diff_percent=round(pixel_diff, 2),
            change_regions=regions,
            severity=severity,
            suggested_change_type=change_type,
            diff_image_base64=diff_b64,
            heatmap_base64=heatmap_b64,
            overlay_base64=overlay_b64,
            recommendations=recommendations
        )
        
        print(f"✅ Comparison complete: {overall_change:.1f}% change, severity: {severity.value}")
        
        return result
    
    def compare_from_paths(self, path1: str, path2: str, **kwargs) -> ComparisonResult:
        """Compare images from file paths."""
        img1 = cv2.imread(path1)
        img2 = cv2.imread(path2)
        
        if img1 is None:
            raise ValueError(f"Could not load image: {path1}")
        if img2 is None:
            raise ValueError(f"Could not load image: {path2}")
        
        return self.compare(img1, img2, **kwargs)
    
    def compare_from_base64(self, b64_1: str, b64_2: str, **kwargs) -> ComparisonResult:
        """Compare images from base64 strings."""
        # Decode base64
        img_data1 = base64.b64decode(b64_1)
        img_data2 = base64.b64decode(b64_2)
        
        # Convert to numpy arrays
        nparr1 = np.frombuffer(img_data1, np.uint8)
        nparr2 = np.frombuffer(img_data2, np.uint8)
        
        img1 = cv2.imdecode(nparr1, cv2.IMREAD_COLOR)
        img2 = cv2.imdecode(nparr2, cv2.IMREAD_COLOR)
        
        if img1 is None or img2 is None:
            raise ValueError("Could not decode one or both base64 images")
        
        return self.compare(img1, img2, **kwargs)


# Singleton instance for use in worker
_comparator_instance: Optional[ImageComparator] = None


def get_comparator() -> ImageComparator:
    """Get or create the ImageComparator singleton."""
    global _comparator_instance
    if _comparator_instance is None:
        _comparator_instance = ImageComparator()
    return _comparator_instance


# Convenience functions
def compare_images(img1: np.ndarray, img2: np.ndarray, **kwargs) -> ComparisonResult:
    """Quick comparison function."""
    return get_comparator().compare(img1, img2, **kwargs)


def compare_images_from_paths(path1: str, path2: str, **kwargs) -> ComparisonResult:
    """Quick comparison from file paths."""
    return get_comparator().compare_from_paths(path1, path2, **kwargs)


def compare_images_from_base64(b64_1: str, b64_2: str, **kwargs) -> ComparisonResult:
    """Quick comparison from base64 strings."""
    return get_comparator().compare_from_base64(b64_1, b64_2, **kwargs)
