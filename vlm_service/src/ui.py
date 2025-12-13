import gradio as gr
import numpy as np
from PIL import Image
from .vlm_engine import get_prompt, list_prompts, PREDEFINED_PROMPTS
# Importamos las funciones helper de main para reutilizar la lógica de obtención del analizador
# Nota: Para evitar importaciones circulares, pasaremos el analyzer como argumento o lo importaremos dentro de la función

### http://localhost:5100/ui ###

def create_ui(get_analyzer_func):
    """
    Crea la interfaz de Gradio.
    Args:
        get_analyzer_func: Función que devuelve la instancia de MoondreamAnalyzer
    """

    # --- Funciones Wrappers para Gradio ---
    def gradio_analyze(image, prompt, dropdown_prompt_key):
        if image is None:
            return "⚠️ Por favor carga una imagen primero."
        
        # Prioridad: Si hay algo escrito en prompt, úsalo. Si no, usa el dropdown.
        final_prompt = prompt
        if not final_prompt and dropdown_prompt_key:
            final_prompt = get_prompt(dropdown_prompt_key)
        
        if not final_prompt:
            final_prompt = "Describe this image."

        try:
            analyzer = get_analyzer_func()
            # Gradio entrega numpy array en RGB, MoondreamAnalyzer espera imagen
            response = analyzer.analyze_image(image, final_prompt)
            return response
        except Exception as e:
            return f"Error: {str(e)}"

    def gradio_suggest_classes(image, context):
        if image is None:
            return "⚠️ Carga una imagen", "...", "..."
        
        try:
            analyzer = get_analyzer_func()
            
            # Replicamos la lógica del endpoint /suggest-classes pero simplificada para UI
            scene_prompt = "Describe this scene briefly."
            if context:
                scene_prompt = f"Context: {context}. " + scene_prompt
            
            scene_desc = analyzer.analyze_image(image, scene_prompt)
            
            # Detección de objetos
            coco_prompt = "List distinct objects visible in this image based on COCO classes."
            objects = analyzer.analyze_image(image, coco_prompt)
            
            return scene_desc, objects
        except Exception as e:
            return f"Error: {str(e)}", "Error"

    def update_prompt_box(key):
        """Actualiza la caja de texto cuando se selecciona un prompt del dropdown"""
        if key:
            return get_prompt(key)
        return ""

    # --- Diseño de la Interfaz ---
    with gr.Blocks(title="Moondream VLM Service", theme=gr.themes.Soft()) as demo:
        gr.Markdown("# 👁️ VLM Service: Moondream2")
        gr.Markdown("Microservicio de análisis de visión y lenguaje.")

        with gr.Tabs():
            # TAB 1: Análisis General
            with gr.TabItem("🖼️ Análisis de Imagen"):
                with gr.Row():
                    with gr.Column(scale=1):
                        img_input = gr.Image(label="Imagen de Entrada", type="numpy")
                        
                        prompt_dropdown = gr.Dropdown(
                            choices=list(PREDEFINED_PROMPTS.keys()),
                            label="Prompts Predefinidos (Opcional)"
                        )
                        
                        prompt_input = gr.Textbox(
                            label="Prompt / Pregunta",
                            placeholder="Describe this image...",
                            lines=3
                        )
                        
                        analyze_btn = gr.Button("🚀 Analizar", variant="primary")

                    with gr.Column(scale=1):
                        output_text = gr.Textbox(label="Respuesta del VLM", lines=10, interactive=False)

                # Eventos
                prompt_dropdown.change(
                    fn=update_prompt_box,
                    inputs=[prompt_dropdown],
                    outputs=[prompt_input]
                )
                analyze_btn.click(
                    fn=gradio_analyze,
                    inputs=[img_input, prompt_input, prompt_dropdown],
                    outputs=[output_text]
                )

            # TAB 2: Sugerencia de Clases (Detección)
            with gr.TabItem("🔍 Sugerir Clases (Detección)"):
                gr.Markdown("Analiza una escena para sugerir qué clases detectar.")
                with gr.Row():
                    with gr.Column():
                        img_detect_input = gr.Image(label="Imagen de Cámara/Escena", type="numpy")
                        ctx_input = gr.Textbox(label="Contexto (opcional)", placeholder="Ej: Warehouse, Traffic, Kitchen")
                        suggest_btn = gr.Button("🧠 Analizar Escena", variant="primary")
                    
                    with gr.Column():
                        scene_output = gr.Textbox(label="Descripción de Escena")
                        objects_output = gr.Textbox(label="Objetos Detectados")
                
                suggest_btn.click(
                    fn=gradio_suggest_classes,
                    inputs=[img_detect_input, ctx_input],
                    outputs=[scene_output, objects_output]
                )

    return demo