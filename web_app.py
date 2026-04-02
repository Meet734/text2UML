#!/usr/bin/env python3
"""
Text2UML - Web Application for generating UML diagrams from text descriptions
"""

from flask import Flask, render_template, request, jsonify
import requests
import os
import json
from datetime import datetime
from dotenv import load_dotenv

# Load environment
load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

# Initialize Flask app
app = Flask(__name__)
app.config['JSON_SORT_KEYS'] = False

# In-memory storage for generation history
generation_history = []


def call_gemini_api(prompt, system_message="", temperature=0.3, max_tokens=8000):
    """Call Google Gemini API to generate content"""
    headers = {"Content-Type": "application/json"}
    
    full_prompt = f"{system_message}\n\n{prompt}" if system_message else prompt
    
    payload = {
        "contents": [{
            "parts": [{"text": full_prompt}]
        }],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        }
    }
    
    try:
        response = requests.post(
            f"{API_URL}?key={GOOGLE_API_KEY}",
            headers=headers,
            json=payload,
            timeout=60
        )
        
        if response.status_code == 200:
            data = response.json()
            if "candidates" in data and len(data["candidates"]) > 0:
                candidate = data["candidates"][0]
                if "content" in candidate and "parts" in candidate["content"]:
                    if len(candidate["content"]["parts"]) > 0:
                        return candidate["content"]["parts"][0]["text"]
        
        return None
            
    except Exception as e:
        print(f"API Error: {e}")
        return None


def generate_uml(text_description):
    """Generate initial UML diagram from text description"""
    
    system_prompt = """You are an expert UML class diagram designer. Generate a COMPLETE, DETAILED, and SYNTACTICALLY CORRECT PlantUML class diagram.

**CRITICAL REQUIREMENTS:**
1. EVERY class must have a closing brace }
2. EVERY attribute must have type information
3. EVERY method must have parameters and return type
4. Include ALL relationships with proper cardinality
5. Start with @startuml and END with @enduml
6. Do NOT truncate or leave anything incomplete

**FORMAT:**
@startuml
class ClassName {
  -privateAttr: Type
  #protectedAttr: Type
  +publicAttr: Type
  +method1(param: Type): ReturnType
  +method2(param1: Type, param2: Type): ReturnType
}

class AnotherClass {
  -id: String
  +getId(): String
}

ClassName "1" -- "0..*" AnotherClass : relationship
@enduml

**RULES:**
- Always close every class with }
- Always complete every attribute and method definition
- Always specify return types
- Always end with @enduml
- Generate ONLY valid PlantUML code
"""
    
    result = call_gemini_api(text_description, system_message=system_prompt, temperature=0.3, max_tokens=8000)
    
    if result:
        # Clean up markdown code blocks
        result = result.replace('```plantuml', '').replace('```python', '').replace('```', '').strip()
        
        # Ensure proper start/end tags
        if "@startuml" not in result:
            result = "@startuml\n" + result
        if "@enduml" not in result:
            result = result + "\n@enduml"
        
        # Remove incomplete lines
        lines = result.split('\n')
        fixed_lines = []
        for line in lines:
            stripped = line.strip()
            # Skip incomplete attribute/method lines
            if not stripped in ['-', '+', '#', ':', '-:', '+:', '#:']:
                fixed_lines.append(line)
        
        result = '\n'.join(fixed_lines)
    
    return result


def refine_uml(current_uml, text_description, refinement_feedback):
    """Refine existing UML based on user feedback"""
    
    system_prompt = f"""You are an expert UML designer. Refine the following PlantUML diagram based on user feedback.

**CRITICAL: THE REFINED DIAGRAM MUST BE COMPLETE AND VALID**
- EVERY class must have a closing brace
- EVERY attribute and method must be COMPLETE
- No truncation, no incomplete lines
- Start with @startuml and END with @enduml

**CURRENT DIAGRAM:**
{current_uml}

**ORIGINAL DESCRIPTION:**
{text_description}

**REFINEMENT REQUEST:**
{refinement_feedback}

**INSTRUCTIONS:**
1. Preserve all correct elements
2. Apply the requested improvements
3. Add/modify classes, attributes, or relationships as needed
4. Ensure EVERY class is properly closed
5. Ensure EVERY attribute has a type
6. Ensure EVERY method has parameters and return type
7. Ensure EVERY relationship is complete

Generate ONLY the refined PlantUML code between @startuml and @enduml.
"""
    
    # Pass refinement_feedback as the main user prompt (not text_description)
    result = call_gemini_api(refinement_feedback, system_message=system_prompt, temperature=0.3, max_tokens=8000)
    
    if result:
        # Clean up markdown code blocks
        result = result.replace('```plantuml', '').replace('```python', '').replace('```', '').strip()
        
        # Ensure proper start/end tags
        if "@startuml" not in result:
            result = "@startuml\n" + result
        if "@enduml" not in result:
            result = result + "\n@enduml"
        
        # Remove incomplete lines
        lines = result.split('\n')
        fixed_lines = []
        for line in lines:
            stripped = line.strip()
            if not stripped in ['-', '+', '#', ':', '-:', '+:', '#:']:
                fixed_lines.append(line)
        
        result = '\n'.join(fixed_lines)
    
    return result

def validate_plantuml(code):
    """Validate PlantUML code syntax"""
    if not code:
        return False
    
    # Must have start and end tags
    if "@startuml" not in code or "@enduml" not in code:
        return False
    
    # Check for incomplete class definitions
    lines = code.split('\n')
    for i, line in enumerate(lines):
        stripped = line.strip()
        
        # Check if class starts but isn't closed
        if stripped.startswith('class ') and '{' in stripped:
            closed = False
            for j in range(i+1, len(lines)):
                if '}' in lines[j]:
                    closed = True
                    break
            
            if not closed:
                return False
            
            # Check for incomplete attribute lines
            for j in range(i+1, len(lines)):
                if '}' in lines[j]:
                    break
                attr_line = lines[j].strip()
                if attr_line in ['-', '+', '#', ':', '-:', '+:']:
                    return False
    
    # Must have at least one class definition
    if 'class ' not in code:
        return False
    
    return True


@app.route('/')
def index():
    """Serve the main web interface"""
    return render_template('index.html')


@app.route('/api/generate', methods=['POST'])
def api_generate():
    """API endpoint to generate UML from text description"""
    try:
        data = request.json
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
        
        text_input = data.get('text', '').strip()
        
        if not text_input:
            return jsonify({"error": "Please enter a description"}), 400
        
        uml = generate_uml(text_input)
        
        if uml and validate_plantuml(uml):
            # Add to history
            entry = {
                "id": len(generation_history) + 1,
                "input": text_input,
                "uml": uml,
                "timestamp": datetime.now().isoformat(),
                "refinements": 0
            }
            generation_history.append(entry)
            
            return jsonify({
                "success": True,
                "uml": uml,
                "history_id": entry["id"],
                "class_count": uml.count("class "),
                "rel_count": uml.count("--")
            })
        else:
            return jsonify({"error": "Failed to generate valid PlantUML. Try rephrasing your description."}), 500
            
    except Exception as e:
        return jsonify({"error": f"Error: {str(e)}"}), 500

@app.route('/api/refine', methods=['POST'])
def api_refine():
    """API endpoint to refine existing UML"""
    try:
        data = request.json
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
        
        current_uml = data.get('uml', '').strip()
        text_input = data.get('text', '').strip()
        feedback = data.get('feedback', '').strip()
        history_id = data.get('history_id')
        
        if not current_uml or not feedback:
            return jsonify({"error": "Missing UML or feedback"}), 400
        
        refined_uml = refine_uml(current_uml, text_input, feedback)
        
        if refined_uml and validate_plantuml(refined_uml):
            if history_id:
                for entry in generation_history:
                    if entry["id"] == history_id:
                        entry["refinements"] += 1
                        entry["uml"] = refined_uml
                        break
            return jsonify({
                "success": True,
                "uml": refined_uml,
                "class_count": refined_uml.count("class "),
                "rel_count": refined_uml.count("--")
            })
        else:
            return jsonify({"error": "Failed to generate valid refined PlantUML. Try rephrasing your feedback."}), 500
            
    except Exception as e:
        return jsonify({"error": f"Error: {str(e)}"}), 500


@app.route('/api/history', methods=['GET'])
def api_history():
    """Get generation history (most recent first)"""
    return jsonify(list(reversed(generation_history)))


@app.route('/api/history/clear', methods=['POST'])
def api_history_clear():
    """Clear session generation history"""
    generation_history.clear()
    return jsonify({"success": True})


@app.route('/api/example', methods=['GET'])
def api_example():
    """Get an example description"""
    example = """A university has multiple departments. Each department offers several courses. 
A course is taught by one or more professors. Students can enroll in multiple courses. 
Each student has a unique ID, name, and email. Professors have an office and a salary. 
Courses have a code, title, and credit hours. A department has a name and is managed by a chair."""
    return jsonify({"example": example})


@app.route('/api/export-svg', methods=['POST'])
def api_export_svg():
    """Server-side proxy to fetch rendered SVG from PlantUML service"""
    try:
        data = request.json
        if not data or 'encoded' not in data:
            return jsonify({"error": "Missing encoded PlantUML"}), 400

        encoded = data['encoded']
        url = f"https://www.plantuml.com/plantuml/svg/{encoded}"

        resp = requests.get(url, timeout=15)
        if resp.status_code == 200:
            return app.response_class(
                response=resp.content,
                status=200,
                mimetype='image/svg+xml'
            )
        else:
            return jsonify({"error": "PlantUML service unavailable"}), 502
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    print("\n" + "="*80)
    print("TEXT2UML - Interactive Web Application")
    print("="*80)
    print("\nStarting web server...")
    print("URL: http://localhost:5000")
    print("Press Ctrl+C to stop\n")
    print("="*80 + "\n")
    
    app.run(debug=False, port=5000, host='127.0.0.1')
