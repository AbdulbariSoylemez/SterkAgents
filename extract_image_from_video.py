import os
import logging
from typing import Optional
from pathlib import Path

import cv2
from PIL import Image

logger = logging.getLogger(__name__)


def get_frame_from_video(video_path: str, timestamp_ms: int) -> Optional[Image.Image]:
    """
    Extract frame from video at specified timestamp.
    
    Args:
        video_path: Full path to video file
        timestamp_ms: Timestamp in milliseconds
        
    Returns:
        PIL Image object if successful, None otherwise
    """
    video_file = Path(video_path)
    
    if not video_file.exists():
        logger.error(f"Video file not found: {video_path}")
        return None

    cap = cv2.VideoCapture(video_path)
    
    if not cap.isOpened():
        logger.error(f"Cannot open video file: {video_path}")
        return None

    try:
        cap.set(cv2.CAP_PROP_POS_MSEC, timestamp_ms)
        ret, frame = cap.read()
        
        if not ret:
            logger.warning(f"Cannot extract frame at {timestamp_ms}ms from '{video_file.name}'")
            return None
            
        logger.info(f"Successfully extracted frame at {timestamp_ms}ms from '{video_file.name}'")
        
        # Convert BGR to RGB for PIL/Gemini compatibility
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        return Image.fromarray(frame_rgb)
        
    except Exception as e:
        logger.exception(f"Error extracting frame from video: {e}")
        return None
        
    finally:
        cap.release()