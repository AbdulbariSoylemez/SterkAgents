#!/usr/bin/env python3
"""
Test script to check vector store functionality
"""

import os
import logging
from pathlib import Path
from query_manager import QueryManager, get_collection_dir

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_vector_store():
    """Test vector store functionality"""
    try:
        # Test collection path
        collection_name = "gerçeğin_sınırı"
        collection_path = get_collection_dir(collection_name)
        logger.info(f"Collection path: {collection_path}")
        
        # Test QueryManager initialization
        query_manager = QueryManager(collection_name=collection_name)
        logger.info(f"QueryManager initialized successfully")
        logger.info(f"Collection path: {query_manager.collection_path}")
        logger.info(f"Videos directory: {query_manager.videos_directory}")
        
        # Test vector store collection count
        try:
            collection_count = query_manager.vector_store._collection.count()
            logger.info(f"Vector store collection count: {collection_count}")
            
            if collection_count == 0:
                logger.error("Vector store is empty!")
                return False
                
        except Exception as e:
            logger.error(f"Error getting collection count: {e}")
            return False
        
        # Test simple query
        test_question = "Bu eğitimin konusu nedir?"
        logger.info(f"Testing query: {test_question}")
        
        result = query_manager.ask(test_question)
        logger.info(f"Query result: {result}")
        
        return True
        
    except Exception as e:
        logger.error(f"Error in test: {e}")
        return False

if __name__ == "__main__":
    success = test_vector_store()
    if success:
        print("✅ Vector store test passed!")
    else:
        print("❌ Vector store test failed!") 