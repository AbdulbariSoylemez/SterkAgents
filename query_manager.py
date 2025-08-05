import os
import logging
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
        self.collection_path = Path(base_persist_directory) / collection_name
        self.videos_directory = self.collection_path.parent.parent / "Education_video" / collection_name

        if not self.collection_path.exists():
            raise FileNotFoundError(f"Collection not found: {self.collection_path}")
        if not self.videos_directory.exists():
            raise FileNotFoundError(f"Videos directory not found: {self.videos_directory}")

    def _initialize_components(self) -> None:
        logger.info("Initializing multimodal RAG components...")
        
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

    # UPDATED: Performance measurement has been added into this method.
    def _retrieve_context_and_image(self, question: str) -> Tuple[List[Document], Optional[Image.Image]]:
        """Retrieve relevant documents and extract the frame from the most relevant video."""
        # 1. Measure vector search time
        retrieval_start_time = time.perf_counter()
        retrieved_docs = self.retriever.invoke(question)
        retrieval_end_time = time.perf_counter()
        logger.info(f"PERF: Vector database search (retrieval) took { (retrieval_end_time - retrieval_start_time) * 1000:.2f} ms.")

        if not retrieved_docs:
            return [], None

        # 2. Measure video frame extraction time
        frame_extraction_start_time = time.perf_counter()
        most_relevant_doc = retrieved_docs[0]
        metadata = most_relevant_doc.metadata
        video_path = self.videos_directory / metadata['video_title']
        frame_image = get_frame_from_video(str(video_path), metadata['start_ms'])
        frame_extraction_end_time = time.perf_counter()
        logger.info(f"PERF: Video frame extraction took { (frame_extraction_end_time - frame_extraction_start_time) * 1000:.2f} ms.")

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

            context_text += f"--- Source Document {i+1} ---\n"
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
            **CORE TASK & RULES**

            **RULE #1: PRIMARY TASK - Answering from Video Content**
            If the user's question is related to the provided video content, you MUST follow these rules:
            - Answer ONLY with information from the `SOURCE DOCUMENTS`. Do not use external knowledge.
            - Start your response directly with the Turkish phrase: "Bu konuda videoda..."
            - Summarize the main point in 1-2 sentences.
            - List key details using bullet points (*). Cite the source at the end of each bullet point: [Video: title, mm:ss]
            - If the answer is not in the videos, state ONLY the Turkish sentence: "Bu konu videolarda ele alınmamış."
            - End the response with the Turkish phrase: "Başka soruların varsa sorabilirsin!"

            **RULE #2: EXCEPTION - Answering Off-Topic Scientific Questions**
            If the user's question is NOT related to the video content BUT is a scientific question (e.g., physics, space, technology, biology), you MUST follow these rules:
            - Switch to a general "helpful assistant" mode for this answer.
            - Provide a concise, accurate, and scientific answer.
            - DO NOT use the video-specific formatting (e.g., no "Bu konuda videoda..." start, no video citations).
            - Keep the answer direct and easy to understand.
            - After providing the scientific answer, gently guide the user back to the primary topic with the Turkish phrase: "Umarım bu açıklama yardımcı olmuştur. Derslerle ilgili başka sorun olursa, yine buradayım!"

            **RULE #3: Handling Other Off-Topic Questions**
            If the question is not related to the videos AND not a scientific question, state ONLY the Turkish sentence: "Ben bir eğitim asistanıyım ve sadece ders içerikleri veya genel bilimsel konularda yardımcı olabilirim."

            **IMPORTANT:**
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

    # UPDATED: General and LLM-specific performance measurement added to the main `ask` method.
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
        
        # 3. Measure the duration of the LLM API call
        llm_start_time = time.perf_counter()
        response = self.llm.invoke(model_input)
        llm_end_time = time.perf_counter()
        logger.info(f"PERF: LLM API call (Gemini) took { (llm_end_time - llm_start_time) * 1000:.2f} ms.")
        
        total_end_time = time.perf_counter()
        logger.info(f"PERF: Total question answering time took { (total_end_time - total_start_time) * 1000:.2f} ms.")

        return {
            "answer": response.content,
            "source_documents": retrieved_docs
        }