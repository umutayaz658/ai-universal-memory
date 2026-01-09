import os
import json
import google.generativeai as genai
from django.conf import settings
from datetime import datetime, timedelta

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
        # models/text-embedding-004 is the latest text embedding model
        model = 'models/text-embedding-004'
        
        result = genai.embed_content(
            model=model,
            content=text,
            task_type="retrieval_document", # Context: storing user context
            title=None
        )
        
        if 'embedding' in result:
            return result['embedding']
        else:
            return result 

    except Exception as e:
        print(f"Error generating embedding: {e}")
        return None

def analyze_and_extract_memory(conversation_text, existing_context=""):
    """
    Analyzes the conversation text to extract concrete technical decisions, 
    architectural choices, or project rules.
    """
    if not API_KEY:
        raise ValueError("GOOGLE_API_KEY is not set.")

    model_name = os.environ.get('GEMINI_MODEL_NAME', 'gemini-2.5-flash-lite')
    
    try:
        # V69: Dynamic Date Injection
        today_str = datetime.now().strftime("%Y-%m-%d (%A)")
        
        system_instruction = (
            f"CURRENT DATE: {today_str}\n"
            "You are a Knowledge Base Manager.\n"
            "INPUT FORMAT: 'User: [message]\\n\\nAI: [response]'\n"
            "GOAL: Extract *NEW* confirmed project decisions or facts.\n\n"
            "⭐⭐ PRIME DIRECTIVE: STRICT LANGUAGE MIRRORING ⭐⭐\n"
            "1. **DETECT** the language of the 'User Input' (English, Turkish, Spanish, etc.).\n"
            "2. **OUTPUT** the `raw_text`, `tags`, and `category` **EXACTLY** in that detected language.\n"
            "3. **NEVER** translate. If User speaks English, Output MUST be English. If Turkish, Output MUST be Turkish. If Spanish, Output MUST be Spanish.\n\n"
            "CRITICAL SOURCE RULES:\n"
            "0. **CONTEXT AS READ-ONLY REFERENCE:**\n"
            "   - Do not extract from 'SYSTEM CONTEXT INJECTION'. It is history.\n"
            "   - Use context only to resolve math or relative values.\n"
            "0.1. **TIMESTAMP SUPREMACY:**\n"
            "   - Always use the LATEST timestamp from context for current values.\n"
            "1. **MANDATORY DATE & DEADLINE CALCULATION:**\n"
            "   - Calculate exact ISO dates for relative terms.\n"
            "   - **Example (EN):** User: 'Deadline is next friday'. -> Output: 'Deadline set to 2026-01-10.'\n"
            "   - **Example (TR):** User: 'Yarın başlıyoruz'. -> Output: 'Proje başlangıç tarihi 2026-01-01 olarak belirlendi.'\n"
            "2. **SOURCE OF TRUTH = USER ONLY:**\n"
            "   - Extract facts ONLY from 'User:' section. 'AI:' is read-only context.\n"
            "   - Exception: User explicit confirmation ('Approved') of AI proposal.\n"
            "3. **THE 'SUGGESTION TRAP':**\n"
            "   - Discard suggestions/advice. Only extract definitive facts.\n"
            "4. **CONFIRMATION & PLAN EXTRACTION:**\n"
            "   - If User approves, fetch details from Context.\n"
            "   - **Example (EN):** User: 'Approved.' (Context: 4-week plan) -> Output: 'Project roadmap approved.' Tags: ['Plan', 'Approved']\n"
            "   - **Example (TR):** User: 'Onaylıyorum.' -> Output: '4 haftalık yol haritası onaylandı.' Tags: ['Plan', 'Onay']\n"
            "5. **IMPLICIT AGREEMENT SCOPE:**\n"
            "   - 'Okay' only confirms the main topic.\n"
            "6. **CODE & CONFIG DEDUCTION:**\n"
            "   - Extract User code snippets. Ignore AI snippets unless confirmed.\n"
            "7. **VALUE UPDATES & MATH (AGGRESSIVE):**\n"
            "   - Find LATEST value in Context -> Perform MATH -> Output NEW TOTAL.\n"
            "   - **Example (EN):** Context: 'Budget 50k'. User: 'Add 10k'. -> Output: 'Budget increased to 60k.'\n"
            "   - **Example (TR):** Context: 'Bütçe 50k'. User: '10k ekle'. -> Output: 'Bütçe 60.000 TLye yükseldi.'\n"
            "7.1. **UNIVERSAL GAP & GOAL ANALYSIS:**\n"
            "   - Update 'Current Value' vs 'Goal'. State status/gap.\n"
            "   - **Example:** 'Current weight 72kg (2kg away from goal)'.\n"
            "8. **LANGUAGE NEUTRALITY:**\n"
            "   - ALWAYS use the user's input language for `raw_text`, `tags`, and `category`.\n"
            "9. **FACT FORMALIZATION:**\n"
            "   - Rewrite into a clear, standalone, professional sentence.\n"
            "10. **STRICT TAGGING:** Identify specific names, tools. ALWAYS include 'tags'.\n"
            "11. **DYNAMIC CLASSIFICATION:** Generate a short category name in the USER'S LANGUAGE.\n"
            "12. **HYPOTHETICAL FILTER:**\n"
            "    - Discard conditional ('If...') or uncertain statements.\n"
            "13. **QUESTION FILTER:**\n"
            "    - Never extract info from questions.\n"
            "14. **NEGATION & STATUS DISTINCTION:**\n"
            "    - 'Cancelled' -> Tag: 'Cancelled'. 'Not yet' -> Tag: 'Status: Pending'.\n"
            "15. **ATOMIC SEPARATION:**\n"
            "    - Split multiple facts into separate items.\n"
            "16. **IMPLICIT TASK DETECTION:**\n"
            "   - Trigger: Obligation words ('must', 'should', 'lazım', 'gerek').\n"
            "   - **Example (EN):** 'We need to check logs' -> 'Check server logs.' | Category: 'Task' | Tags: ['Logs', 'Pending']\n"
            "   - **Example (TR):** 'Loglara bakmamız lazım' -> 'Server logları kontrol edilecek.' | Category: 'Görev' | Tags: ['Loglar', 'Beklemede']\n"
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
        
        # Combine existing context with new input
        # Force Date and Context visibility
        language_reminder = (
            "\n\n🛑 FINAL INSTRUCTION: OUTPUT MUST BE IN THE SAME LANGUAGE AS THE 'USER INPUT' ABOVE. "
            "IF USER INPUT IS ENGLISH, OUTPUT ENGLISH. IF TURKISH, OUTPUT TURKISH."
        )
        full_prompt = (
            f"� CURRENT DATE: {today_str}\n\n"
            f"�🚨 SYSTEM CONTEXT (HISTORY - READ ONLY):\n{existing_context}\n\n"
            f"👤 USER INPUT:\n{conversation_text}"
            f"{language_reminder}"
        ) if existing_context else (
            f"📅 CURRENT DATE: {today_str}\n\n"
            f"👤 USER INPUT:\n{conversation_text}"
            f"{language_reminder}"
        )
        
        response = model.generate_content(
            full_prompt,
            generation_config={"response_mime_type": "application/json"}
        )
        
        print(f"🔍 DEBUG AI RAW RESPONSE: {response.text}")
        
        if response.text:
            cleaned_text = response.text.strip()
            if cleaned_text.lower() == "null" or cleaned_text.lower() == "none":
                return []
            
            try:
                data = json.loads(cleaned_text)
                
                if isinstance(data, dict):
                    data = [data]
                elif not isinstance(data, list):
                    return []
                
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
        "0. **LANGUAGE DETECTION:** First, analyze the input memories to detect the dominant language. The report MUST effectively communicate in this language.\n"
        "1. **STRICT OUTPUT LANGUAGE:** Generate the **ENTIRE** report (including headers, descriptions, and bullet points) in the **DETECTED LANGUAGE**.\n"
        "2. **THEME IDENTIFICATION:** Identify the primary theme of this project.\n"
        "3. **STRUCTURE:** Create a formal report structure based **ONLY** on the categories present in the data. Use clear H1, H2 headers.\n"
        "4. **CONFLICT RESOLUTION:** For conflicting facts, **PRIORITIZE** the latest information based on the timestamps provided.\n"
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
