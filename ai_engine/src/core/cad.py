"""
CAD Processing Module - "Architect's Eye"
=========================================

Este módulo convierte archivos CAD (DXF/DWG) en imágenes y los analiza
usando Moondream2 (VLM) para simular el ojo de un experto en arquitectura.

Flujo de trabajo:
1. Recibir archivo CAD (DXF principalmente, DWG convertido)
2. Renderizar a imagen PNG de alta resolución (Rasterización)
3. Analizar con Moondream2 usando prompts especializados
4. Reportar progreso y resultados al backend

Dependencias:
- ezdxf: Lectura y manipulación de archivos DXF
- matplotlib: Renderizado a imagen
- Pillow: Procesamiento de imagen
- opencv-python: Manipulación adicional

Usage:
    from src.core.cad import CADProcessor
    
    processor = CADProcessor(vlm_engine)
    result = processor.process_project(
        file_path='/path/to/plan.dxf',
        project_id=123,
        project_type='architecture',
        callback_fn=update_progress
    )
"""

import os
import json
import cv2
import numpy as np
from PIL import Image
from typing import Optional, Dict, Any, Callable, List, Tuple
from dataclasses import dataclass, asdict
from enum import Enum


class ProjectType(Enum):
    """Tipos de proyecto soportados"""
    ARCHITECTURE = "architecture"
    ENGINEERING = "engineering"
    ELECTRICAL = "electrical"
    PLUMBING = "plumbing"
    STRUCTURAL = "structural"
    HVAC = "hvac"
    LANDSCAPE = "landscape"
    INTERIOR = "interior"
    URBAN = "urban"
    OTHER = "other"


@dataclass
class CADMetadata:
    """Metadata extraída del archivo CAD"""
    layers: List[str]
    block_names: List[str]
    units: str
    extents: Dict[str, float]  # min_x, min_y, max_x, max_y
    entity_count: int
    text_content: List[str]
    dimension_texts: List[str]


@dataclass
class AnalysisResult:
    """Resultado del análisis completo"""
    success: bool
    render_image_path: Optional[str]
    render_thumbnail_path: Optional[str]
    metadata: Optional[Dict[str, Any]]
    analysis_general: Optional[Dict[str, Any]]
    analysis_rooms: Optional[Dict[str, Any]]
    analysis_safety: Optional[Dict[str, Any]]
    analysis_structural: Optional[Dict[str, Any]]
    analysis_dimensions: Optional[Dict[str, Any]]
    analysis_materials: Optional[Dict[str, Any]]
    error_message: Optional[str] = None


class CADProcessor:
    """
    Procesador de archivos CAD con análisis de IA.
    
    Simula el "ojo del arquitecto" convirtiendo planos técnicos
    en descripciones inteligentes.
    """
    
    # Prompts especializados por tipo de análisis
    ANALYSIS_PROMPTS = {
        'general': {
            'architecture': "Describe this architectural floor plan in detail. What type of building is it? How many floors does it show? What is the overall layout?",
            'engineering': "Describe this engineering drawing. What type of structure or system does it represent? What are the main components?",
            'electrical': "Describe this electrical plan. Identify the main electrical components, circuits, and panel locations.",
            'plumbing': "Describe this plumbing plan. Identify pipes, fixtures, drains, and water supply points.",
            'structural': "Describe this structural drawing. Identify beams, columns, foundations, and load-bearing elements.",
            'default': "Describe this technical drawing in detail. What does it represent? What are the main elements?"
        },
        'rooms': {
            'architecture': "List all rooms or spaces visible in this floor plan. For each room, describe its apparent purpose and relative size.",
            'interior': "Identify all interior spaces in this design. Describe the layout and flow between rooms.",
            'default': "Identify distinct areas or zones in this drawing. What is the purpose of each area?"
        },
        'safety': {
            'architecture': "Identify safety elements in this floor plan: emergency exits, fire extinguisher locations, escape routes, stairwells, and any safety hazards.",
            'engineering': "Identify safety-critical elements in this drawing: emergency systems, safety barriers, hazard zones.",
            'electrical': "Identify electrical safety elements: ground connections, circuit breakers, emergency disconnects, and potential hazards.",
            'default': "Identify any safety-related elements or potential hazards visible in this drawing."
        },
        'structural': {
            'architecture': "Identify structural elements: load-bearing walls, columns, beams, and foundation indicators.",
            'structural': "Analyze the structural system: identify columns, beams, slabs, foundations, and their apparent arrangement.",
            'engineering': "Identify the main structural components and their connections.",
            'default': "Identify any structural or support elements visible in this drawing."
        },
        'dimensions': {
            'architecture': "Estimate the approximate dimensions of the spaces shown. Identify any dimension annotations visible.",
            'engineering': "Identify dimension annotations and estimate the scale of the drawing.",
            'default': "Describe any measurements or scale information visible in this drawing."
        },
        'materials': {
            'architecture': "Based on the drawing style and annotations, suggest what materials might be used for walls, floors, and finishes.",
            'interior': "Identify material specifications or finishes indicated in this interior design.",
            'structural': "Identify construction materials indicated: concrete, steel, wood, masonry.",
            'default': "Identify any material specifications or suggestions visible in this drawing."
        }
    }
    
    def __init__(self, vlm_engine=None, output_dir: str = "/app/storage/app/public/cad_renders"):
        """
        Inicializa el procesador CAD.
        
        Args:
            vlm_engine: Motor VLM (Moondream2) para análisis
            output_dir: Directorio para guardar renders (default: volumen compartido)
        """
        self.vlm_engine = vlm_engine
        self.output_dir = output_dir
        self._ensure_output_dir()
        
        # Lazy import ezdxf
        self._ezdxf = None
        self._matplotlib_loaded = False
    
    def _ensure_output_dir(self):
        """Crear directorio de salida si no existe"""
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(os.path.join(self.output_dir, "thumbnails"), exist_ok=True)
    
    def _load_ezdxf(self):
        """Carga lazy de ezdxf para no impactar startup"""
        if self._ezdxf is None:
            try:
                import ezdxf
                from ezdxf.addons.drawing import RenderContext, Frontend
                from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
                self._ezdxf = ezdxf
                self._RenderContext = RenderContext
                self._Frontend = Frontend
                self._MatplotlibBackend = MatplotlibBackend
                print("✅ ezdxf cargado correctamente")
            except ImportError as e:
                print(f"❌ Error importando ezdxf: {e}")
                raise ImportError("ezdxf no está instalado. Ejecute: pip install ezdxf matplotlib")
        return self._ezdxf
    
    def _load_matplotlib(self):
        """Carga lazy de matplotlib"""
        if not self._matplotlib_loaded:
            import matplotlib
            matplotlib.use('Agg')  # Non-interactive backend
            import matplotlib.pyplot as plt
            self._plt = plt
            self._matplotlib_loaded = True
        return self._plt
    
    def _convert_dwg_to_dxf(self, dwg_path: str) -> Optional[str]:
        """
        Intenta convertir un archivo DWG a DXF usando herramientas disponibles.
        
        Prueba en orden:
        1. ODAFileConverter (si está instalado)
        2. LibreDWG dwg2dxf (si está instalado)
        3. teigha_file_converter
        
        Returns:
            Path al archivo DXF convertido o None si falla
        """
        import subprocess
        import tempfile
        
        base_name = os.path.splitext(os.path.basename(dwg_path))[0]
        temp_dir = tempfile.gettempdir()
        output_dxf = os.path.join(temp_dir, f"{base_name}_converted.dxf")
        
        # Try ODAFileConverter
        try:
            oda_converter = os.environ.get('ODA_FILE_CONVERTER', 'ODAFileConverter')
            result = subprocess.run(
                [oda_converter, os.path.dirname(dwg_path), temp_dir, 'ACAD2018', 'DXF', '0', '1', base_name],
                capture_output=True, text=True, timeout=60
            )
            if result.returncode == 0 and os.path.exists(output_dxf):
                print(f"✅ DWG convertido con ODAFileConverter")
                return output_dxf
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            print(f"⚠️ ODAFileConverter no disponible: {e}")
        
        # Try LibreDWG dwg2dxf
        try:
            result = subprocess.run(
                ['dwg2dxf', '-o', output_dxf, dwg_path],
                capture_output=True, text=True, timeout=60
            )
            if result.returncode == 0 and os.path.exists(output_dxf):
                print(f"✅ DWG convertido con LibreDWG")
                return output_dxf
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            print(f"⚠️ LibreDWG no disponible: {e}")
        
        print(f"❌ No se pudo convertir DWG a DXF")
        return None
    
    def render_dxf_to_image(
        self, 
        dxf_path: str, 
        output_path: str,
        dpi: int = 150,
        background_color: str = 'white',
        clean_noise: bool = True
    ) -> Tuple[bool, Optional[CADMetadata]]:
        """
        Convierte un archivo DXF en una imagen PNG.
        
        Args:
            dxf_path: Ruta al archivo DXF
            output_path: Ruta de salida para el PNG
            dpi: Resolución de salida
            background_color: Color de fondo ('white' o 'black')
            clean_noise: Si True, elimina entidades de ruido (MTEXT, TEXT, DIMENSION, etc.)
        
        Returns:
            Tuple[success, metadata]
        """
        try:
            ezdxf = self._load_ezdxf()
            plt = self._load_matplotlib()
            
            print(f"📐 Leyendo DXF: {dxf_path}")
            
            # Cargar documento
            doc = ezdxf.readfile(dxf_path)
            msp = doc.modelspace()
            
            # Extraer metadata ANTES de limpiar (para conservar textos/cotas)
            metadata = self._extract_metadata(doc, msp)
            
            # OPTIMIZACIÓN: Limpieza de ruido visual
            if clean_noise:
                entities_to_delete = []
                noise_types = ['MTEXT', 'TEXT', 'DIMENSION', 'HATCH', 'LEADER', 'MULTILEADER']
                
                for entity in msp:
                    if entity.dxftype() in noise_types:
                        entities_to_delete.append(entity)
                
                deleted_count = 0
                for entity in entities_to_delete:
                    try:
                        msp.delete_entity(entity)
                        deleted_count += 1
                    except:
                        pass
                
                if deleted_count > 0:
                    print(f"🧹 Limpieza: {deleted_count} entidades de ruido eliminadas")
            
            # Configurar renderizado - Alta resolución para mejor análisis VLM
            fig = plt.figure(figsize=(20, 20), dpi=dpi)
            ax = fig.add_axes([0, 0, 1, 1])
            ax.set_axis_off()
            
            if background_color == 'white':
                ax.set_facecolor('white')
                fig.patch.set_facecolor('white')
            else:
                ax.set_facecolor('black')
                fig.patch.set_facecolor('black')
            
            # Crear contexto y renderizar
            ctx = self._RenderContext(doc)
            out = self._MatplotlibBackend(ax)
            self._Frontend(ctx, out).draw_layout(msp, finalize=True)
            
            # Guardar con alta calidad
            fig.savefig(output_path, dpi=dpi, bbox_inches='tight', 
                       pad_inches=0.1, facecolor=fig.get_facecolor(),
                       edgecolor='none')
            plt.close(fig)
            
            print(f"✅ Imagen renderizada: {output_path}")
            return True, metadata
            
        except Exception as e:
            print(f"❌ Error renderizando DXF: {e}")
            import traceback
            traceback.print_exc()
            return False, None
    
    def _extract_metadata(self, doc, msp) -> CADMetadata:
        """Extrae metadata útil del documento DXF"""
        try:
            # Layers
            layers = [layer.dxf.name for layer in doc.layers]
            
            # Blocks
            block_names = [block.name for block in doc.blocks if not block.name.startswith('*')]
            
            # Units
            units_map = {
                0: 'Unitless', 1: 'Inches', 2: 'Feet', 3: 'Miles',
                4: 'Millimeters', 5: 'Centimeters', 6: 'Meters', 7: 'Kilometers'
            }
            units = units_map.get(doc.header.get('$INSUNITS', 0), 'Unknown')
            
            # Extents
            try:
                extmin = doc.header.get('$EXTMIN', (0, 0, 0))
                extmax = doc.header.get('$EXTMAX', (0, 0, 0))
                extents = {
                    'min_x': extmin[0] if extmin else 0,
                    'min_y': extmin[1] if extmin else 0,
                    'max_x': extmax[0] if extmax else 0,
                    'max_y': extmax[1] if extmax else 0,
                }
            except:
                extents = {'min_x': 0, 'min_y': 0, 'max_x': 0, 'max_y': 0}
            
            # Entity count
            entity_count = len(list(msp))
            
            # Extract text content
            text_content = []
            dimension_texts = []
            for entity in msp:
                if entity.dxftype() == 'TEXT':
                    text_content.append(entity.dxf.text)
                elif entity.dxftype() == 'MTEXT':
                    text_content.append(entity.text)
                elif entity.dxftype() == 'DIMENSION':
                    try:
                        dimension_texts.append(str(entity.dxf.text))
                    except:
                        pass
            
            return CADMetadata(
                layers=layers[:50],  # Limitar a 50
                block_names=block_names[:50],
                units=units,
                extents=extents,
                entity_count=entity_count,
                text_content=text_content[:100],  # Limitar
                dimension_texts=dimension_texts[:50]
            )
            
        except Exception as e:
            print(f"⚠️ Error extrayendo metadata: {e}")
            return CADMetadata(
                layers=[], block_names=[], units='Unknown',
                extents={}, entity_count=0, text_content=[], dimension_texts=[]
            )
    
    def create_thumbnail(self, image_path: str, thumbnail_path: str, size: Tuple[int, int] = (400, 400)):
        """Crear thumbnail de la imagen renderizada"""
        try:
            img = Image.open(image_path)
            img.thumbnail(size, Image.Resampling.LANCZOS)
            img.save(thumbnail_path, 'PNG', optimize=True)
            print(f"✅ Thumbnail creado: {thumbnail_path}")
            return True
        except Exception as e:
            print(f"❌ Error creando thumbnail: {e}")
            return False
    
    def analyze_with_vlm(
        self, 
        image_path: str, 
        project_type: str,
        analysis_types: List[str] = None
    ) -> Dict[str, Dict[str, Any]]:
        """
        Analiza la imagen renderizada con Moondream2.
        
        Args:
            image_path: Ruta a la imagen PNG
            project_type: Tipo de proyecto para seleccionar prompts
            analysis_types: Lista de tipos de análisis a realizar
        
        Returns:
            Dict con resultados por tipo de análisis
        """
        if self.vlm_engine is None:
            print("⚠️ VLM engine no disponible, saltando análisis")
            return {}
        
        if analysis_types is None:
            analysis_types = ['general', 'rooms', 'safety', 'structural', 'dimensions', 'materials']
        
        # Cargar imagen
        try:
            image = cv2.imread(image_path)
            if image is None:
                print(f"❌ No se pudo cargar imagen: {image_path}")
                return {}
        except Exception as e:
            print(f"❌ Error cargando imagen: {e}")
            return {}
        
        results = {}
        
        for analysis_type in analysis_types:
            try:
                # Obtener prompt apropiado
                prompts = self.ANALYSIS_PROMPTS.get(analysis_type, {})
                prompt = prompts.get(project_type, prompts.get('default', ''))
                
                if not prompt:
                    continue
                
                print(f"🤖 Analizando: {analysis_type}...")
                
                # Analizar con VLM (puede ser local o cliente remoto)
                vlm_result = self.vlm_engine.analyze_image(image, prompt)
                
                # Soportar tanto dict (VLMClient) como string (MoondreamAnalyzer local)
                if isinstance(vlm_result, dict):
                    response = vlm_result.get('answer', '') if vlm_result.get('success') else f"Error: {vlm_result.get('error', 'Unknown')}"
                else:
                    response = str(vlm_result)
                
                results[f'analysis_{analysis_type}'] = {
                    'prompt': prompt,
                    'response': response,
                    'timestamp': self._get_timestamp()
                }
                
                print(f"✅ {analysis_type}: {response[:100] if response else 'No response'}...")
                
            except Exception as e:
                print(f"❌ Error en análisis {analysis_type}: {e}")
                results[f'analysis_{analysis_type}'] = {
                    'error': str(e)
                }
        
        return results
    
    def process_project(
        self,
        file_path: str,
        project_id: int,
        project_type: str = 'architecture',
        callback_fn: Callable[[int, str, int], None] = None
    ) -> AnalysisResult:
        """
        Procesa un proyecto CAD completo.
        
        Args:
            file_path: Ruta al archivo CAD
            project_id: ID del proyecto en BD
            project_type: Tipo de proyecto
            callback_fn: Función para reportar progreso (project_id, step, progress%)
        
        Returns:
            AnalysisResult con todos los datos
        """
        def report(step: str, progress: int):
            print(f"📊 [{progress}%] {step}")
            if callback_fn:
                callback_fn(project_id, step, progress)
        
        try:
            # Verificar archivo
            if not os.path.exists(file_path):
                return AnalysisResult(
                    success=False,
                    render_image_path=None,
                    render_thumbnail_path=None,
                    metadata=None,
                    analysis_general=None,
                    analysis_rooms=None,
                    analysis_safety=None,
                    analysis_structural=None,
                    analysis_dimensions=None,
                    analysis_materials=None,
                    error_message=f"Archivo no encontrado: {file_path}"
                )
            
            # Determinar tipo de archivo
            ext = os.path.splitext(file_path)[1].lower()
            
            report("Iniciando procesamiento...", 5)
            
            # Rutas de salida
            render_filename = f"cad_{project_id}.png"
            thumbnail_filename = f"cad_{project_id}_thumb.png"
            render_path = os.path.join(self.output_dir, render_filename)
            thumbnail_path = os.path.join(self.output_dir, "thumbnails", thumbnail_filename)
            
            metadata = None
            
            # FASE 1: Renderizado (0-30%)
            report("Renderizando plano a imagen...", 10)
            
            if ext == '.dxf':
                success, metadata = self.render_dxf_to_image(file_path, render_path)
            elif ext == '.dwg':
                # DWG requiere conversión a DXF
                report("⚠️ DWG detectado, intentando conversión...", 15)
                
                # Try to convert DWG to DXF using available tools
                dxf_path = self._convert_dwg_to_dxf(file_path)
                
                if dxf_path and os.path.exists(dxf_path):
                    report("✅ DWG convertido a DXF", 18)
                    success, metadata = self.render_dxf_to_image(dxf_path, render_path)
                    # Clean up temp DXF
                    try:
                        os.remove(dxf_path)
                    except:
                        pass
                else:
                    # Fallback: try ezdxf directly (may work for some DWG versions)
                    report("⚠️ Conversión fallida, intentando lectura directa...", 18)
                    success, metadata = self.render_dxf_to_image(file_path, render_path)
                    
                    if not success:
                        return AnalysisResult(
                            success=False, render_image_path=None, render_thumbnail_path=None,
                            metadata=None, analysis_general=None, analysis_rooms=None,
                            analysis_safety=None, analysis_structural=None,
                            analysis_dimensions=None, analysis_materials=None,
                            error_message="El archivo DWG no pudo ser procesado. Por favor, convierta el archivo a formato DXF y vuelva a subirlo."
                        )
            elif ext == '.pdf':
                # PDF: Usar pdf2image (futuro)
                return AnalysisResult(
                    success=False, render_image_path=None, render_thumbnail_path=None,
                    metadata=None, analysis_general=None, analysis_rooms=None,
                    analysis_safety=None, analysis_structural=None,
                    analysis_dimensions=None, analysis_materials=None,
                    error_message="Soporte PDF aún no implementado. Use archivos DXF."
                )
            else:
                return AnalysisResult(
                    success=False, render_image_path=None, render_thumbnail_path=None,
                    metadata=None, analysis_general=None, analysis_rooms=None,
                    analysis_safety=None, analysis_structural=None,
                    analysis_dimensions=None, analysis_materials=None,
                    error_message=f"Tipo de archivo no soportado: {ext}"
                )
            
            if not success:
                return AnalysisResult(
                    success=False, render_image_path=None, render_thumbnail_path=None,
                    metadata=None, analysis_general=None, analysis_rooms=None,
                    analysis_safety=None, analysis_structural=None,
                    analysis_dimensions=None, analysis_materials=None,
                    error_message="Error al renderizar el archivo CAD"
                )
            
            report("Generando thumbnail...", 25)
            self.create_thumbnail(render_path, thumbnail_path)
            
            report("Renderizado completado", 30)
            
            # FASE 2: Análisis con IA (30-95%)
            if self.vlm_engine:
                report("Iniciando análisis con IA...", 35)
                
                # Análisis general
                report("Analizando descripción general...", 40)
                analysis = self.analyze_with_vlm(render_path, project_type, ['general'])
                analysis_general = analysis.get('analysis_general')
                
                # Análisis de habitaciones
                report("Identificando espacios y habitaciones...", 50)
                analysis = self.analyze_with_vlm(render_path, project_type, ['rooms'])
                analysis_rooms = analysis.get('analysis_rooms')
                
                # Análisis de seguridad
                report("Evaluando elementos de seguridad...", 60)
                analysis = self.analyze_with_vlm(render_path, project_type, ['safety'])
                analysis_safety = analysis.get('analysis_safety')
                
                # Análisis estructural
                report("Analizando elementos estructurales...", 70)
                analysis = self.analyze_with_vlm(render_path, project_type, ['structural'])
                analysis_structural = analysis.get('analysis_structural')
                
                # Análisis de dimensiones
                report("Estimando dimensiones...", 80)
                analysis = self.analyze_with_vlm(render_path, project_type, ['dimensions'])
                analysis_dimensions = analysis.get('analysis_dimensions')
                
                # Análisis de materiales
                report("Sugiriendo materiales...", 90)
                analysis = self.analyze_with_vlm(render_path, project_type, ['materials'])
                analysis_materials = analysis.get('analysis_materials')
            else:
                analysis_general = None
                analysis_rooms = None
                analysis_safety = None
                analysis_structural = None
                analysis_dimensions = None
                analysis_materials = None
            
            report("Análisis completado", 100)
            
            # Paths relativos para storage
            relative_render = f"cad_renders/{render_filename}"
            relative_thumbnail = f"cad_renders/thumbnails/{thumbnail_filename}"
            
            return AnalysisResult(
                success=True,
                render_image_path=relative_render,
                render_thumbnail_path=relative_thumbnail,
                metadata=asdict(metadata) if metadata else None,
                analysis_general=analysis_general,
                analysis_rooms=analysis_rooms,
                analysis_safety=analysis_safety,
                analysis_structural=analysis_structural,
                analysis_dimensions=analysis_dimensions,
                analysis_materials=analysis_materials
            )
            
        except Exception as e:
            print(f"❌ Error procesando proyecto: {e}")
            import traceback
            traceback.print_exc()
            return AnalysisResult(
                success=False, render_image_path=None, render_thumbnail_path=None,
                metadata=None, analysis_general=None, analysis_rooms=None,
                analysis_safety=None, analysis_structural=None,
                analysis_dimensions=None, analysis_materials=None,
                error_message=str(e)
            )
    
    def _get_timestamp(self) -> str:
        """Obtener timestamp ISO"""
        from datetime import datetime
        return datetime.utcnow().isoformat() + 'Z'


# ============================================================================
# OPTIMIZED CAD RENDERING - clean_and_render_cad
# ============================================================================
# Esta función implementa renderizado optimizado de planos CAD:
# 1. Limpia ruido (MTEXT, TEXT, DIMENSION, HATCH, LEADER)
# 2. Fuerza líneas negras sobre fondo blanco (alto contraste)
# 3. Renderiza a alta resolución (150 DPI, 20x20 figsize)
# ============================================================================

def clean_and_render_cad(dxf_path: str, output_image_path: str, dpi: int = 150) -> bool:
    """
    Renderiza un archivo DXF a imagen PNG con limpieza y optimización.
    
    Esta versión:
    - Elimina entidades de ruido (textos, cotas, sombreados)
    - Fuerza líneas negras sobre fondo blanco
    - Genera imagen de alta resolución para mejor análisis VLM
    
    Args:
        dxf_path: Ruta al archivo DXF
        output_image_path: Ruta de salida para el PNG
        dpi: Resolución de salida (default 150)
        
    Returns:
        bool: True si exitoso, False si error
    """
    try:
        # Imports
        import ezdxf
        from ezdxf.addons.drawing import RenderContext, Frontend
        from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
        import matplotlib
        matplotlib.use('Agg')  # Non-interactive backend
        import matplotlib.pyplot as plt
        
        print(f"📐 Procesando CAD (optimizado): {dxf_path}")
        
        # Cargar documento
        doc = ezdxf.readfile(dxf_path)
        msp = doc.modelspace()
        
        # 1. LIMPIEZA: Borrar entidades de ruido (Cotas, Textos, etc.)
        # Esto mejora la claridad visual para el análisis VLM
        entities_to_delete = []
        noise_types = ['MTEXT', 'TEXT', 'DIMENSION', 'HATCH', 'LEADER', 'MULTILEADER']
        
        for entity in msp:
            if entity.dxftype() in noise_types:
                entities_to_delete.append(entity)
        
        deleted_count = 0
        for entity in entities_to_delete:
            try:
                msp.delete_entity(entity)
                deleted_count += 1
            except:
                pass
        
        if deleted_count > 0:
            print(f"🧹 Limpieza: {deleted_count} entidades de ruido eliminadas")
        
        # 2. RENDERIZADO: Alto contraste (Negro sobre Blanco)
        ctx = RenderContext(doc)
        
        # Configurar figura grande para mejor resolución
        fig = plt.figure(figsize=(20, 20), dpi=dpi)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_axis_off()
        
        # Fondo blanco
        ax.set_facecolor('white')
        fig.patch.set_facecolor('white')
        
        # Backend de matplotlib
        out = MatplotlibBackend(ax)
        
        # Renderizar layout
        frontend = Frontend(ctx, out)
        frontend.draw_layout(msp, finalize=True)
        
        # Crear directorio de salida si no existe
        os.makedirs(os.path.dirname(output_image_path), exist_ok=True)
        
        # Guardar imagen
        fig.savefig(
            output_image_path, 
            dpi=dpi, 
            bbox_inches='tight', 
            pad_inches=0.1,
            facecolor='white',
            edgecolor='none'
        )
        plt.close(fig)
        
        print(f"✅ Imagen CAD renderizada: {output_image_path}")
        return True
        
    except Exception as e:
        print(f"❌ Error renderizando CAD: {e}")
        import traceback
        traceback.print_exc()
        return False


def clean_and_render_cad_with_metadata(dxf_path: str, output_image_path: str, dpi: int = 150) -> Tuple[bool, Optional[Dict]]:
    """
    Versión extendida que también extrae metadata del CAD.
    
    Args:
        dxf_path: Ruta al archivo DXF
        output_image_path: Ruta de salida para el PNG
        dpi: Resolución de salida (default 150)
        
    Returns:
        Tuple[bool, Optional[Dict]]: (success, metadata_dict)
    """
    try:
        import ezdxf
        from ezdxf.addons.drawing import RenderContext, Frontend
        from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        
        print(f"📐 Procesando CAD con metadata: {dxf_path}")
        
        # Cargar documento
        doc = ezdxf.readfile(dxf_path)
        msp = doc.modelspace()
        
        # Extraer metadata ANTES de limpiar
        metadata = {
            'layers': [layer.dxf.name for layer in doc.layers][:50],
            'block_names': [b.name for b in doc.blocks if not b.name.startswith('*')][:50],
            'entity_count': len(list(msp)),
            'text_content': [],
            'dimension_texts': []
        }
        
        # Extraer textos y cotas antes de eliminarlos
        for entity in msp:
            if entity.dxftype() == 'TEXT':
                metadata['text_content'].append(entity.dxf.text)
            elif entity.dxftype() == 'MTEXT':
                metadata['text_content'].append(entity.text)
            elif entity.dxftype() == 'DIMENSION':
                try:
                    metadata['dimension_texts'].append(str(entity.dxf.text))
                except:
                    pass
        
        metadata['text_content'] = metadata['text_content'][:100]
        metadata['dimension_texts'] = metadata['dimension_texts'][:50]
        
        # Units
        units_map = {
            0: 'Unitless', 1: 'Inches', 2: 'Feet', 3: 'Miles',
            4: 'Millimeters', 5: 'Centimeters', 6: 'Meters', 7: 'Kilometers'
        }
        metadata['units'] = units_map.get(doc.header.get('$INSUNITS', 0), 'Unknown')
        
        # LIMPIEZA
        entities_to_delete = []
        noise_types = ['MTEXT', 'TEXT', 'DIMENSION', 'HATCH', 'LEADER', 'MULTILEADER']
        
        for entity in msp:
            if entity.dxftype() in noise_types:
                entities_to_delete.append(entity)
        
        for entity in entities_to_delete:
            try:
                msp.delete_entity(entity)
            except:
                pass
        
        # RENDERIZADO
        ctx = RenderContext(doc)
        fig = plt.figure(figsize=(20, 20), dpi=dpi)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_axis_off()
        ax.set_facecolor('white')
        fig.patch.set_facecolor('white')
        
        out = MatplotlibBackend(ax)
        Frontend(ctx, out).draw_layout(msp, finalize=True)
        
        os.makedirs(os.path.dirname(output_image_path), exist_ok=True)
        fig.savefig(output_image_path, dpi=dpi, bbox_inches='tight', 
                   pad_inches=0.1, facecolor='white')
        plt.close(fig)
        
        print(f"✅ Imagen CAD renderizada con metadata: {output_image_path}")
        return True, metadata
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False, None


# Singleton instance
_cad_processor: Optional[CADProcessor] = None


def get_cad_processor(vlm_engine=None) -> CADProcessor:
    """Obtener instancia singleton del procesador CAD"""
    global _cad_processor
    if _cad_processor is None:
        _cad_processor = CADProcessor(vlm_engine=vlm_engine)
    elif vlm_engine and _cad_processor.vlm_engine is None:
        _cad_processor.vlm_engine = vlm_engine
    return _cad_processor
