"""
Template Engine - Coordinates template selection and parameter extraction.

Flow:
1. Classify user prompt → Identify best template
2. Extract parameters → Get content for template
3. Generate code → Fill template with parameters
"""

import json
from typing import Optional, Dict, Any, Tuple

from app.llm import call_llm_json
from app.templates.function_graph import FunctionGraphTemplate
from app.templates.algebraic_steps import AlgebraicStepsTemplate
from app.templates.geometric_proof import GeometricProofTemplate


# Registry of available templates
TEMPLATE_REGISTRY = {
    "function_graph": FunctionGraphTemplate,
    "algebraic_steps": AlgebraicStepsTemplate,
    "geometric_proof": GeometricProofTemplate,
}


CLASSIFICATION_PROMPT = """Analyze this user prompt and classify it into ONE of these animation types:

1. function_graph - Plotting one or more mathematical functions (e.g., "graph y=x^2", "plot sin and cos")
2. algebraic_steps - Step-by-step equation solving (e.g., "solve 2x+4=10", "derive the quadratic formula")
3. geometric_proof - Visual proof using shapes (e.g., "prove Pythagorean theorem", "show area of circle")

USER PROMPT: "{prompt}"

Respond with ONLY a JSON object in this format:
{{
    "template": "template_name",
    "confidence": 0.95
}}

If you're not confident (< 0.7), use "unknown" as the template name."""


def get_parameter_extraction_prompt(template_name: str, user_prompt: str) -> str:
    """Generate parameter extraction prompt based on template type."""
    
    if template_name == "function_graph":
        return f"""Extract parameters for plotting functions from this prompt:

USER PROMPT: "{user_prompt}"

Respond with ONLY a JSON object:
{{
    "title": "descriptive title",
    "functions": [
        {{"expr": "x**2", "label": "y = x²", "color": "BLUE"}},
        {{"expr": "2*x", "label": "y = 2x", "color": "RED"}}
    ],
    "x_range": [-5, 5, 1],
    "y_range": [-3, 10, 1]
}}

CRITICAL:
- expr must be valid Python expression (use ** for power, not ^)
- Use proper LaTeX in labels (e.g., x^2 not x**2)
- Colors must be: BLUE, RED, GREEN, YELLOW, ORANGE, PURPLE, PINK, WHITE
- Ranges should cover the interesting part of the functions"""
    
    elif template_name == "algebraic_steps":
        return f"""Extract step-by-step solution from this prompt:

USER PROMPT: "{user_prompt}"

Respond with ONLY a JSON object:
{{
    "title": "Solution Title",
    "steps": [
        {{"equation": "2x + 4 = 10", "annotation": "Original equation"}},
        {{"equation": "2x = 6", "annotation": "Subtract 4 from both sides"}},
        {{"equation": "x = 3", "annotation": "Divide by 2"}}
    ]
}}

CRITICAL:
- Use proper LaTeX formatting (e.g., \\\\\\\\frac{{}}{{{{}}}}{{{{}}}}{{, x^2, \\\\\\\\sqrt{{{{}}}}{{)
- Each step should show clear progression
- Annotations should explain what changed"""
    
    elif template_name == "geometric_proof":
        return f"""Extract geometric proof elements from this prompt:

USER PROMPT: "{user_prompt}"

Respond with ONLY a JSON object:
{{
    "theorem": "a^2 + b^2 = c^2",
    "shapes": [
        {{"type": "Square", "side": 2, "color": "BLUE", "label": "a^2", "position": [-3, 0, 0]}},
        {{"type": "Triangle", "vertices": [[0,0,0], [3,0,0], [3,4,0]], "color": "GREEN", "label": ""}},
        {{"type": "Square", "side": 1.5, "color": "RED", "label": "b^2", "position": [3, 0, 0]}}
    ],
    "proof_steps": [
        {{"text": "The squares on the legs..."}}
    ]
}}

CRITICAL:
- Shapes: Square, Circle, Triangle, Rectangle
- Colors: BLUE, RED, GREEN, YELLOW, ORANGE, PURPLE
- Position: [x, y, 0] where x,y are in range [-7, 7] and [-4, 4]
- Spread shapes out - minimum 2 units apart"""
    
    return ""


def classify_prompt(user_prompt: str) -> Tuple[Optional[str], float]:
    """
    Classify user prompt to determine which template to use.
    
    Returns:
        (template_name, confidence)
    """
    prompt = CLASSIFICATION_PROMPT.format(prompt=user_prompt)
    result = call_llm_json(prompt)
    
    if not result:
        return None, 0.0
    
    template_name = result.get("template", "unknown")
    confidence = result.get("confidence", 0.0)
    
    if template_name == "unknown" or confidence < 0.7:
        return None, confidence
    
    return template_name, confidence


def extract_parameters(template_name: str, user_prompt: str) -> Optional[Dict[str, Any]]:
    """
    Extract parameters for a specific template.
    
    Returns:
        Dictionary of parameters or None if extraction failed
    """
    prompt = get_parameter_extraction_prompt(template_name, user_prompt)
    if not prompt:
        return None
    
    result = call_llm_json(prompt)
    print(f"DEBUG: Extracted parameters for {template_name}: {json.dumps(result, indent=2)}")
    return result


def generate_from_template(user_prompt: str) -> Tuple[Optional[str], str]:
    """
    Main entry point: classify prompt, extract parameters, generate code.
    
    Returns:
        (generated_code, status_message)
    """
    # Step 1: Classify
    print(f"\n📋 Classifying prompt...")
    template_name, confidence = classify_prompt(user_prompt)
    
    if not template_name:
        return None, "Could not classify prompt into a known template"
    
    print(f"✅ Classified as: {template_name} (confidence: {confidence:.2f})")
    
    # Step 2: Get template class
    template_class = TEMPLATE_REGISTRY.get(template_name)
    if not template_class:
        return None, f"Template '{template_name}' not found in registry"
    
    # Step 3: Extract parameters
    print(f"🔍 Extracting parameters...")
    params = extract_parameters(template_name, user_prompt)
    
    if not params:
        return None, "Failed to extract parameters from prompt"
    
    print(f"✅ Extracted parameters: {json.dumps(params, indent=2)}")
    
    # Step 4: Validate parameters
    is_valid, error_msg = template_class.validate_params(params)
    if not is_valid:
        return None, f"Parameter validation failed: {error_msg}"
    
    # Step 5: Generate code
    print(f"🎬 Generating code from template...")
    try:
        code = template_class.generate_code(params)
        print(f"✅ Code generated successfully")
        return code, "success"
    except Exception as e:
        return None, f"Error generating code: {str(e)}"
