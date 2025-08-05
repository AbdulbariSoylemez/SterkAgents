import logging
import os
from pathlib import Path
from typing import Dict, Any, List, Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, HttpUrl, Field, model_validator

from video_chunks_generator import LocalVideoProcessor, VideoChunker, logger
from create_vector_store import RAGVectorStoreManager, CreateCollectionRequest
from query_manager import QueryManager

class DirectoryRequest(BaseModel):
    """Request model for directory processing."""
    directory_path: str = Field(..., description="Full path to directory containing videos")


class QuestionRequest(BaseModel):
    """Request model for asking questions."""
    collection_name: str = Field(..., description="Name of the collection to query")
    question: str = Field(..., description="User's question")


class SourceDocument(BaseModel):
    """Model for source document information."""
    page_content: str
    metadata: Dict[str, Any]


class CreateCollectionResponse(BaseModel):
    """Response model for collection creation."""
    status: str
    message: str
    collection_path: str
    chunks_added: int


class AnswerResponse(BaseModel):
    """Response model for question answering."""
    answer: str
    source_documents: List[SourceDocument]


# FastAPI Application
app = FastAPI(
    title="Video RAG Pipeline API",
    description="API for processing videos and creating RAG vector collections",
    version="3.1.0"
)


class VideoProcessingService:
    """Service class for video processing operations."""
    
    SUPPORTED_VIDEO_EXTENSIONS = ('.mp4', '.mov', '.mkv', '.avi', '.webm')
    @classmethod
    def process_directory(cls, directory_path: str) -> Dict[str, Any]:
        """Process all videos in a directory."""
        directory = Path(directory_path)
        
        if not directory.exists() or not directory.is_dir():
            raise HTTPException(
                status_code=404, 
                detail=f"Directory not found: {directory_path}"
            )

        collection_name = directory.name
        logger.info(f"Auto-generated collection name: '{collection_name}'")

        processor = LocalVideoProcessor()
        video_chunker = VideoChunker()
        
        all_chunks = []
        processed_files = []
        failed_files = []

        video_files = [
            f for f in directory.iterdir() 
            if f.is_file() and f.suffix.lower() in cls.SUPPORTED_VIDEO_EXTENSIONS
        ]

        if not video_files:
            raise HTTPException(
                status_code=404,
                detail="No supported video files found in directory"
            )

        logger.info(f"Processing {len(video_files)} videos from '{directory_path}'")

        for video_file in video_files:
            try:
                cls._process_single_file(
                    video_file, processor, video_chunker, 
                    all_chunks, processed_files, failed_files
                )
            except Exception as e:
                logger.error(f"Error processing '{video_file.name}': {e}")
                failed_files.append(video_file.name)

        if not all_chunks:
            raise HTTPException(
                status_code=500,
                detail="No RAG data could be created from any video in directory"
            )

        return {
            "collection_name": collection_name,
            "base_persist_directory": "./rag_collections",
            "chunks": all_chunks,
            "summary": {
                "total_chunks_created": len(all_chunks),
                "processed_video_count": len(processed_files),
                "failed_video_count": len(failed_files),
                "processed_files": processed_files,
                "failed_files": failed_files
            }
        }
    
    @staticmethod
    def _process_single_file(video_file, processor, video_chunker, all_chunks, processed_files, failed_files):
        """Process a single video file."""
        logger.info(f"Processing: {video_file}")
        
        transcript_segments, video_title, video_id = processor.get_transcript(str(video_file))
        
        if not transcript_segments:
            logger.warning(f"No transcript for '{video_file.name}', skipping")
            failed_files.append(video_file.name)
            return

        chunks = video_chunker.chunk_transcript(transcript_segments, video_id, video_title)
        
        if not chunks:
            logger.warning(f"No chunks created for '{video_file.name}', skipping")
            failed_files.append(video_file.name)
            return

        all_chunks.extend(chunks)
        processed_files.append(video_file.name)
        logger.info(f"Successfully processed '{video_file.name}' - {len(chunks)} chunks added")


@app.post("/process_directory_for_rag", response_model=Dict[str, Any])
async def process_directory_for_rag(request: DirectoryRequest):
    """Process all videos in a directory for RAG."""
    try:
        return VideoProcessingService.process_directory(request.directory_path)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unexpected error during directory processing: {e}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@app.post("/create_collection", response_model=CreateCollectionResponse)
async def create_vector_store(request: CreateCollectionRequest):
    """Create a vector store collection from processed chunks."""
    try:
        collection_path = Path(request.base_persist_directory) / request.collection_name
        logger.info(f"Creating collection '{request.collection_name}' at: {collection_path}")
        
        rag_manager = RAGVectorStoreManager(persist_directory=str(collection_path))
        chunks_as_dicts = [chunk.dict() for chunk in request.chunks]
        rag_manager.create_and_persist_store(chunks_as_dicts)
        
        return CreateCollectionResponse(
            status="success",
            message=f"Collection '{request.collection_name}' created successfully",
            collection_path=str(collection_path),
            chunks_added=len(request.chunks)
        )
    except Exception as e:
        logger.exception(f"Error creating collection: {e}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@app.post("/ask", response_model=AnswerResponse)
async def ask_question(request: QuestionRequest):
    """Ask a question against a collection."""
    try:
        query_manager = QueryManager(collection_name=request.collection_name)
        result = query_manager.ask(request.question)
        
        return AnswerResponse(
            answer=result["answer"],
            source_documents=[
                SourceDocument(
                    page_content=doc.page_content,
                    metadata=doc.metadata
                ) for doc in result["source_documents"]
            ]
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception(f"Error answering question: {e}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


if __name__ == '__main__':
    uvicorn.run(
        "app:app", 
        host='0.0.0.0', 
        port=5001, 
        reload=False, 
        log_level="info"
    )