import os
import logging
import re
import uuid
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
import time
import threading
import dotenv
from slugify import slugify
from functools import lru_cache
from moviepy.editor import VideoFileClip

from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

dotenv.load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    encoding='utf-8'
)
logger = logging.getLogger(__name__)

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

if not os.getenv("GOOGLE_API_KEY"):
    logger.warning("GOOGLE_API_KEY not found in environment variables. Using fallback method...")
    env_path = Path(".env")
    if env_path.exists():
        with open(env_path, "r") as f:
            for line in f:
                if line.strip().startswith("GOOGLE_API_KEY="):
                    key = line.strip().split("=", 1)[1].strip().strip('"').strip("'")
                    os.environ["GOOGLE_API_KEY"] = key
                    logger.info("GOOGLE_API_KEY loaded from .env file")
                    break

if os.getenv("GOOGLE_API_KEY"):
    api_key = os.getenv("GOOGLE_API_KEY")
    masked_key = f"{api_key[:5]}...{api_key[-5:]}" if len(api_key) > 10 else "***"
    logger.info(f"GOOGLE_API_KEY is set (masked: {masked_key})")
else:
    logger.error("GOOGLE_API_KEY is still not set! Application may not work correctly.")

app = FastAPI(
    title="SterkAgents Web Service",
    description="Web service for SterkAgents RAG video education platform",
    version="1.0.0"
)

@lru_cache(maxsize=200)
def get_video_duration(video_path: str) -> Tuple[int, str]:
    try:
        if not Path(video_path).exists():
            logger.warning(f"Video file not found for duration calculation: {video_path}")
            return 0, "N/A"
        
        with VideoFileClip(video_path) as video:
            duration_seconds = int(video.duration)
        
        minutes = duration_seconds // 60
        seconds = duration_seconds % 60
        formatted_duration = f"{minutes}d {seconds}sn"
        
        return duration_seconds, formatted_duration
    except Exception as e:
        logger.error(f"Error getting video duration for {video_path}: {e}")
        return 0, "N/A"

def extract_leading_number(filename: str) -> int:
    match = re.match(r'^\s*(\d+)', filename)
    if match:
        return int(match.group(1))
    return float('inf')

def create_video_list() -> List[Dict[str, Any]]:
    videos = []
    root_dir = Path("Education_video")

    if not root_dir.exists():
        logger.warning("Education_video directory not found")
        return videos

    for course_dir in sorted(root_dir.iterdir()):
        if not course_dir.is_dir():
            continue

        course_name = course_dir.name
        course_id = f"course_{slugify(course_name)}"
        collection_name = course_name.lower().replace(" ", "_")

        video_files = sorted(
            [p for p in course_dir.glob("**/*.mp4") if p.is_file()],
            key=lambda x: extract_leading_number(x.name)
        )
        
        is_series = len(video_files) > 1
        thumbnail_files = list(course_dir.glob("**/*.jpg")) + list(course_dir.glob("**/*.png"))
        thumbnail = f"/Education_video/{course_name}/{thumbnail_files[0].name}" if thumbnail_files and len(thumbnail_files) > 0 else None

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
            video_path_url = f"/Education_video/{course_name}/{main_video.name}"
            course_info["video_url"] = video_path_url
            if thumbnail:
                course_info["thumbnail"] = thumbnail

            series_videos = []
            total_duration_seconds = 0
            
            for idx, video_file in enumerate(video_files):
                video_name = video_file.stem
                video_path = f"/Education_video/{course_name}/{video_file.name}"
                full_path = str(video_file.resolve())
                
                duration_seconds, duration = get_video_duration(full_path)
                total_duration_seconds += duration_seconds
                
                series_videos.append({
                    "title": video_name,
                    "video_path": video_path,
                    "collection_name": collection_name,
                    "original_dir_name": course_name,
                    "index": idx,
                    "duration": duration
                })
            
            total_minutes = total_duration_seconds // 60
            total_seconds = total_duration_seconds % 60
            total_duration = f"{total_minutes}d {total_seconds}sn"
            course_info["total_duration"] = total_duration
            course_info["series_videos_data"] = series_videos
            course_info["video_count"] = len(video_files)

            videos.append(course_info)
            logger.info(f"Added course '{course_name}' with {len(video_files)} videos")

    return videos

from query_manager import QueryManager, is_valid_collection, find_latest_collection_uuid, get_collection_dir

def ensure_collection_exists(collection_name: str) -> Dict[str, Any]:
    """
    Check if a collection exists, and if not, create it.
    """
    try:
        collection_path = get_collection_dir(collection_name)
        
        logger.info(f"Checking if collection exists at: {collection_path}")
        logger.info(f"Collection path exists: {collection_path.exists()}")
        logger.info(f"Collection is valid: {is_valid_collection(collection_path)}")
        
        if is_valid_collection(collection_path):
            latest_uuid = find_latest_collection_uuid(collection_path)
            logger.info(f"Collection '{collection_name}' already exists with UUID: {latest_uuid}")
            return {
                "status": "exists",
                "message": f"Collection '{collection_name}' already exists",
                "collection_path": str(collection_path / latest_uuid) if latest_uuid else str(collection_path),
                "collection_uuid": latest_uuid
            }
        
        original_dir_name = find_original_dir_name(collection_name)
        course_dir = Path("Education_video") / original_dir_name
        
        if not course_dir.exists() or not course_dir.is_dir():
            logger.error(f"Could not find matching directory for collection '{collection_name}'")
            return {
                "status": "error",
                "message": f"Could not find matching directory for collection '{collection_name}'",
                "collection_path": None
            }
        
        from app import VideoProcessingService
        from create_vector_store import RAGVectorStoreManager
        
        logger.info(f"Processing course directory for collection '{collection_name}': {course_dir}")
        start_time = time.time()
        
        collection_uuid = str(uuid.uuid4())
        collection_uuid_path = collection_path / collection_uuid
        
        if not collection_path.exists():
            collection_path.mkdir(parents=True, exist_ok=True)
        
        processing_result = VideoProcessingService.process_directory(str(course_dir))
        chunks = processing_result.get("chunks", [])
        
        logger.info(f"Processing result: {processing_result}")
        logger.info(f"Number of chunks generated: {len(chunks)}")
        
        if not chunks:
            logger.error(f"No chunks generated for course '{collection_name}'")
            return {
                "status": "error",
                "message": f"No chunks generated for course '{collection_name}'",
                "collection_path": None
            }
        
        # Debug: Check first few chunks
        if chunks:
            logger.info(f"First chunk sample: {chunks[0]}")
            logger.info(f"Number of chunks with text: {len([c for c in chunks if c.get('text', '').strip()])}")
        
        collection_uuid_path.mkdir(parents=True, exist_ok=True)
        
        rag_manager = RAGVectorStoreManager(persist_directory=str(collection_uuid_path))
        rag_manager.create_and_persist_store(chunks)
        
        elapsed_time = time.time() - start_time
        chunks_count = len(chunks)
        logger.info(f"Course collection '{collection_name}/{collection_uuid}' created in {elapsed_time:.2f} seconds with {chunks_count} chunks")
        
        return {
            "status": "created",
            "message": f"Collection '{collection_name}' created successfully with UUID: {collection_uuid}",
            "collection_path": str(collection_uuid_path),
            "collection_uuid": collection_uuid,
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
    for video in VIDEO_LIST:
        if video.get("collection_name") == collection_name:
            return video.get("original_dir_name", collection_name)
    
    education_dir = Path("Education_video")
    if education_dir.exists():
        for dir_path in education_dir.iterdir():
            if dir_path.is_dir() and dir_path.name.lower().replace(" ", "_") == collection_name:
                return dir_path.name
    
    return collection_name



app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/Education_video", StaticFiles(directory="Education_video"), name="education_video")
templates = Jinja2Templates(directory="templates")

class QuestionRequest(BaseModel):
    collection_name: str
    question: str

VIDEO_LIST = create_video_list()

@app.get("/", response_class=HTMLResponse)
async def get_index_page(request: Request):
    response = templates.TemplateResponse("index.html", {"request": request})
    response.headers["Cache-Control"] = "public, max-age=3600"
    return response

@app.get("/video_page.html", response_class=HTMLResponse)
async def get_video_page(request: Request):
    video_id = request.query_params.get("id")
    logger.info(f"Video page requested with id: {video_id}")
    response = templates.TemplateResponse("video_page.html", {"request": request})
    response.headers["Cache-Control"] = "public, max-age=1800"
    return response

@app.get("/api/videolar")
async def get_videos():
    if not VIDEO_LIST:
        logger.error("Video list could not be generated at startup.")
        return JSONResponse(content=[])
    
    response = JSONResponse(content=VIDEO_LIST)
    response.headers["Cache-Control"] = "public, max-age=600"
    return response

@app.post("/api/asistana-sor")
async def ask_assistant(request: QuestionRequest, background_tasks: BackgroundTasks):
    try:
        logger.info(f"Asking question to collection '{request.collection_name}': {request.question}")

        if not os.getenv("GOOGLE_API_KEY"):
            return JSONResponse(status_code=400, content={"answer": "Google API anahtarı bulunamadı.", "sources": []})

        collection_path = get_collection_dir(request.collection_name)
        
        if not is_valid_collection(collection_path):
            logger.info(f"Collection '{request.collection_name}' not found or invalid, starting background creation")
            # Önce koleksiyon oluşturma işlemini başlat
            result = ensure_collection_exists(request.collection_name)
            
            # Eğer koleksiyon zaten varsa (başka bir isimle), hemen yanıt ver
            if result["status"] == "exists":
                logger.info(f"Collection found with different name, using existing collection")
                query_manager = QueryManager(collection_name=request.collection_name)
                result = query_manager.ask(request.question)
                return JSONResponse(content={
                    "answer": result.get("answer", ""),
                    "sources": result.get("source_documents", [])
                })
            
            # Koleksiyon yoksa arka planda oluştur
            background_tasks.add_task(ensure_collection_exists, request.collection_name)
            return JSONResponse(content={
                "answer": "Bu eğitim için veritabanı hazırlanıyor. Bu işlem birkaç dakika sürebilir. Lütfen biraz bekledikten sonra tekrar sorunuzu sorun.",
                "sources": [],
                "status": "processing"
            })

        try:
            query_manager = QueryManager(collection_name=request.collection_name)
            
            result = None
            result_thread = threading.Thread(target=lambda: setattr(threading.current_thread(), "result", query_manager.ask(request.question)))
            result_thread.daemon = True
            result_thread.start()
            result_thread.join(timeout=30)
            
            if result_thread.is_alive():
                return JSONResponse(content={
                    "answer": "Yanıt oluşturulurken zaman aşımı oluştu. Lütfen daha kısa bir soru sorun veya daha sonra tekrar deneyin.",
                    "sources": []
                })
            
            if hasattr(result_thread, "result"):
                result = result_thread.result
            else:
                result = query_manager.ask(request.question)

            # Convert Document objects to serializable format
            source_documents = []
            for doc in result.get("source_documents", []):
                source_documents.append({
                    "page_content": doc.page_content,
                    "metadata": doc.metadata
                })
            
            return JSONResponse(content={
                "answer": result.get("answer", ""),
                "sources": source_documents
            })
            
        except Exception as query_error:
            logger.exception(f"Error querying collection: {query_error}")
            return JSONResponse(content={
                "answer": f"Sorgunuz işlenirken bir hata oluştu: {str(query_error)}",
                "sources": []
            })
            
    except Exception as e:
        logger.exception(f"Error in ask_assistant endpoint: {e}")
        return JSONResponse(status_code=500, content={"answer": "Beklenmeyen bir hata oluştu.", "sources": []})

@app.get("/api/check-collection/{collection_name}")
async def check_collection(collection_name: str):
    collection_path = get_collection_dir(collection_name)
    exists = is_valid_collection(collection_path)
    
    response_data = {"exists": exists}
    
    if exists:
        latest_uuid = find_latest_collection_uuid(collection_path)
        if latest_uuid:
            response_data["uuid"] = latest_uuid
    
    return JSONResponse(content=response_data)

@app.post("/api/ensure-collection")
async def ensure_collection_endpoint(request: Request, background_tasks: BackgroundTasks):
    body = await request.json()
    collection_name = body.get("collection_name")
    if not collection_name:
        raise HTTPException(status_code=400, detail="collection_name is required")
    
    collection_path = get_collection_dir(collection_name)
    if is_valid_collection(collection_path):
        latest_uuid = find_latest_collection_uuid(collection_path)
        return JSONResponse(content={
            "status": "exists",
            "message": f"Collection '{collection_name}' already exists",
            "collection_path": str(collection_path / latest_uuid) if latest_uuid else str(collection_path),
            "collection_uuid": latest_uuid
        })
    
    background_tasks.add_task(ensure_collection_exists, collection_name)
    
    return JSONResponse(content={
        "status": "processing",
        "message": f"Collection '{collection_name}' creation started in background",
        "collection_path": None
    })

if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting SterkAgents with {len(VIDEO_LIST)} videos")
    uvicorn.run("web_api_service:app", host="0.0.0.0", port=5001, reload=True)
