from typing import List, Dict, Any, Optional, Tuple
from django.conf import settings
from django.core.cache import cache
from django.db.models import Q
import re
import logging
from functools import lru_cache

# Optional imports - gracefully handle if not available
try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    np = None
    logger = logging.getLogger(__name__)
    logger.warning("NumPy not available, semantic search will be disabled")

logger = logging.getLogger(__name__)


class VectorSearchService:
    """Enhanced vector search service with semantic embeddings using sentence-transformers"""
    
    def __init__(self):
        self.model = None
        self.embeddings_cache = {}
        self._load_model()
        
        # Keyword categories for intent detection and hybrid search
        self.keyword_categories = {
            'schedule': ['class', 'schedule', 'timetable', 'when', 'time', 'today', 'tomorrow', 'next class'],
            'academic': ['course', 'exam', 'assignment', 'grade', 'study', 'semester', 'credit', 'gpa'],
            'policy': ['rule', 'policy', 'regulation', 'requirement', 'guideline', 'regulation'],
            'procedure': ['how to', 'process', 'step', 'procedure', 'postpone', 'defer', 'withdraw', 'register', 'registration', 'enroll', 'enrollment', 'sign up', 'apply', 'application'],
            'calendar': ['event', 'holiday', 'break', 'exam period', 'registration period', 'deadline'],
            'navigation': ['where', 'how to find', 'navigate', 'go to', 'access', 'feature'],
            'faq': ['what is', 'can i', 'do i need', 'should i', 'is it possible', 'about'],
            'academic_advice': ['advice', 'help with', 'struggling', 'difficulty', 'recommendation', 'suggestion'],
            'program_info': ['program', 'degree', 'major', 'curriculum', 'requirements', 'prerequisites'],
        }
        
        # Category to document category mapping
        self.category_map = {
            'schedule': 'schedule',
            'academic': 'guide',
            'policy': 'policy',
            'procedure': 'procedure',
            'calendar': 'calendar',
            'navigation': 'navigation',
            'faq': 'faq',
            'academic_advice': 'academic_advice',
            'program_info': 'program_info',
        }
    
    def _load_model(self):
        """Lazy load the sentence transformer model with graceful error handling"""
        self.model = None
        self.index = None
        
        # Check if numpy is available first
        if not NUMPY_AVAILABLE:
            logger.warning("NumPy not available, semantic search disabled. Using keyword search only.")
            return
        
        try:
            # Try importing sentence-transformers
            from sentence_transformers import SentenceTransformer
            model_name = getattr(settings, 'SENTENCE_TRANSFORMER_MODEL', 'all-MiniLM-L6-v2')
            logger.info(f"Loading sentence transformer model: {model_name}")
            
            # Try to load the model
            self.model = SentenceTransformer(model_name)
            logger.info("Sentence transformer model loaded successfully")
            
            # Try to initialize FAISS if available
            try:
                import faiss
                self.faiss_available = True
            except ImportError:
                self.faiss_available = False
                logger.info("FAISS not available, using simple similarity search")
                
        except ImportError as e:
            logger.warning(f"sentence-transformers not installed or import failed: {e}. Falling back to keyword search.")
            self.model = None
        except OSError as e:
            # Handle DLL errors on Windows
            if "DLL" in str(e) or "dynamic link library" in str(e).lower():
                logger.warning(f"PyTorch DLL error (likely Windows compatibility issue): {e}. Falling back to keyword search.")
            else:
                logger.error(f"OS error loading sentence transformer model: {e}. Falling back to keyword search.")
            self.model = None
        except Exception as e:
            error_msg = str(e).lower()
            if "dll" in error_msg or "dynamic link" in error_msg:
                logger.warning(f"PyTorch DLL initialization failed: {e}. Falling back to keyword search.")
            else:
                logger.error(f"Error loading sentence transformer model: {e}. Falling back to keyword search.")
            self.model = None
    
    @lru_cache(maxsize=1000)
    def _get_embedding(self, text: str):
        """Get embedding for text with caching"""
        if self.model is None or not NUMPY_AVAILABLE:
            return None
        
        try:
            # Normalize text
            text = text.strip()[:512]  # Limit length for efficiency
            embedding = self.model.encode(text, convert_to_numpy=True, show_progress_bar=False)
            return embedding
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            return None
    
    def _categorize_query(self, query: str) -> List[str]:
        """Categorize query to determine relevant document types"""
        query_lower = query.lower()
        categories = []
        
        for category, keywords in self.keyword_categories.items():
            if any(keyword in query_lower for keyword in keywords):
                categories.append(category)
        
        return categories if categories else ['faq']  # Default to FAQ
    
    def _extract_keywords(self, query: str) -> List[str]:
        """Extract important keywords from query"""
        stop_words = {'the', 'a', 'an', 'is', 'are', 'what', 'how', 'when', 'where', 'i', 'me', 'my', 'can', 'do', 'does'}
        
        words = re.findall(r'\b\w+\b', query.lower())
        keywords = [w for w in words if w not in stop_words and len(w) > 2]
        
        return keywords[:8]  # Top 8 keywords
    
    def _calculate_semantic_similarity(self, query_embedding, doc_text: str) -> float:
        """Calculate semantic similarity using cosine similarity"""
        if query_embedding is None or not NUMPY_AVAILABLE or np is None:
            return 0.0
        
        try:
            doc_embedding = self._get_embedding(doc_text[:512])  # Limit length
            if doc_embedding is None:
                return 0.0
            
            # Cosine similarity
            similarity = np.dot(query_embedding, doc_embedding) / (
                np.linalg.norm(query_embedding) * np.linalg.norm(doc_embedding)
            )
            return float(similarity)
        except Exception as e:
            logger.error(f"Error calculating semantic similarity: {e}")
            return 0.0
    
    def _calculate_keyword_relevance(self, query: str, title: str, content: str, tags: str = "") -> float:
        """Calculate keyword-based relevance score (fallback/hybrid)"""
        score = 0.0
        query_lower = query.lower()
        title_lower = title.lower()
        content_lower = content.lower()
        tags_lower = tags.lower() if tags else ""
        
        keywords = self._extract_keywords(query)
        
        # If no keywords extracted, use the whole query as a keyword
        if not keywords:
            keywords = [query_lower.strip()]
        
        for keyword in keywords:
            # Title matches are most valuable
            if keyword in title_lower:
                score += 10.0  # Increased from 5.0
            # Tag matches are very valuable
            if keyword in tags_lower:
                score += 8.0  # Increased from 4.0
            # Content matches
            if keyword in content_lower:
                score += 2.0  # Increased from 1.0
        
        # Exact phrase match bonus (very high)
        if query_lower in content_lower or query_lower in title_lower:
            score += 20.0  # Increased from 10.0
        
        # Partial phrase match
        query_words = query_lower.split()
        if len(query_words) > 1:
            # Try 2-word and 3-word phrases
            for phrase_len in [2, 3]:
                phrase = " ".join(query_words[:phrase_len])
                if phrase in content_lower:
                    score += 10.0  # Increased from 7.0
                if phrase in title_lower:
                    score += 15.0
        
        # Word count match - if most query words appear in title/content
        if len(query_words) > 1:
            matching_words = sum(1 for word in query_words if word in title_lower or word in content_lower)
            if matching_words >= len(query_words) * 0.6:  # 60% of words match
                score += 12.0
        
        return score
    
    def build_index(self, university_id: Optional[int] = None) -> bool:
        """Build or load vector index for knowledge documents"""
        try:
            from .models import KnowledgeDocument
            
            queryset = KnowledgeDocument.objects.filter(is_active=True)
            if university_id:
                queryset = queryset.filter(Q(university_id=university_id) | Q(university__isnull=True))
            
            doc_count = queryset.count()
            logger.info(f"Knowledge base contains {doc_count} active documents")
            
            return doc_count > 0
        except Exception as e:
            logger.error(f"Error building vector index: {e}")
            return False
    
    def search(self, query: str, top_k: int = 5, university_id: Optional[int] = None, 
               use_semantic: bool = True, use_hybrid: bool = True) -> List[Dict[str, Any]]:
        """Enhanced search with semantic embeddings and hybrid approach"""
        try:
            # OPTIMIZATION: Check cache first with normalized query
            # Normalize query for better cache hits (lowercase, strip whitespace)
            normalized_query = query.lower().strip()
            cache_key = f"rag_search_{hash(normalized_query)}_{university_id}_{top_k}"
            cached_results = cache.get(cache_key)
            if cached_results:
                logger.info(f"RAG cache hit for query: {query[:50]}")
                return cached_results
            
            from .models import KnowledgeDocument
            
            # Get query embedding if semantic search is enabled
            query_embedding = None
            if use_semantic and self.model is not None:
                query_embedding = self._get_embedding(query)
            
            # Categorize query for intent detection
            categories = self._categorize_query(query)
            keywords = self._extract_keywords(query)
            
            logger.info(f"🔍 RAG SEARCH START")
            logger.info(f"   Query: '{query}'")
            logger.info(f"   Detected Categories: {categories}")
            logger.info(f"   Extracted Keywords: {keywords}")
            logger.info(f"   University ID: {university_id}")
            logger.info(f"   Top K: {top_k}")
            
            # Build base queryset
            queryset = KnowledgeDocument.objects.filter(is_active=True)
            if university_id:
                queryset = queryset.filter(Q(university_id=university_id) | Q(university__isnull=True))
            
            # Try to filter by category if detected, but don't be too restrictive
            original_queryset = queryset
            if categories:
                doc_categories = [self.category_map.get(c, 'faq') for c in categories]
                category_queryset = queryset.filter(category__in=doc_categories)
                # Get candidate documents from category-filtered queryset
                candidate_docs = list(category_queryset.select_related('university')[:top_k * 3])
                logger.info(f"Category filter: {doc_categories}, found {len(candidate_docs)} documents")
            else:
                candidate_docs = []
            
            # If no category match or very few results, also search all documents
            if len(candidate_docs) < top_k:
                # Get additional documents from all categories
                all_docs = list(original_queryset.select_related('university')[:top_k * 5])
                # Combine and deduplicate
                existing_ids = {doc.id for doc in candidate_docs}
                for doc in all_docs:
                    if doc.id not in existing_ids:
                        candidate_docs.append(doc)
                        if len(candidate_docs) >= top_k * 3:
                            break
                logger.info(f"Expanded search: total {len(candidate_docs)} candidate documents")
            
            # Score and rank documents
            scored_docs = []
            for doc in candidate_docs:
                # Semantic similarity score
                semantic_score = 0.0
                if query_embedding is not None and use_semantic:
                    # Combine title and content for embedding
                    doc_text = f"{doc.title}. {doc.content[:300]}"
                    semantic_score = self._calculate_semantic_similarity(query_embedding, doc_text)
                
                # Keyword relevance score
                keyword_score = self._calculate_keyword_relevance(
                    query, doc.title, doc.content, doc.tags or ""
                )
                
                # Hybrid score: combine semantic and keyword
                if use_hybrid and semantic_score > 0:
                    # Weighted combination: 70% semantic, 30% keyword
                    hybrid_score = (semantic_score * 0.7) + (min(keyword_score / 30.0, 1.0) * 0.3)
                elif semantic_score > 0:
                    hybrid_score = semantic_score
                else:
                    # When semantic search unavailable, rely more on keyword score
                    # Normalize keyword score to 0-1 range (keyword_score can be 0-50+)
                    hybrid_score = min(keyword_score / 30.0, 1.0)  # Increased divisor from 20.0 to 30.0 for better normalization
                    # If keyword score is high, boost it
                    if keyword_score > 15:
                        hybrid_score = min(hybrid_score * 1.2, 1.0)
                
                # Boost score based on priority and usage
                priority_boost = doc.priority / 10.0  # Normalize to 0-1
                usage_boost = min(doc.usage_count / 100.0, 0.2)  # Cap at 0.2
                
                final_score = hybrid_score * (1.0 + priority_boost * 0.1 + usage_boost)
                
                # Ensure minimum score for documents with keyword matches
                if keyword_score > 5 and final_score < 0.1:
                    final_score = 0.15  # Minimum relevance for documents with keyword matches
                
                scored_docs.append({
                    'id': str(doc.id),
                    'title': doc.title,
                    'content': doc.content,
                    'category': doc.category,
                    'relevance': final_score,
                    'semantic_score': semantic_score,
                    'keyword_score': keyword_score,
                    'document': doc,  # Keep reference for usage tracking
                })
            
            # Sort by relevance
            scored_docs.sort(key=lambda x: x['relevance'], reverse=True)
            
            # Filter out documents with very low relevance (but be lenient for keyword-only search)
            min_relevance = 0.01 if query_embedding is None else 0.05  # Lower threshold when semantic search unavailable
            filtered_docs = [doc for doc in scored_docs if doc['relevance'] >= min_relevance]
            
            # Take top_k results (or all if fewer than top_k)
            results = filtered_docs[:top_k] if filtered_docs else scored_docs[:top_k]  # Fallback to all if filtered is empty
            
            # Log search details for debugging - make it very visible
            if results:
                logger.info(f"✅ FOUND {len(results)} DOCUMENTS")
                for i, result in enumerate(results[:3], 1):  # Show top 3
                    logger.info(f"   {i}. '{result.get('title', 'N/A')}'")
                    logger.info(f"      Relevance: {result.get('relevance', 0):.3f}")
                    logger.info(f"      Keyword Score: {result.get('keyword_score', 0):.1f}")
                    logger.info(f"      Semantic Score: {result.get('semantic_score', 0):.3f}")
                    logger.info(f"      Category: {result.get('category', 'N/A')}")
            else:
                logger.warning(f"❌ NO RESULTS FOUND")
                logger.warning(f"   Total documents scored: {len(scored_docs)}")
                logger.warning(f"   Minimum relevance threshold: {min_relevance}")
                if scored_docs:
                    logger.warning(f"   Best scored document: '{scored_docs[0].get('title', 'N/A')}'")
                    logger.warning(f"   Best relevance: {scored_docs[0].get('relevance', 0):.3f}")
                    logger.warning(f"   Best keyword_score: {scored_docs[0].get('keyword_score', 0):.1f}")
                else:
                    logger.warning(f"   No documents were scored at all!")
                    logger.warning(f"   Candidate documents: {len(candidate_docs)}")
                    logger.warning(f"   Active documents in DB: {KnowledgeDocument.objects.filter(is_active=True).count()}")
            
            # Track usage for retrieved documents
            for result in results:
                doc = result.get('document')
                if doc:
                    try:
                        doc.increment_usage()
                    except Exception as e:
                        logger.warning(f"Error incrementing usage for doc {doc.id}: {e}")
                    # Remove document reference from result
                    result.pop('document', None)
            
                    # OPTIMIZATION: Cache results longer for better performance (1 hour for common queries)
                    if results:
                        # Cache for 1 hour - knowledge base doesn't change frequently
                        cache.set(cache_key, results, 3600)
                        logger.info(f"Found {len(results)} relevant documents (best relevance: {results[0]['relevance']:.3f})")
                    else:
                        logger.info("No relevant documents found")
                        # Cache empty results for shorter time (15 min) to allow for new documents
                        cache.set(cache_key, [], 900)
            
            return results
            
        except Exception as e:
            logger.error(f"Error searching knowledge base: {e}", exc_info=True)
            return []
    
    def format_for_prompt(self, results: List[Dict[str, Any]], max_chars: int = 500) -> str:
        """Format search results for prompt inclusion with token optimization"""
        if not results:
            return ""
        
        formatted = []
        total_chars = 0
        
        for i, result in enumerate(results, 1):
            title = result.get("title", "Document")
            content = result.get("content", "")
            category = result.get("category", "")
            
            # Limit content length intelligently
            remaining_chars = max_chars - total_chars
            if remaining_chars <= 50:
                break
            
            # Prioritize important content - get more content for procedures
            if category == 'procedure':
                # For procedures, try to get step-by-step info
                lines = content.split('\n')
                procedure_lines = [l for l in lines if re.match(r'^\d+\.', l) or l.strip().startswith('-')]
                if procedure_lines:
                    # Get more steps for procedures
                    content_snippet = '\n'.join(procedure_lines[:10])[:min(300, remaining_chars - 50)]
                else:
                    content_snippet = content[:min(250, remaining_chars - 50)]
            else:
                content_snippet = content[:min(200, remaining_chars - 50)]
            
            # Make it clearer that this is knowledge base information
            entry = f"═══════════════════════════════════════════════════════════════\nKNOWLEDGE BASE DOCUMENT {i}\n═══════════════════════════════════════════════════════════════\nCategory: {category.upper()}\nTitle: {title}\n\nContent:\n{content_snippet}\n═══════════════════════════════════════════════════════════════\n"
            
            formatted.append(entry)
            total_chars += len(entry)
        
        if formatted:
            return "\n".join(formatted)
        
        return ""
    
    def search_navigation(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """Search site navigation features"""
        try:
            from .models import SiteNavigation
            
            nav_items = SiteNavigation.objects.filter(is_active=True)
            
            # Simple keyword matching for navigation
            query_lower = query.lower()
            keywords = self._extract_keywords(query)
            
            results = []
            for nav in nav_items:
                score = 0.0
                nav_text = f"{nav.name} {nav.description} {nav.keywords}".lower()
                
                for keyword in keywords:
                    if keyword in nav_text:
                        score += 1.0
                
                if score > 0:
                    results.append({
                        'name': nav.name,
                        'route': nav.route,
                        'description': nav.description,
                        'relevance': score,
                    })
            
            results.sort(key=lambda x: x['relevance'], reverse=True)
            return results[:top_k]
            
        except Exception as e:
            logger.error(f"Error searching navigation: {e}")
            return []
