import os
import json
import google.generativeai as genai
from django.conf import settings

# Configure the library
# Try to get API key from settings first, then environment variable
API_KEY = getattr(settings, 'GOOGLE_API_KEY', os.environ.get('GOOGLE_API_KEY'))

if API_KEY:
    genai.configure(api_key=API_KEY)

def get_embedding(text):
    """
    Generates an embedding for the given text using the 'models/text-embedding-004' model.
    Returns a list of floats (768 dimensions).
    """
    if not API_KEY:
        raise ValueError("GOOGLE_API_KEY is not set.")

    try:
        # The content to embed.
        # content = text  # Or {"content": text} depending on specific method signature, usually text works for embed_content
        
        # models/text-embedding-004 is the latest text embedding model
        model = 'models/text-embedding-004'
        
        result = genai.embed_content(
            model=model,
            content=text,
            task_type="retrieval_document", # Context: storing user context
            title=None
        )
        
        # Result is usually a dict {'embedding': [...]}
        if 'embedding' in result:
            return result['embedding']
        else:
            # Fallback or error handling if response structure is unexpected
            # Some versions might return just the list if not raw response
            return result 

    except Exception as e:
        print(f"Error generating embedding: {e}")
        # In a production app, you might want to log this properly or re-raise
        return None

def analyze_and_extract_memory(conversation_text):
    """
    Analyzes the conversation text to extract concrete technical decisions, 
    architectural choices, or project rules.
    
    Uses 'gemini-2.5-flash-lite' (or configured model).
    Returns a LIST of dictionaries [{'raw_text': ..., 'tags': [...], 'category': ...}] or empty list [].
    """
    if not API_KEY:
        raise ValueError("GOOGLE_API_KEY is not set.")

    model_name = os.environ.get('GEMINI_MODEL_NAME', 'gemini-2.5-flash-lite')
    
    try:
        system_instruction = (
            "You are a Knowledge Base Manager.\n"
            "INPUT FORMAT: 'User: [message]\\n\\nAI: [response]'\n"
            "GOAL: Extract *NEW* confirmed project decisions or facts.\n\n"
            "CRITICAL SOURCE RULES:\n"
            "1. **SOURCE OF TRUTH = USER ONLY:**\n"
            "   - **EXTRACT FACTS ONLY FROM THE 'User:' SECTION.**\n"
            "   - The 'AI:' section is **READ-ONLY context**.\n"
            "2. **THE 'SUGGESTION TRAP' FILTER (CRITICAL):**\n"
            "   - If the extracted text sounds like a suggestion, advice, or opinion (e.g., contains 'recommend', 'suggest', 'should', 'bence', 'öneririm', 'tavsiye'), **DISCARD IT IMMEDIATELY**.\n"
            "   - A fact must be definitive (e.g., 'We will use X', 'The budget is Y'). Advice is NOT a memory.\n"
            "3. **USER CONFIRMATION IS KING:**\n"
            "   - Only extract a technical choice (like 'PostgreSQL') if the **USER** explicitly says 'Let's use PostgreSQL' or 'I agree'.\n"
            "   - **NEVER** extract the Chatbot's proposal until the User stamps it with approval.\n"
            "4. **IMPLICIT AGREEMENT SCOPE:**\n"
            "   - If the User says 'Okay' to a complex suggestions, only extract the MAIN topic found in the User's previous text. Do NOT extract the specific sub-details listed by the AI unless explicitly named by the User.\n"
            "5. **CODE & CONFIG DEDUCTION:**\n"
            "   - If the *USER* provides a code snippet, extract it.\n"
            "   - If the *AI* provides a snippet, IGNORE it unless the USER explicitly says 'Use that code'.\n"
            "6. **UPDATES & RESOLUTIONS:** \n"
            "   - If the user declares a problem **RESOLVED** or **FIXED**.\n"
            "   - **ACTION:** Generate a NEW factual statement.\n"
            "   - **MANDATORY TAGS:** include 'update' and 'correction'.\n"
            "7. **LANGUAGE NEUTRALITY:** ALWAYS use the user's input language for the 'raw_text'.\n"
            "8. **FACT FORMALIZATION (IMPORTANT):**\n"
            "   - **Do NOT** copy the user's text verbatim if it is casual or conversational.\n"
            "   - **REWRITE** the extracted fact into a clear, standalone, professional sentence in the **SAME LANGUAGE** as the input.\n"
            "   - **REMOVE** conversational fillers (e.g., 'tamam', 'hallederiz', 'sanırım', 'olur').\n"
            "   - **Example:** Input: 'tamam postgre kullanıyoruz' -> Output: 'Projede PostgreSQL veritabanı kullanılacak.'\n"
            "9. **STRICT TAGGING:** Identify specific names, tools (Python, Django), files (settings.py). ALWAYS include 'tags'.\n"
            "10. **DYNAMIC CLASSIFICATION:** Generate a short category name (e.g., 'Infrastructure').\n"
            "11. **HYPOTHETICAL FILTER (STRICT):**\n"
            "    - **DISCARD** statements that are conditional, uncertain, or future possibilities dependent on 'if'.\n"
            "    - Keywords to block: 'eğer', 'belki', 'olabilir', 'düşünüyoruz', 'if', 'maybe', 'might', 'depends'.\n"
            "    - Example: 'Eğer yatırım gelirse ofis tutacağız' -> **IGNORE**. (Not a realized fact yet).\n"
            "12. **QUESTION FILTER:**\n"
            "    - **NEVER** extract information from questions asked by the User.\n"
            "    - If the user asks 'Should we use Redis?', DO NOT extract 'Redis'. Only extract if they say 'Let's use Redis'.\n"
            "13. **NEGATION & REMOVAL:**\n"
            "    - Be extremely careful with negative sentences (e.g., 'We are NOT using React', 'React iptal').\n"
            "    - **Action:** If a user explicitly cancels a tool/method, generate a memory stating clearly that it is **REMOVED** or **CANCELLED**.\n"
            "    - Example: 'React kullanmıyoruz' -> Output: 'React teknolojisi projeden çıkarıldı/kullanılmayacak.' (Tag: 'React', 'Cancelled').\n"
            "Output format: JSON List\n"
            "[\n"
            "  {\n"
            "    \"raw_text\": \"...\", \n"
            "    \"tags\": [\"...\"], \n"
            "    \"category\": \"...\"\n"
            "  }\n"
            "]\n"
            "OR [] if nothing relevant."
        )
        
        model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=system_instruction
        )
        
        # Force JSON response
        response = model.generate_content(
            conversation_text,
            generation_config={"response_mime_type": "application/json"}
        )
        
        print(f"🔍 DEBUG AI RAW RESPONSE: {response.text}")
        
        if response.text:
            cleaned_text = response.text.strip()
            if cleaned_text.lower() == "null" or cleaned_text.lower() == "none":
                return []
            
            try:
                data = json.loads(cleaned_text)
                
                # Ensure we have a list
                if isinstance(data, dict):
                    data = [data]
                elif not isinstance(data, list):
                    return []
                
                # Filter valid items
                valid_memories = []
                for item in data:
                    if isinstance(item, dict) and item.get('raw_text'):
                        if 'category' not in item:
                            item['category'] = 'other'
                        valid_memories.append(item)
                        
                return valid_memories

            except json.JSONDecodeError:
                print(f"❌ Failed to parse JSON memory: {cleaned_text}")
                return []
            
        return []

    except Exception as e:
        print(f"❌ Error analysing memory: {e}")
        return []

def generate_project_report(memories):
    """
    Generates a comprehensive project report in Markdown format using the provided memories.
    """
    if not API_KEY:
        raise ValueError("GOOGLE_API_KEY is not set.")

    model_name = os.environ.get('GEMINI_MODEL_NAME', 'gemini-2.5-flash-lite')
    
    # improved Prompt
    system_instruction = (
        "You are an expert Document Specialist.\n"
        "GOAL: Analyze the provided project memories and generate a professional, structured Project Report in Markdown.\n\n"
        "RULES:\n"
        "0. **LANGUAGE DETECTION:** First, analyze the input memories to detect the dominant language (e.g., Turkish, English, Spanish). The report MUST effectively communicate in this language.\n"
        "1. **STRICT OUTPUT LANGUAGE:** Generate the **ENTIRE** report (including headers, descriptions, and bullet points) in the **DETECTED LANGUAGE**. If memories are in Turkish, the report headers MUST be in Turkish (e.g., 'Yönetici Özeti', 'Teknik Altyapı').\n"
        "2. **THEME IDENTIFICATION:** Identify the primary theme of this project (e.g., Software Development, Health Tracking, Legal Case) based on the content.\n"
        "3. **STRUCTURE:** Create a formal report structure based **ONLY** on the categories present in the data. Use clear H1, H2 headers.\n"
        "4. **CONFLICT RESOLUTION:** For conflicting facts (e.g., price changes, deadline updates), **PRIORITIZE** the latest information based on the timestamps provided. Mention the update history if relevant (e.g., 'Budget increased from X to Y').\n"
        "5. **FORMATTING:** Use professional Markdown. Use bullet points for readability. Use bold text for key figures or decisions.\n"
        "6. **TONE:** Keep it professional, objective, and concise.\n"
        "7. **Executive Summary:** Start with a brief Executive Summary of the project status and key facts.\n"
        "8. **MISSING DATA:** If a category is missing, do not invent data. Just omit that section.\n"
    )

    try:
        model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=system_instruction
        )
        
        # Prepare input data as a formatted string
        # memory_text = "\n".join([f"- [{m['category']}] ({m['created_at']}) {m['raw_text']}" for m in memories])
        # memories is expected to be a list of dicts: {'raw_text', 'category', 'created_at'}
        
        memory_lines = []
        for m in memories:
            timestamp = m.get('created_at', 'Unknown Time')
            category = m.get('category', 'General')
            text = m.get('raw_text', '')
            memory_lines.append(f"[{timestamp}] [{category.upper()}]: {text}")
            
        full_text = "\n".join(memory_lines)
        
        prompt = f"Please generate a Project Report from the following memory log:\n\n{full_text}"

        response = model.generate_content(prompt)
        
        if response.text:
            return response.text
        return "# Error generating report."

    except Exception as e:
        print(f"❌ Error generating report: {e}")
        return f"# Error generating report\n\nAn error occurred: {str(e)}"
