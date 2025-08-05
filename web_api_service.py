import os
import logging
import sys
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
import uuid
import time
import threading
import dotenv
import cv2
from functools import lru_cache

from fastapi import FastAPI, Request, HTTPException, Body
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

# Load environment variables from .env file
dotenv.load_dotenv()

# Configure logging - Fix encoding issues
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    encoding='utf-8'  # Fix encoding issues
)
logger = logging.getLogger(__name__)

# Fix OpenMP conflict
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

# Check API key at startup
if not os.getenv("GOOGLE_API_KEY"):
    logger.warning("GOOGLE_API_KEY not found in environment variables. Using fallback method...")
    # Try to load from .env file directly
    env_path = Path(".env")
    if env_path.exists():
        with open(env_path, "r") as f:
            for line in f:
                if line.strip().startswith("GOOGLE_API_KEY="):
                    key = line.strip().split("=", 1)[1].strip().strip('"').strip("'")
                    os.environ["GOOGLE_API_KEY"] = key
                    logger.info("GOOGLE_API_KEY loaded from .env file")
                    break

# Verify API key is loaded
if os.getenv("GOOGLE_API_KEY"):
    api_key = os.getenv("GOOGLE_API_KEY")
    masked_key = f"{api_key[:5]}...{api_key[-5:]}" if len(api_key) > 10 else "***"
    logger.info(f"GOOGLE_API_KEY is set (masked: {masked_key})")
else:
    logger.error("GOOGLE_API_KEY is still not set! Application may not work correctly.")

# Initialize the FastAPI app
app = FastAPI(
    title="SterkAgents Web Service",
    description="Web service for SterkAgents RAG video education platform",
    version="1.0.0"
)

@lru_cache(maxsize=100)
def get_video_duration(video_path: str) -> Tuple[int, str]:
    """
    Get the duration of a video file in seconds and formatted string.
    Uses LRU cache to avoid recalculating durations for the same file.
    
    Args:
        video_path: Path to the video file
        
    Returns:
        Tuple of (duration_seconds, formatted_duration)
    """
    try:
        if not Path(video_path).exists():
            return 0, "~45 dk"
            
        video = cv2.VideoCapture(video_path)
        fps = video.get(cv2.CAP_PROP_FPS)
        frame_count = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
        duration_seconds = int(frame_count / fps) if fps > 0 else 0
        video.release()
        
        # Format duration as minutes and seconds
        minutes = duration_seconds // 60
        seconds = duration_seconds % 60
        formatted_duration = f"{minutes}d {seconds}sn"
        
        return duration_seconds, formatted_duration
    except Exception as e:
        logger.error(f"Error getting video duration: {e}")
        return 0, "~45 dk"

def create_video_list() -> List[Dict[str, Any]]:
    """Create a list of videos from the Education_video directory structure."""
    videos = []
    root_dir = Path("Education_video")

    if not root_dir.exists():
        logger.warning("Education_video directory not found")
        return videos

    for course_dir in root_dir.iterdir():
        if not course_dir.is_dir():
            continue

        course_id = str(uuid.uuid4())
        course_name = course_dir.name
        collection_name = course_name.lower().replace(" ", "_")

        video_files = list(course_dir.glob("**/*.mp4"))
        is_series = len(video_files) > 1

        thumbnail_files = list(course_dir.glob("**/*.jpg")) + list(course_dir.glob("**/*.png"))
        thumbnail = f"/Education_video/{course_name}/{thumbnail_files[0].name}" if thumbnail_files else None

        course_info = {
            "id": course_id,
            "title": course_name.replace("_", " "),
            "description": f"Eğitim: {course_name.replace('_', ' ')}",
            "is_series": is_series,
            "collection_name": collection_name,
            "original_dir_name": course_name,
        }

        if video_files:
            main_video = video_files[0]
            video_path = f"/Education_video/{course_name}/{main_video.name}"
            course_info["video_url"] = video_path
            if thumbnail:
                course_info["thumbnail"] = thumbnail

            if is_series:
                series_videos = []
                total_duration_seconds = 0
                
                # Process all videos in the course
                for idx, video_file in enumerate(sorted(video_files)):
                    # Use original filename as the video title without changing it
                    video_name = video_file.stem
                    video_path = f"/Education_video/{course_name}/{video_file.name}"
                    full_path = str(Path("Education_video") / course_name / video_file.name)
                    
                    # Get video duration using cached function
                    duration_seconds, duration = get_video_duration(full_path)
                    total_duration_seconds += duration_seconds
                    
                    # Add video to series list
                    series_videos.append({
                        "title": video_name,
                        "video_path": video_path,
                        "collection_name": collection_name,
                        "original_dir_name": course_name,
                        "index": idx + 1,
                        "duration": duration
                    })
                
                # Format total duration
                total_minutes = total_duration_seconds // 60
                total_seconds = total_duration_seconds % 60
                total_duration = f"{total_minutes}d {total_seconds}sn"
                course_info["total_duration"] = total_duration
                course_info["series_videos_data"] = series_videos

            videos.append(course_info)

    return videos

def ensure_collection_exists(collection_name: str) -> Dict[str, Any]:
    """
    Check if a collection exists, and if not, create it.
    Creates a single RAG context per course (Education_video subdirectory).
    
    Args:
        collection_name: Name of the collection to check/create
        
    Returns:
        Dict with status and collection information
    """
    try:
        # Check if collection already exists
        collection_path = Path("./rag_collections") / collection_name
        if collection_path.exists() and collection_path.is_dir():
            logger.info(f"Collection '{collection_name}' already exists")
            return {
                "status": "exists",
                "message": f"Collection '{collection_name}' already exists",
                "collection_path": str(collection_path)
            }
        
        # Find the corresponding directory in Education_video (uses cached function)
        original_dir_name = find_original_dir_name(collection_name)
        course_dir = Path("Education_video") / original_dir_name
        
        # Validate course directory
        if not course_dir.exists() or not course_dir.is_dir():
            logger.error(f"Could not find matching directory for collection '{collection_name}'")
            return {
                "status": "error",
                "message": f"Could not find matching directory for collection '{collection_name}'",
                "collection_path": None
            }
        
        # Import here to avoid circular imports
        from app import VideoProcessingService
        from create_vector_store import RAGVectorStoreManager
        
        # Process the entire course directory as a single collection
        logger.info(f"Processing course directory for collection '{collection_name}': {course_dir}")
        start_time = time.time()
        
        # Process directory and get chunks
        processing_result = VideoProcessingService.process_directory(str(course_dir))
        chunks = processing_result.get("chunks", [])
        
        if not chunks:
            logger.error(f"No chunks generated for course '{collection_name}'")
            return {
                "status": "error",
                "message": f"No chunks generated for course '{collection_name}'",
                "collection_path": None
            }
        
        # Create vector store
        rag_manager = RAGVectorStoreManager(persist_directory=str(collection_path))
        rag_manager.create_and_persist_store(chunks)
        
        # Log performance metrics
        elapsed_time = time.time() - start_time
        chunks_count = len(chunks)
        logger.info(f"Course collection '{collection_name}' created in {elapsed_time:.2f} seconds with {chunks_count} chunks")
        
        return {
            "status": "created",
            "message": f"Course collection '{collection_name}' created successfully",
            "collection_path": str(collection_path),
            "chunks_added": chunks_count
        }
    except Exception as e:
        logger.exception(f"Error ensuring collection exists: {e}")
        return {
            "status": "error",
            "message": f"Error creating collection: {str(e)}",
            "collection_path": None
        }

@lru_cache(maxsize=50)
def find_original_dir_name(collection_name: str) -> str:
    """
    Find the original directory name for a given collection name.
    Uses LRU cache to avoid repeated lookups for the same collection.
    """
    # First check in VIDEO_LIST for better performance
    for video in VIDEO_LIST:
        if video.get("collection_name") == collection_name:
            return video.get("original_dir_name", collection_name)
    
    # Try direct search in Education_video as fallback
    education_dir = Path("Education_video")
    if education_dir.exists():
        for dir_path in education_dir.iterdir():
            if dir_path.is_dir() and dir_path.name.lower().replace(" ", "_") == collection_name:
                return dir_path.name
    
    # If not found, return the original collection name
    return collection_name

# Import QueryManager from query_manager.py
from query_manager import QueryManager

# Mount static files directories
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/Education_video", StaticFiles(directory="Education_video"), name="education_video")

# Set up templates
templates = Jinja2Templates(directory="templates")

# Define request models
class QuestionRequest(BaseModel):
    collection_name: str
    question: str

# Create the video list
VIDEO_LIST = create_video_list()

# Define routes
@app.get("/", response_class=HTMLResponse)
async def get_index_page(request: Request):
    """Render the index page."""
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/video_page.html", response_class=HTMLResponse)
async def get_video_page(request: Request):
    """Render the video page."""
    return templates.TemplateResponse("video_page.html", {"request": request})

@app.get("/api/videolar")
async def get_videos():
    """Return the list of available videos."""
    try:
        return JSONResponse(content=VIDEO_LIST)
    except Exception as e:
        logger.error(f"Error retrieving videos: {e}")
        raise HTTPException(status_code=500, detail="Error retrieving videos")

@app.post("/api/asistana-sor")
async def ask_assistant(request: QuestionRequest):
    """Send a question to the RAG system and get an answer."""
    try:
        logger.info(f"Asking question to collection '{request.collection_name}': {request.question}")

        # Check for Google API key
        if not os.getenv("GOOGLE_API_KEY"):
            logger.error("GOOGLE_API_KEY environment variable not found")
            return {
                "answer": "Google API anahtarı bulunamadı. Lütfen sistem yöneticisiyle iletişime geçin.",
                "sources": []
            }

        try:
            # Check if collection exists, if not create it
            collection_path = Path("./rag_collections") / request.collection_name
            if not collection_path.exists():
                logger.info(f"Collection '{request.collection_name}' not found, creating it")
                result = ensure_collection_exists(request.collection_name)
                if result["status"] == "error":
                    return {
                        "answer": f"Bu eğitim için veritabanı oluşturulamadı: {result['message']}",
                        "sources": []
                    }
                elif result["status"] == "created":
                    logger.info(f"Successfully created collection: {result['message']}")
            
            # Use QueryManager with timeout
            def ask_with_timeout(collection_name: str, question: str, timeout_seconds: int = 30) -> Dict[str, Any]:
                """
                Run the query with a timeout.
                
                Args:
                    collection_name: Name of the RAG collection
                    question: User's question
                    timeout_seconds: Maximum time to wait for response
                    
                Returns:
                    Dict with result and source_documents
                """
                result = {"result": "", "source_documents": []}
                error = None
                
                def _ask_thread() -> None:
                    """Thread function to run the query with patched QueryManager."""
                    nonlocal result, error
                    try:
                        # Find the corresponding directory in Education_video (uses cached function)
                        original_dir_name = find_original_dir_name(collection_name)
                        videos_directory = Path("Education_video") / original_dir_name
                        
                        # Make sure the videos directory exists
                        videos_directory.mkdir(parents=True, exist_ok=True)
                        
                        # Create a patch for QueryManager to fix the videos_directory path issue
                        original_setup_paths = QueryManager._setup_paths
                        
                        # Define patched method
                        def patched_setup_paths(self, collection_name: str, base_persist_directory: str) -> None:
                            """Patched setup_paths to use the correct videos_directory."""
                            self.collection_path = Path(base_persist_directory) / collection_name
                            # Use the videos_directory we found instead of the default calculation
                            self.videos_directory = videos_directory
                            
                            if not self.collection_path.exists():
                                raise FileNotFoundError(f"Collection not found: {self.collection_path}")
                            # Skip videos_directory check as we've already handled it
                        
                        try:
                            # Apply the patch
                            QueryManager._setup_paths = patched_setup_paths
                            
                            # Initialize QueryManager with the correct paths
                            query_manager = QueryManager(
                                collection_name=collection_name,
                                base_persist_directory="./rag_collections"
                            )
                            result = query_manager.ask(question)
                        finally:
                            # Restore the original method (even if there was an error)
                            QueryManager._setup_paths = original_setup_paths
                        
                    except Exception as e:
                        logger.error(f"Error in query thread: {str(e)}")
                        error = e
                
                # Start thread with timeout
                thread = threading.Thread(target=_ask_thread)
                thread.daemon = True
                thread.start()
                thread.join(timeout_seconds)
                
                if thread.is_alive():
                    return {
                        "result": "Sorgunuz zaman aşımına uğradı. Lütfen daha basit bir soru deneyin veya daha sonra tekrar deneyin.",
                        "source_documents": []
                    }
                
                if error:
                    raise error
                    
                return result
            
            # Ask question with timeout using QueryManager
            start_time = time.time()
            result = ask_with_timeout(request.collection_name, request.question)
            elapsed_time = time.time() - start_time
            
            logger.info(f"Query answered in {elapsed_time:.2f} seconds")
            
            return {
                "answer": result["answer"],
                "sources": [
                    {
                        "content": doc.page_content,
                        "metadata": doc.metadata
                    } for doc in result["source_documents"][:3]  # Limit to first 3 sources
                ]
            }
        except ValueError as e:
            logger.error(f"ValueError: {e}")
            if "GOOGLE_API_KEY" in str(e):
                return {
                    "answer": "Google API anahtarı bulunamadı. Lütfen sistem yöneticisiyle iletişime geçin.",
                    "sources": []
                }
            else:
                return {
                    "answer": f"Yapılandırma hatası: {str(e)}",
                    "sources": []
                }
        except FileNotFoundError as e:
            logger.error(f"Collection not found: {e}")
            return {
                "answer": f"Bu eğitim koleksiyonu ('{request.collection_name}') için RAG veritabanı bulunamadı.",
                "sources": []
            }
        except Exception as e:
            logger.exception(f"Unexpected error: {e}")
            return {
                "answer": f"Beklenmeyen bir hata oluştu: {str(e)}. Lütfen tekrar deneyin.",
                "sources": []
            }
    except Exception as e:
        logger.exception(f"Error in ask_assistant endpoint: {e}")
        return {
            "answer": "Sorunuzu yanıtlarken bir hata oluştu. Lütfen daha sonra tekrar deneyin.",
            "sources": []
        }

@app.get("/api/collections")
async def list_collections():
    """List all available RAG collections."""
    try:
        base_dir = Path("./rag_collections")
        if not base_dir.exists():
            return {"collections": []}

        collections = [
            {
                "name": d.name,
                "path": str(d)
            }
            for d in base_dir.iterdir()
            if d.is_dir()
        ]

        return {"collections": collections}
    except Exception as e:
        logger.error(f"Error listing collections: {e}")
        raise HTTPException(status_code=500, detail=f"Error listing collections: {str(e)}")

@app.get("/api/check-collection/{collection_name}")
async def check_collection(collection_name: str):
    """Check if a collection exists and is ready for querying."""
    try:
        collection_path = Path("./rag_collections") / collection_name
        
        if collection_path.exists() and collection_path.is_dir():
            return {
                "status": "success",
                "exists": True,
                "path": str(collection_path)
            }
        else:
            return {
                "status": "success",
                "exists": False
            }
    except Exception as e:
        logger.error(f"Error checking collection: {e}")
        return {
            "status": "error",
            "message": str(e)
        }

@app.post("/api/ensure-collection")
async def ensure_collection(collection_name: str = Body(...)):
    """Ensure a collection exists, creating it if necessary."""
    try:
        result = ensure_collection_exists(collection_name)
        return result
    except Exception as e:
        logger.error(f"Error ensuring collection: {e}")
        return {
            "status": "error",
            "message": str(e)
        }

@app.get("/api/debug-env")
async def debug_env():
    """Debug endpoint to check environment variables."""
    try:
        google_api_key_set = bool(os.getenv("GOOGLE_API_KEY"))
        return {
            "google_api_key_set": google_api_key_set,
            "google_api_key_length": len(os.getenv("GOOGLE_API_KEY", "")) if google_api_key_set else 0,
            "api_key_masked": f"{os.getenv('GOOGLE_API_KEY', '')[:5]}...{os.getenv('GOOGLE_API_KEY', '')[-5:]}" if google_api_key_set and len(os.getenv("GOOGLE_API_KEY", "")) > 10 else "***"
        }
    except Exception as e:
        logger.error(f"Error in debug endpoint: {e}")
        return {"error": str(e)}

# Fallback for other static files
@app.get("/{path:path}")
async def catch_all(path: str):
    if os.path.exists(path):
        return FileResponse(path)
    
    if path.startswith("static/"):
        file_path = path
    else:
        file_path = f"static/{path}"
    
    if os.path.exists(file_path):
        return FileResponse(file_path)
    else:
        raise HTTPException(status_code=404, detail=f"File not found: {path}")

if __name__ == "__main__":
    import uvicorn
    
    logger.info(f"Starting SterkAgents with {len(VIDEO_LIST)} videos")
    
    uvicorn.run(
        "web_api_service:app",
        host="0.0.0.0",
        port=5001,
        reload=False,  # Disable reload for production
        log_level="info"
    )