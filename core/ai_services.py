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

def analyze_and_extract_memory(conversation_text):
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
            "CRITICAL SOURCE RULES:\n"
            "0. **CONTEXT AS READ-ONLY REFERENCE:**\n"
            "   - The input 'User:' text usually contains a block starting with '🚨 SYSTEM CONTEXT INJECTION 🚨'.\n"
            "   - **DO NOT** extract items from this block as *new* memories. They are history.\n"
            "   - **HOWEVER, YOU MUST USE THIS CONTEXT** to resolve current values (e.g., retrieving the current budget to add to it).\n"
            "   - **ONLY** extract facts from the text following the label '**USER QUESTION:**' or text clearly distinct from the injection block.\n"
            "0.1. **TIMESTAMP SUPREMACY:**\n"
            "   - The input context contains timestamps like `[YYYY-MM-DD HH:MM]`.\n"
            "   - When determining the 'current state' of any value (budget, status, version), you **MUST** look at the entry with the **LATEST (NEWEST)** timestamp.\n"
            "   - **IGNORE** all older conflicting values. They are dead history.\n"
            "   - **Example:** If Context has `[09:00] Budget: 100` and `[10:00] Budget: 50`, and User says 'Add 10', the math MUST be `50 + 10 = 60`. Never use the old 100.\n"
            "1. **MANDATORY DATE & DEADLINE CALCULATION (HIGHEST PRIORITY):**\n"
            "   - **Trigger:** Relative dates ('tomorrow'), Durations ('in 30 days'), or **COUNTDOWNS** ('30 gün kaldı', '30 gün var', 'time remaining').\n"
            "   - **ACTION:** Calculate the **EXACT ISO DATE (YYYY-MM-DD)**.\n"
            "   - **LOGIC:** - 'In X days' -> Target = Today + X.\n"
            "     - 'X days left/remaining/var/kaldı' -> Target = Today + X.\n"
            "   - **REQUIREMENT:** You **MUST** append the calculated date to the `raw_text` in parentheses.\n"
            "   - **Example:** (Today: 2025-12-29) User: 'Projenin bitmesine 30 gün var'. \n"
            "     -> Output: 'Proje bitiş süresi 30 gün kaldı (Deadline: 2026-01-28).'\n"
            "     -> Tags: ['Proje', 'Deadline: 2026-01-28', 'Status: Countdown']\n"
            "2. **SOURCE OF TRUTH = USER ONLY:**\n"
            "   - **EXTRACT FACTS ONLY FROM THE 'User:' SECTION.**\n"
            "   - The 'AI:' section is **READ-ONLY context**.\n"
            "   - **EXCEPTION:** If the User explicitly *confirms* or *approves* a proposal made by the AI in the immediate context, you **MUST** extract the details of that proposal from the Context.\n"
            "3. **THE 'SUGGESTION TRAP' FILTER (CRITICAL):**\n"
            "   - If the extracted text sounds like a suggestion, advice, or opinion, **DISCARD IT IMMEDIATELY**.\n"
            "   - A fact must be definitive. Advice is NOT a memory.\n"
            "4. **CONFIRMATION & PLAN EXTRACTION (CRITICAL):**\n"
            "   - **Trigger:** User says 'I agree', 'Approved', 'Let's do it', 'Tamam', 'Onaylıyorum' in response to a detailed plan/list.\n"
            "   - **ACTION:** You **MUST** fetch the details of the plan (Timeline, Responsibilities, Tech Stack) from the *Context* (the AI's previous message).\n"
            "   - **OUTPUT:** Create a comprehensive memory item.\n"
            "   - **Format:** Raw Text: 'Project Plan Approved: [Summary of Key Steps/Weeks]'. Category: 'Roadmap' or 'Plan'.\n"
            "   - **Example:** User: 'Onaylıyorum.' (Context has 4-week plan). -> Output: 'Alfabet Projesi 4 haftalık yol haritası onaylandı. 1. Hafta: Kurulum (Umut), 2. Hafta: API (Teoman)...' Tags: ['Roadmap', 'Plan', 'Approved']\n"
            "5. **IMPLICIT AGREEMENT SCOPE:**\n"
            "   - If the User says 'Okay' to a complex suggestion, only extract the MAIN topic found in the User's previous text.\n"
            "6. **CODE & CONFIG DEDUCTION:**\n"
            "   - If the *USER* provides a code snippet, extract it.\n"
            "   - If the *AI* provides a snippet, IGNORE it unless the USER explicitly says 'Use that code'.\n"
            "7. **VALUE UPDATES & STATE CHANGES (CRITICAL):**\n"
            "   - **Trigger:** If a value changes (math, status change, version bump, checking off a pending item).\n"
            "   - **STATE CALCULATION:** Find the LATEST value in context, perform the math, and save the NEW TOTAL.\n"
            "   - **MANDATORY TAG:** Any memory item that contains the *NEW* resulting value MUST include the tag **'Update'** or **'Correction'**.\n"
            "   - **Example:** User: 'Add 50k'. \n"
            "     - Item 1: 'Added 50k.' Tags: ['Update']\n"
            "     - Item 2: 'New Budget: 450k.' Tags: ['Budget', 'Update'] <--- (MUST HAVE 'Update' TAG TO BYPASS DEDUPLICATION)\n"
            "   - **CONDITIONAL / PENDING CLAUSE:** IF the status is 'pending', 'proposed', 'draft', or 'not yet', **DO NOT** perform arithmetic. Extract as fact with tag `Status: Pending`.\n"
            "7.1. **UNIVERSAL GAP & GOAL ANALYSIS (MANDATORY):**\n"
            "   - **Trigger:** If the user updates a 'Current Value' (e.g., weight, spending, pages read) AND a related 'Goal', 'Limit', or 'Target' exists in the context.\n"
            "   - **ACTION:** Calculate the difference and explicitly state the status/gap in the output.\n"
            "   - **Logic:**\n"
            "     - **Finance/Limits:** (Limit - Current) -> '... (X remaining in budget/limit)' OR '... (Over limit by X)'.\n"
            "     - **Health/Weight:** (Current - Goal) -> '... (X to go / X away from goal)'.\n"
            "     - **Progress:** (Current / Total) -> '... (X% completed)'.\n"
            "   - **Examples:**\n"
            "     - Context: 'Goal Weight: 70kg'. User: 'I am 72kg today'. -> Output: 'Current weight 72kg (2kg away from goal)'. Tags: ['Weight', 'Health', 'Update']\n"
            "     - Context: 'Read 50 pages'. User: 'Read 20 more'. -> Output: 'Total read 70 pages'. Tags: ['Reading', 'Update']\n"
            "8. **LANGUAGE NEUTRALITY:** ALWAYS use the user's input language for the 'raw_text'.\n"
            "9. **FACT FORMALIZATION (IMPORTANT):**\n"
            "   - **REWRITE** the extracted fact into a clear, standalone, professional sentence.\n"
            "   - **REMOVE** conversational fillers.\n"
            "10. **STRICT TAGGING:** Identify specific names, tools, files. ALWAYS include 'tags'.\n"
            "11. **DYNAMIC CLASSIFICATION:** Generate a short category name.\n"
            "12. **HYPOTHETICAL FILTER (STRICT):**\n"
            "    - **DISCARD** statements that are conditional, uncertain, or future possibilities dependent on 'if'.\n"
            "13. **QUESTION FILTER:**\n"
            "    - **NEVER** extract information from questions asked by the User.\n"
            "14. **NEGATION & STATUS DISTINCTION:**\n"
            "    - Be extremely careful with negative sentences.\n"
            "    - **Cancelled/Dead:** If explicitly cancelled ('React iptal'), tag as 'Cancelled'.\n"
            "    - **Not Yet/Pending:** If 'not yet added' or 'will add later', tag as 'Status: Pending'. Do not treat as a cancellation.\n"
            "    - **Example:** 'React kullanmıyoruz' -> Output: 'React teknolojisi projeden çıkarıldı.' (Tag: 'React', 'Cancelled').\n"
            "15. **ATOMIC SEPARATION:**\n"
            "    - If the input contains multiple distinct facts, split them into SEPARATE memory items in the JSON list.\n"
            "16. **IMPLICIT TASK DETECTION (ACTIONABLE INTELLIGENCE):**\n"
            "   - **Trigger:** If the user's text implies an obligation, future action, or something that implies a 'To-Do'.\n"
            "   - **Keywords to Watch:** 'lazım', 'gerek', 'malı', '-meli', 'yapacağız', 'unutma', 'hatırlat', 'need to', 'must', 'should', 'todo', 'plan to'.\n"
            "   - **ACTION:** 1. Set the `category` to **'TASK'** or **'TODO'**.\n"
            "     2. Add the tag **'Status: Pending'**.\n"
            "     3. Rewrite the `raw_text` as a clear imperative command.\n"
            "   - **Example:** User: 'Server loglarına bakmamız lazım.' \n"
            "     -> Output: 'Server logları kontrol edilecek.' | Category: 'TASK' | Tags: ['Server', 'Logs', 'Status: Pending']\n"
            "   - **Example:** User: 'Eve giderken süt almayı unutmayayım.'\n"
            "     -> Output: 'Süt alınacak.' | Category: 'SHOPPING' | Tags: ['Shopping', 'Status: Pending']\n"
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
