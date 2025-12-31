from rest_framework import viewsets, permissions, status, views, generics
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from django.db.models import Q, TextField
from django.db.models.functions import Cast
from django.contrib.postgres.search import TrigramSimilarity
from pgvector.django import CosineDistance

from .models import Project, Memory, ProjectReport
from .serializers import ProjectSerializer, MemorySerializer, UserSerializer
from . import ai_services
import hashlib
import markdown
from xhtml2pdf import pisa
from xhtml2pdf import pisa
from django.http import HttpResponse
from rest_framework.throttling import ScopedRateThrottle

class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    permission_classes = (AllowAny,)
    serializer_class = UserSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        token, created = Token.objects.get_or_create(user=user)
        return Response({
            'user_id': user.pk,
            'email': user.email,
            'token': token.key
        }, status=status.HTTP_201_CREATED)

class ProjectViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        # Automatically assign the project to the current user
        serializer.save(user=self.request.user)

    def get_queryset(self):
        # Only return projects belonging to the current user
        return Project.objects.filter(user=self.request.user)

class StoreMemoryView(views.APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'ai_action'

    def post(self, request):
        project_id = request.data.get('project_id')
        text = request.data.get('text')

        if not project_id or not text:
            return Response(
                {"error": "project_id and text are required"}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check if project exists
        project = get_object_or_404(Project, id=project_id)
        
        # Explicit Permission Check
        if project.user != request.user:
            return Response({"error": "Unauthorized project access"}, status=status.HTTP_403_FORBIDDEN)

        # 1. RETRIEVE CONTEXT (Source A + Source B) to enable "Context-Aware Math"
        # We need to give the AI the current state (e.g. "Budget is 500") so it can process "Add 50" -> 550.
        
        context_str = ""
        try:
            # Generate embedding for the *current* input to find similar past memories
            current_embedding = ai_services.get_embedding(text)
            
            if current_embedding:
                # Source A: Similarity (Find relevant topics like "Budget" or "Weight")
                similar_memories = list(Memory.objects.filter(project=project) \
                    .annotate(distance=CosineDistance('vector', current_embedding)) \
                    .order_by('distance')[:15]) # Top 15 relevant (Expanded)

                # Source B: Recency (Find specific immediate context like "I just said X")
                # We need the absolute latest memories to handle "Add 5 to that"
                recent_memories = list(Memory.objects.filter(project=project) \
                    .order_by('-created_at')[:10]) # Last 10 items (Expanded)

                # Merge & Deduplicate
                context_pool = {m.id: m for m in similar_memories + recent_memories}.values()
                
                # Sort by Created At (Oldest -> Newest) so the AI reads the story in order
                sorted_pool = sorted(context_pool, key=lambda x: x.created_at)

                # Format as string
                context_lines = []
                for m in sorted_pool:
                    date_str = m.created_at.strftime("%Y-%m-%d %H:%M")
                    context_lines.append(f"- [{date_str}] {m.raw_text}")
                
                context_str = "\n".join(context_lines)
                print(f"🧠 INJECTING CONTEXT ({len(sorted_pool)} items):\n{context_str[:200]}...")

        except Exception as e:
            print(f"⚠️ Error retrieving context: {e}")
            # Non-blocking: proceed without context if this fails

        # 2. Analyze and extract memory (WITH CONTEXT)
        # Returns LIST of dicts [{'raw_text': str, 'tags': list, 'category': str}] or []
        extraction_results = ai_services.analyze_and_extract_memory(text, context_str)
        print(f"🧠 DEBUG EXTRACTION: {extraction_results}")
        
        if not extraction_results:
            return Response({
                "message": "No significant memory extracted from the text.",
                "created_count": 0,
                "results": []
            }, status=status.HTTP_200_OK)

        saved_memories = []
        ignored_memories = []

        # Iterate over each extracted fact
        for item in extraction_results:
            extracted_text = item.get('raw_text')
            tags = item.get('tags', [])
            category = item.get('category', 'other')

            if not extracted_text:
                continue

            # 2. Get embedding for the extracted text
            embedding = ai_services.get_embedding(extracted_text)
            
            if not embedding:
                print(f"❌ Failed to generate embedding for: {extracted_text}")
                continue

            # 3. DEDUPLICATION CHECK
            # A) CORRECTION BYPASS
            correction_keywords = {
                'correction', 'change', 'update', 'düzeltme', 'degisiklik', 
                'yenileme', 'revizyon', 'guncelleme', 
                'status', 'durum', 'pending', 'beklemede', 'draft', 'taslak'
            }
            is_correction = False
            for tag in tags:
                tag_lower = str(tag).lower()
                if any(k in tag_lower for k in correction_keywords):
                    is_correction = True
                    break

            if is_correction:
                print("🚀 Correction detected. Skipping deduplication.")
            else:
                # B) STANDARD DEDUPLICATION
                similar_memories = Memory.objects.filter(project=project) \
                    .annotate(distance=CosineDistance('vector', embedding)) \
                    .filter(distance__lt=0.05) \
                    .order_by('distance')
                    
                if similar_memories.exists():
                    duplicate = similar_memories.first()
                    print(f"🛑 Duplicate blocked. Distance: {duplicate.distance}")
                    ignored_memories.append({
                        "text": extracted_text,
                        "reason": "Duplicate"
                    })
                    continue

            # 4. Save Memory
            memory = Memory.objects.create(
                project=project,
                raw_text=extracted_text, 
                vector=embedding,
                tags=tags,
                category=category,
                source="user_conversation"
            )
            saved_memories.append({
                "id": memory.id,
                "text": extracted_text,
                "category": category
            })

        return Response({
            "message": f"Processed {len(extraction_results)} facts.",
            "created_count": len(saved_memories),
            "saved": saved_memories,
            "ignored": ignored_memories
        }, status=status.HTTP_201_CREATED)

class RetrieveContextView(views.APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'ai_action'

    def post(self, request):
        project_id = request.data.get('project_id')
        query = request.data.get('query')

        if not project_id or not query:
            print(f"DEBUG QUERY: {query} (PID: {project_id})")
            return Response(
                {"error": "project_id and query are required"}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check if project exists
        project = get_object_or_404(Project, id=project_id)
        
        # Explicit Permission Check
        if project.user != request.user:
            return Response({"error": "Unauthorized project access"}, status=status.HTTP_403_FORBIDDEN)

        # 1. Get embedding for the query
        print(f"DEBUG QUERY: {query}")
        query_embedding = ai_services.get_embedding(query)
        print(f"DEBUG EMBEDDING: {query_embedding[:5] if query_embedding else 'None'}...")
        
        if not query_embedding:
             return Response(
                {"error": "Failed to generate embedding for query."}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        # 2. Vector Search (Top 20) - Increased from 10
        vector_memories = list(Memory.objects.filter(project=project) \
            .order_by(CosineDistance('vector', query_embedding))[:20])

        # 3. Fuzzy Keyword Search (Trigram)
        # Allows typos ("büttçe") and suffix variations ("bütçesi")
        keywords = [w for w in query.split() if len(w) > 3]
        keyword_memories = []
        
        # MULTILINGUAL STOPWORD FILTER
        ignored_keywords = {
            # TR Common & Domain
            'proje', 'projede', 'projesi', 'hakkında', 'nedir', 'hangi', 'neler', 
            'ile', 'için', 've', 'veya', 'bir', 'bu', 'şu', 'uygulama',
            
            # EN Common & Domain
            'project', 'projects', 'about', 'what', 'which', 'how', 
            'for', 'with', 'and', 'or', 'a', 'an', 'the', 'this', 'that', 'app', 'application'
        }

        if keywords:
            for word in keywords:
                if word.lower() in ignored_keywords:
                    continue

                # DYNAMIC THRESHOLD LOGIC
                # Short words need loose matching (typos), Long words need strict matching (noise)
                threshold = 0.3 if len(word) > 5 else 0.1
                

                
                # Search in Tags
                similar_tags = Memory.objects.filter(project=project) \
                    .annotate(tags_as_text=Cast('tags', output_field=TextField())) \
                    .annotate(similarity=TrigramSimilarity('tags_as_text', word)) \
                    .filter(similarity__gt=threshold) \
                    .order_by('-similarity')[:2]

                if len(similar_tags) > 0:
                    print(f"🎯 DEBUG KEYWORD MATCH for '{word}' (Thresh: {threshold}): Found {len(similar_tags)} tags")

                keyword_memories.extend(list(similar_tags))
                


        # 4. Merge and Deduplicate (Keep relevance ranking)
        # PRIORITY: Vectors FIRST, then Keywords
        seen_ids = set()
        final_results = []

        # Vectors first
        for mem in vector_memories:
            if mem.id not in seen_ids:
                final_results.append(mem)
                seen_ids.add(mem.id)

        # Keywords second
        for mem in keyword_memories:
            if mem.id not in seen_ids:
                final_results.append(mem)
                seen_ids.add(mem.id)

        print(f"DEBUG FOUND: {len(final_results)} merged memories")

        # 5. Serialize results (Select Top 20 Relevance -> Sort by Date)
        # We slice [:20] FIRST to keep the most relevant ones.
        top_results = final_results[:20]
        
        # THEN sort chronologically (Newest First) as requested for UI priority
        top_results.sort(key=lambda x: x.created_at, reverse=True)

        results = []
        for mem in top_results:
            time_str = mem.created_at.strftime("%Y-%m-%d %H:%M")
            formatted_text = f"[{time_str}] {mem.raw_text}"

            results.append({
                "id": mem.id,
                "raw_text": formatted_text, 
                "source": mem.source,
                "created_at": mem.created_at
            })

        return Response({
            "results": results
        }, status=status.HTTP_200_OK)

class DeleteMemoryView(views.APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        project_id = request.data.get('project_id')
        target_text = request.data.get('target_text', '').strip()

        if not project_id:
            return Response({"error": "Project ID required"}, status=status.HTTP_400_BAD_REQUEST)

        # Check if project exists
        project = get_object_or_404(Project, id=project_id)
        
        # Explicit Permission Check
        if project.user != request.user:
            return Response({"error": "Unauthorized project access"}, status=status.HTTP_403_FORBIDDEN)
        memory_id = request.data.get('memory_id')

        try:
            if memory_id:
                # 0. DIRECT DELETION (UI Support)
                memory_to_delete = get_object_or_404(Memory, id=memory_id, project=project)
                deleted_text = memory_to_delete.raw_text
                memory_to_delete.delete()
                print(f"🗑️ UI DELETE: ID {memory_id} - '{deleted_text}'")
                
                snippet = deleted_text[:50] + "..." if len(deleted_text) > 50 else deleted_text
                return Response({
                    "success": True, 
                    "message": "Memory deleted.",
                    "deleted_text": snippet
                }, status=status.HTTP_200_OK)

            memory_to_delete = None

            if not target_text:
                # 1. PANIC MODE: User typed "/delete" (No args)
                # Delete the absolute last memory created (Undo)
                memory_to_delete = Memory.objects.filter(project=project).order_by('-created_at').first()
            
            else:
                # 0. SAFETY LOCK (NEW) 🛡️
                # Prevent deleting "500" (too generic) or "ve" (stop word)
                is_numeric = target_text.isdigit()
                if (is_numeric and len(target_text) < 4) or (not is_numeric and len(target_text) < 3):
                    return Response({
                        "success": False,
                        "message": "⚠️ Güvenlik: Arama terimi çok kısa veya genel. Lütfen daha spesifik olun (Örn: 'bütçe 500')."
                    }, status=status.HTTP_400_BAD_REQUEST)

                # 2. SNIPER MODE: User typed "/delete keyword"
                
                # A) Priority 1: Unaccented Exact-ish Match (Text OR Tags)
                # Handles "butce" -> "bütçe", "sifre" -> "şifre"
                # Note: We cast tags to text to allow string searching
                memory_to_delete = Memory.objects.filter(project=project) \
                    .annotate(tags_as_text=Cast('tags', output_field=TextField())) \
                    .filter(
                        Q(raw_text__unaccent__icontains=target_text) | 
                        Q(tags_as_text__unaccent__icontains=target_text)
                    ).order_by('-created_at').first()

                # B) Priority 2: Fuzzy Match (ONLY for words >= 4 chars)
                # We skip fuzzy for short words to prevent accidents
                if not memory_to_delete and len(target_text) >= 4:
                    print(f"🔍 Unaccent match failed for '{target_text}'. Trying Trigram...")
                    
                    memory_to_delete = Memory.objects.filter(project=project) \
                        .annotate(tags_as_text=Cast('tags', output_field=TextField())) \
                        .annotate(
                            sim_text=TrigramSimilarity('raw_text', target_text),
                            sim_tags=TrigramSimilarity('tags_as_text', target_text)
                        ) \
                        .filter(Q(sim_text__gt=0.4) | Q(sim_tags__gt=0.4)) \
                        .order_by('-created_at') \
                        .first() 
                        # Note: Ordering by created_at is safer for 'Undo' logic than similarity score alone.

            if memory_to_delete:
                deleted_text = memory_to_delete.raw_text
                memory_to_delete.delete()
                print(f"🗑️ HARD DELETE: '{deleted_text}'")
                
                # Return snippet for confirmation
                snippet = deleted_text[:50] + "..." if len(deleted_text) > 50 else deleted_text
                return Response({
                    "success": True, 
                    "message": "Memory deleted.",
                    "deleted_text": snippet
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    "success": False, 
                    "message": f"Silinecek kayıt bulunamadı: '{target_text}'"
                }, status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class ProjectExportView(views.APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        project_id = request.data.get('project_id')
        export_format = request.data.get('format', 'md')  # 'md' or 'pdf'
        
        if not project_id:
            return Response({"error": "Project ID required"}, status=status.HTTP_400_BAD_REQUEST)
            
        # Check permissions
        project = get_object_or_404(Project, id=project_id)
        if project.user != request.user:
            return Response({"error": "Unauthorized project access"}, status=status.HTTP_403_FORBIDDEN)
            
        # Fetch all memories
        memories = Memory.objects.filter(project=project).order_by('created_at')
        
        if not memories.exists():
            return Response({"error": "No memories found for this project"}, status=status.HTTP_404_NOT_FOUND)
            
        # ---------------- CACHING LOGIC ----------------
        # Calculate Data Hash (Fingerprint of current state)
        memory_fingerprints = memories.values_list('id', 'created_at')
        fingerprint_str = "".join([f"{mid}-{mtime}" for mid, mtime in memory_fingerprints])
        data_hash = hashlib.md5(fingerprint_str.encode('utf-8')).hexdigest()

        # Check Cache
        cached_report = ProjectReport.objects.filter(project=project, data_hash=data_hash).first()
        
        if cached_report:
            print(f"⚡ CACHE HIT: Serving report for hash {data_hash}")
            report_markdown = cached_report.markdown_content
        else:
            print(f"🐢 CACHE MISS: Generating new report for hash {data_hash}")
            memory_data = []
            for mem in memories:
                memory_data.append({
                    "raw_text": mem.raw_text,
                    "category": mem.category,
                    "created_at": mem.created_at.strftime("%Y-%m-%d %H:%M:%S")
                })
                
            # Generate Report using AI (Markdown)
            report_markdown = ai_services.generate_project_report(memory_data)
            
            # Save to Cache
            ProjectReport.objects.create(
                project=project,
                markdown_content=report_markdown,
                data_hash=data_hash
            )
        
        if export_format == 'pdf':
            # Convert Markdown -> HTML
            html_content = markdown.markdown(report_markdown)
            
            # Robust styling for PDF with Local DejaVu Sans (Multi-language support)
            full_html = f"""
            <html>
            <head>
                <meta charset="UTF-8">
                <style>
                    @page {{ size: A4; margin: 1cm; }}
                    @font-face {{
                        font-family: 'DejaVuSans';
                        src: url('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf');
                    }}
                    body {{ 
                        font-family: 'DejaVuSans', sans-serif; 
                        font-size: 12px; 
                    }}
                    h1 {{ color: #333; font-size: 18px; border-bottom: 1px solid #ccc; padding-bottom: 5px; }}
                    h2 {{ color: #555; font-size: 14px; margin-top: 15px; }}
                    ul {{ margin-left: 20px; }}
                    li {{ margin-bottom: 5px; }}
                    strong, b {{ font-weight: bold; }}
                </style>
            </head>
            <body>
                <h1>Project Report: {project.name}</h1>
                {html_content}
            </body>
            </html>
            """
            
            # Generate PDF
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="{project.name}_Report.pdf"'
            
            # Encode HTML to UTF-8 before passing to pisa
            pisa_status = pisa.CreatePDF(full_html.encode('utf-8'), dest=response, encoding='utf-8')
            
            if pisa_status.err:
                return Response({"error": "Error generating PDF"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                
            return response
        
        # Default: Return JSON with Markdown
        return Response({
            "project_name": project.name,
            "report": report_markdown
        }, status=status.HTTP_200_OK)

class SiteConfigView(views.APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        sites_config = {
            'chatgpt.com': {
                'button': 'button[data-testid="send-button"], button[data-testid="fruitjuice-send-button"], #composer-submit-button',
                'stopButtonSelector': 'button[aria-label="Stop generating"], button[data-testid="stop-button"]',
                'streamingSelector': '.result-streaming',
                'userMsg': 'div[data-message-author-role="user"]',
                'aiMsg': 'div[data-message-author-role="assistant"]'
            },
            'gemini.google.com': {
                'button': '.send-button, button:has(mat-icon[data-mat-icon-name="send"]), button:has(mat-icon[fonticon="send"])',
                'stopButtonSelector': 'button[aria-label="Stop response"]',
                'streamingSelector': '.streaming',
                'userMsg': ['.query-text', '.user-query', 'div[data-message-author-role="user"]'],
                'aiMsg': ['.markdown', '.model-response', 'message-content']
            },
            'chat.deepseek.com': {
                'button': 'div[role="button"]:has(svg)',
                'stopButtonSelector': ['div[role="button"]:has(svg rect)', '.ds-stop-button', '[aria-label="Stop"]'],
                'streamingSelector': '.ds-markdown--assistant.streaming',
                'userMsg': ['div.fbb737a4', '.ds-markdown--user'],
                'aiMsg': ['.ds-markdown']
            },
            'chat.mistral.ai': {
                'button': 'button[aria-label="Send query"], button:has(svg)',
                'stopButtonSelector': 'button[aria-label="Stop generating"]',
                'streamingSelector': '.animate-pulse',
                'userMsg': ['.bg-basic-gray-alpha-4 .select-text', 'div.ms-auto .select-text', '.select-text'],
                'aiMsg': ['div[data-message-part-type="answer"]', '.markdown-container-style', '.prose']
            },
            'perplexity.ai': {
                'button': 'button[aria-label="Submit"], button[aria-label="Ask"]',
                'stopButtonSelector': 'button[aria-label="Stop"]',
                'streamingSelector': '.animate-pulse',
                'userMsg': ['h1 .select-text', 'div[class*="group/query"] .select-text', '.font-display'],
                'aiMsg': ['.prose', 'div[dir="auto"]']
            }
        }
        return Response(sites_config, status=status.HTTP_200_OK)
