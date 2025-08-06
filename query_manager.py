import os
import logging
import uuid
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
import base64
import io
from PIL import Image
import time

from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from langchain_community.vectorstores.chroma import Chroma
from langchain_core.documents import Document

from extract_image_from_video import get_frame_from_video

logger = logging.getLogger(__name__)


def is_valid_uuid(uuid_str: str) -> bool:
    """Check if a string is a valid UUID."""
    try:
        uuid_obj = uuid.UUID(uuid_str)
        return str(uuid_obj) == uuid_str
    except (ValueError, AttributeError):
        return False

def find_latest_collection_uuid(collection_path: Path) -> Optional[str]:
    """
    Find the most recent UUID subdirectory in the collection path.
    Returns the UUID string if found, None otherwise.
    """
    if not collection_path.exists():
        return None
    
    uuid_dirs = [d for d in collection_path.iterdir() if d.is_dir() and is_valid_uuid(d.name)]
    
    if not uuid_dirs:
        return None
    
    # Sort by directory creation time (newest first)
    uuid_dirs.sort(key=lambda d: d.stat().st_mtime, reverse=True)
    return uuid_dirs[0].name

def is_valid_collection(collection_path: Path) -> bool:
    """
    Check if a collection path contains a valid ChromaDB collection.
    """
    if not collection_path.exists() or not collection_path.is_dir():
        return False
    
    # Önce doğrudan collection_path'te chroma.sqlite3 var mı kontrol et
    if (collection_path / "chroma.sqlite3").exists():
        return True
    
    # UUID alt dizinlerini kontrol et
    uuid_dirs = [d for d in collection_path.iterdir() if d.is_dir() and is_valid_uuid(d.name)]
    
    for uuid_dir in uuid_dirs:
        if (uuid_dir / "chroma.sqlite3").exists():
            return True
    
    return False

def get_collection_dir(collection_name: str) -> Path:
    """Get the collection directory path, checking both slugified and original names."""
    from slugify import slugify
    
    base = Path("./rag_collections")
    slug = slugify(collection_name)
    slug_dir = base / slug
    orig_dir = base / collection_name
    
    # Debug logging
    logger.info(f"Looking for collection '{collection_name}'")
    logger.info(f"Checking slug_dir: {slug_dir} (exists: {slug_dir.exists()})")
    logger.info(f"Checking orig_dir: {orig_dir} (exists: {orig_dir.exists()})")
    
    # Check if either directory exists and is valid
    if slug_dir.exists() and is_valid_collection(slug_dir):
        logger.info(f"Found valid collection at slug_dir: {slug_dir}")
        return slug_dir
    elif orig_dir.exists() and is_valid_collection(orig_dir):
        logger.info(f"Found valid collection at orig_dir: {orig_dir}")
        return orig_dir
    
    # If neither exists or is valid, prefer the slugified version for new collections
    logger.info(f"No valid collection found, will use slug_dir: {slug_dir}")
    return slug_dir

def find_original_dir_name(collection_name: str) -> str:
    """Find the original directory name for a given collection name."""
    # Import VIDEO_LIST from web_api_service to get the correct mapping
    try:
        from web_api_service import VIDEO_LIST
        for video in VIDEO_LIST:
            if video.get("collection_name") == collection_name:
                return video.get("original_dir_name", collection_name)
    except ImportError:
        pass
    
    # Fallback: check the actual directory structure
    education_dir = Path("Education_video")
    if education_dir.exists():
        for dir_path in education_dir.iterdir():
            if dir_path.is_dir() and dir_path.name.lower().replace(" ", "_") == collection_name:
                return dir_path.name
    
    return collection_name

def pil_to_base64(image: Image.Image, format: str = "jpeg") -> str:
    """Convert PIL Image to base64 string."""
    buffered = io.BytesIO()
    image.save(buffered, format=format)
    img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
    return f"data:image/{format};base64,{img_str}"


class QueryManager:
    """Multimodal RAG query manager for video-based question answering."""

    def __init__(self, collection_name: str, base_persist_directory: str = "./rag_collections"):
        self._validate_environment()
        self._setup_paths(collection_name, base_persist_directory)
        self._initialize_components()

    def _validate_environment(self) -> None:
        if not os.getenv("GOOGLE_API_KEY"):
            raise ValueError("GOOGLE_API_KEY environment variable not found.")

    def _setup_paths(self, collection_name: str, base_persist_directory: str) -> None:
        # Get the correct collection directory path
        base_collection_path = get_collection_dir(collection_name)
        
        # Debug logging
        logger.info(f"Base collection path: {base_collection_path}")
        
        # Check if base_collection_path has chroma.sqlite3 directly
        if (base_collection_path / "chroma.sqlite3").exists():
            logger.info(f"Using base collection path directly: {base_collection_path}")
            self.collection_path = base_collection_path
        else:
            # Look for UUID subdirectories
            latest_uuid = find_latest_collection_uuid(base_collection_path)
            if not latest_uuid:
                raise FileNotFoundError(f"No valid collection UUID found for: {collection_name}")
            
            self.collection_path = base_collection_path / latest_uuid
            logger.info(f"Using UUID subdirectory: {self.collection_path}")
        
        # Get the original directory name for videos directory
        original_dir_name = find_original_dir_name(collection_name)
        self.videos_directory = Path("Education_video") / original_dir_name

        if not self.collection_path.exists():
            raise FileNotFoundError(f"Collection path not found: {self.collection_path}")
        if not self.videos_directory.exists():
            raise FileNotFoundError(f"Videos directory not found: {self.videos_directory}")
        
        logger.info(f"Final collection path: {self.collection_path}")
        logger.info(f"Videos directory: {self.videos_directory}")

    def _initialize_components(self) -> None:
        logger.info(f"Initializing multimodal RAG components from: {self.collection_path}")

        self.embeddings = GoogleGenerativeAIEmbeddings(model="models/embedding-001")
        self.vector_store = Chroma(
            persist_directory=str(self.collection_path),
            embedding_function=self.embeddings
        )
        self.llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", temperature=0.3)
        self.retriever = self.vector_store.as_retriever(
            search_type="mmr",
            search_kwargs={"k": 4, "fetch_k": 20}
        )

        logger.info("Multimodal RAG query manager initialized successfully.")

    def _retrieve_context_and_image(self, question: str) -> Tuple[List[Document], Optional[Image.Image]]:
        """Retrieve relevant documents and extract the frame from the most relevant video."""
        retrieval_start_time = time.perf_counter()
        
        # Debug: Check vector store collection count
        try:
            collection_count = self.vector_store._collection.count()
            logger.info(f"Vector store collection count: {collection_count}")
        except Exception as e:
            logger.error(f"Error getting collection count: {e}")
        
        retrieved_docs = self.retriever.invoke(question)
        retrieval_end_time = time.perf_counter()
        logger.info(
            f"PERF: Vector database search (retrieval) took {(retrieval_end_time - retrieval_start_time) * 1000:.2f} ms.")
        logger.info(f"Retrieved {len(retrieved_docs)} documents")

        if not retrieved_docs:
            logger.warning("No documents retrieved from vector store")
            return [], None

        frame_extraction_start_time = time.perf_counter()
        most_relevant_doc = retrieved_docs[0]
        metadata = most_relevant_doc.metadata
        logger.info(f"Most relevant doc metadata: {metadata}")
        video_title = metadata['video_title']
        # Remove .mp4 extension if it already exists
        if video_title.endswith('.mp4'):
            video_path = self.videos_directory / video_title
        else:
            video_path = self.videos_directory / f"{video_title}.mp4"
        frame_image = get_frame_from_video(str(video_path), metadata['start_ms'])
        frame_extraction_end_time = time.perf_counter()
        logger.info(
            f"PERF: Video frame extraction took {(frame_extraction_end_time - frame_extraction_start_time) * 1000:.2f} ms.")

        return retrieved_docs, frame_image

    def _format_context_for_prompt(self, source_documents: List[Document]) -> str:
        context_text = ""
        for i, doc in enumerate(source_documents):
            metadata = doc.metadata
            video_title = metadata.get('video_title', 'Unknown Video')
            start_ms = metadata.get('start_ms', 0)

            seconds = start_ms // 1000
            minutes = seconds // 60
            remaining_seconds = seconds % 60
            timestamp = f"{minutes:02d}:{remaining_seconds:02d}"

            context_text += f"--- Source Document {i + 1} ---\n"
            context_text += f"Video Title: {video_title}\n"
            context_text += f"Timestamp: {timestamp}\n"
            context_text += f"Content: {doc.page_content}\n\n"

        return context_text

    def _create_prompt(self, formatted_context: str, question: str) -> str:
        return f"""You are "EğitimBot," an expert educational assistant. Your primary purpose is to provide clear and helpful answers to students using information strictly from the provided video transcripts.

            PERSONA:
            - A patient and supportive teacher
            - Professional yet warm
            - Focused on student learning

            ---
            *CORE TASK & RULES*

            *RULE #1: PRIMARY TASK - Answering from Video Content*
            If the user's question is related to the provided video content, you MUST follow these rules:
            - Answer ONLY with information from the SOURCE DOCUMENTS. Do not use external knowledge.
            - Start your response directly with the Turkish phrase: "Eğitim içeriğimize göre...."
            - Summarize the main point in 1-2 sentences.
            - List key details using bullet points Suchlike (⭐).Indicate the source at the end of the most relevant contanet sign: [Video: title, mm:ss]
            - If the answer is not in the videos, state ONLY the Turkish sentence: "Bu konu videolarda ele alınmamış."
            -End the answer with a beautiful Turkish expression: 

            *RULE #2: EXCEPTION - Answering Off-Topic Scientific Questions*
            If the user's question is a contextually relevant question (e.g., if it's about video content), you must follow these rules:          - Switch to a general "helpful assistant" mode for this answer.
            - Provide a concise, accurate, and scientific answer.
            - Keep the answer direct and easy to understand.
            - After providing the scientific answer, gently guide the user back to the primary topic with the Turkish phrase: "Umarım bu açıklama yardımcı olmuştur. Derslerle ilgili başka sorun olursa, yine buradayım!"

            *RULE #3: Handling Other Off-Topic Questions*
            If the question is not related to the videos AND not a scientific question, state ONLY the Turkish sentence: "Ben bir eğitim asistanıyım ve sadece ders içerikleri veya genel bilimsel konularda yardımcı olabilirim."

            *IMPORTANT:*
            - Your final response must ALWAYS be in Turkish.
            - Assess the user's question first to decide which rule to apply (Rule #1, #2, or #3).

            ---
            SOURCE DOCUMENTS (Only for Rule #1):
            {formatted_context}

            QUESTION: {question}

            ANSWER:"""

    def _build_message_content(self, prompt: str, frame_image: Optional[Image.Image]) -> List[Dict[str, Any]]:
        message_content = [{"type": "text", "text": prompt}]

        if frame_image:
            base64_image = pil_to_base64(frame_image)
            message_content.append({
                "type": "image_url",
                "image_url": {"url": base64_image}
            })

        return message_content

    def ask(self, question: str) -> Dict[str, Any]:
        """Process a multimodal question and return the answer with source documents."""
        logger.info(f"Processing multimodal question: '{question}'")
        total_start_time = time.perf_counter()

        retrieved_docs, frame_image = self._retrieve_context_and_image(question)

        if not retrieved_docs:
            return {
                "answer": "No content was found in the videos related to your question.",
                "source_documents": []
            }

        formatted_context = self._format_context_for_prompt(retrieved_docs)
        prompt = self._create_prompt(formatted_context, question)

        message_content = self._build_message_content(prompt, frame_image)
        model_input = [HumanMessage(content=message_content)]

        llm_start_time = time.perf_counter()
        response = self.llm.invoke(model_input)
        llm_end_time = time.perf_counter()
        logger.info(f"PERF: LLM API call (Gemini) took {(llm_end_time - llm_start_time) * 1000:.2f} ms.")

        total_end_time = time.perf_counter()
        logger.info(f"PERF: Total question answering time took {(total_end_time - total_start_time) * 1000:.2f} ms.")

        return {
            "answer": response.content,
            "source_documents": retrieved_docs
        }
