"""
Dependency injection for FastAPI application.
Manages connections to external services and shared resources.
"""
import os
import logging
from typing import Optional, Dict, Any
from functools import lru_cache
from contextlib import asynccontextmanager

# Optional Pinecone import - handle colorama issues
PINECONE_AVAILABLE = False
pinecone = None
try:
    # Disable colorama to avoid console issues
    import os
    os.environ['NO_COLOR'] = '1'
    import pinecone
    PINECONE_AVAILABLE = True
except Exception as e:
    print(f"Pinecone import failed: {e}")
    PINECONE_AVAILABLE = False
    pinecone = None

from openai import OpenAI
from openai import AsyncOpenAI
from sentence_transformers import SentenceTransformer
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from dotenv import load_dotenv

# Load environment variables (commented out due to .env file issue)
# load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database
Base = declarative_base()


class DatabaseManager:
    """Manages PostgreSQL database connections."""
    
    def __init__(self):
        self.database_url = self._get_database_url()
        self.engine = create_engine(
            self.database_url,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            pool_recycle=300
        )
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine
        )
    
    def _get_database_url(self) -> str:
        """Construct database URL from environment variables."""
        host = os.getenv("POSTGRES_HOST", "localhost")
        port = os.getenv("POSTGRES_PORT", "5432")
        user = os.getenv("POSTGRES_USER", "demo_user")
        password = os.getenv("POSTGRES_PASSWORD", "demo_password")
        database = os.getenv("POSTGRES_DB", "demo_db")
        
        # Use mock database URL for demo
        if user == "demo_user" and password == "demo_password":
            logger.warning("Using mock database configuration")
            return "sqlite:///demo.db"
        
        if not all([user, password, database]):
            raise ValueError("Missing required PostgreSQL environment variables")
        
        return f"postgresql://{user}:{password}@{host}:{port}/{database}"
    
    def get_db(self) -> Session:
        """Get database session."""
        db = self.SessionLocal()
        try:
            return db
        except Exception as e:
            db.close()
            raise e
    
    def close_db(self, db: Session):
        """Close database session."""
        db.close()
    
    def test_connection(self) -> bool:
        """Test database connection."""
        try:
            db = self.get_db()
            from sqlalchemy import text
            db.execute(text("SELECT 1"))
            self.close_db(db)
            return True
        except Exception as e:
            logger.error(f"Database connection test failed: {e}")
            return False


class PineconeManager:
    """Manages Pinecone vector database connections."""
    
    def __init__(self):
        # Initialize index as None by default
        self.index = None
        
        if not PINECONE_AVAILABLE:
            logger.warning("Pinecone not available - running in mock mode")
            self.mock_mode = True
            return
            
        # Try to get from environment variables, fallback to hardcoded values
        self.api_key = os.getenv("PINECONE_API_KEY", "pcsk_3WBKR7_JMdkSFuxiUfNDp3vqz3heEM6heaS9tugp43bocDx5ztRfHQsCF76ST9fVRVFCLS")
        self.index_name = os.getenv("PINECONE_INDEX_NAME", "loopersbaja")
        self.environment = os.getenv("PINECONE_ENVIRONMENT", "us-east-1")
        
        # Check if using placeholder values
        if any(key in ["your_pinecone_api_key_here", "your_pinecone_index_name_here", "your_pinecone_environment_here"] 
               for key in [self.api_key, self.index_name, self.environment]):
            logger.warning("Using placeholder Pinecone values - running in mock mode")
            logger.info("To enable Pinecone, update the values in dependencies.py")
            self.mock_mode = True
            return
        
        self.mock_mode = False
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize Pinecone client and index."""
        try:
            # Set API key as environment variable and use Index directly
            import os
            os.environ['PINECONE_API_KEY'] = self.api_key
            import pinecone
            self.index = pinecone.Index(self.index_name)
            logger.info("Pinecone client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Pinecone: {e}")
            self.mock_mode = True
            self.index = None
    
    async def search_similar(
        self, 
        embedding: list, 
        top_k: int = 5,
        filter_dict: Optional[Dict[str, Any]] = None
    ) -> list:
        """Search for similar vectors in Pinecone."""
        if self.mock_mode:
            logger.warning("Pinecone not available - returning mock results")
            return []
            
        try:
            search_params = {
                "vector": embedding,
                "top_k": top_k,
                "include_metadata": True,
                "include_values": False
            }
            
            if filter_dict:
                search_params["filter"] = filter_dict
            
            results = self.index.query(**search_params)
            return results.matches
        except Exception as e:
            logger.error(f"Pinecone search failed: {e}")
            return []
    
    def test_connection(self) -> bool:
        """Test Pinecone connection."""
        if self.mock_mode:
            return False
            
        try:
            stats = self.index.describe_index_stats()
            logger.info(f"Pinecone connection test passed. Index stats: {stats}")
            return True
        except Exception as e:
            logger.error(f"Pinecone connection test failed: {e}")
            return False


class OpenAIManager:
    """Manages OpenAI API connections and requests."""
    
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY", "your_openai_api_key_here")
        self.mock_mode = self.api_key in ["sk-demo-key", "your_openai_api_key_here"]
        
        if not self.mock_mode:
            self.client = AsyncOpenAI(api_key=self.api_key)
            self.sync_client = OpenAI(api_key=self.api_key)
        else:
            logger.warning("Using mock OpenAI configuration")
            logger.info("To enable OpenAI, update the API key in dependencies.py")
            self.client = None
            self.sync_client = None
            
        self.model = os.getenv("OPENAI_MODEL", "gpt-4")
        self.max_tokens = int(os.getenv("OPENAI_MAX_TOKENS", "1500"))
        self.temperature = float(os.getenv("OPENAI_TEMPERATURE", "0.1"))
    
    async def generate_response(self, prompt: str) -> str:
        """Generate response using OpenAI API."""
        if self.mock_mode:
            logger.warning("OpenAI not available - returning mock response")
            return "This is a mock response from the AI assistant. Please configure OpenAI API for full functionality."
            
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an AI assistant designed to analyze legal and policy documents with high accuracy and provide clear, well-reasoned answers."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                top_p=0.9,
                frequency_penalty=0.0,
                presence_penalty=0.0
            )
            
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"OpenAI API call failed: {e}")
            raise e
    
    def test_connection(self) -> bool:
        """Test OpenAI API connection."""
        if self.mock_mode:
            return False
            
        try:
            # Simple test with minimal tokens
            response = self.sync_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": "Test"}],
                max_tokens=1
            )
            return True
        except Exception as e:
            logger.error(f"OpenAI connection test failed: {e}")
            return False


class EmbeddingManager:
    """Manages sentence transformer model for generating embeddings."""
    
    def __init__(self):
        self.model_name = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
        self._load_model()
    
    def _load_model(self):
        """Load the sentence transformer model."""
        try:
            self.model = SentenceTransformer(self.model_name)
            logger.info(f"Embedding model '{self.model_name}' loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            raise e
    
    def encode(self, text: str) -> list:
        """Generate embedding for input text."""
        try:
            embedding = self.model.encode(text, convert_to_tensor=False)
            return embedding.tolist()
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            raise e
    
    def encode_batch(self, texts: list) -> list:
        """Generate embeddings for multiple texts."""
        try:
            embeddings = self.model.encode(texts, convert_to_tensor=False)
            return [emb.tolist() for emb in embeddings]
        except Exception as e:
            logger.error(f"Failed to generate batch embeddings: {e}")
            raise e


# Global instances (singletons)
_database_manager: Optional[DatabaseManager] = None
_pinecone_manager: Optional[PineconeManager] = None
_openai_manager: Optional[OpenAIManager] = None
_embedding_manager: Optional[EmbeddingManager] = None


@lru_cache()
def get_database_manager() -> DatabaseManager:
    """Get database manager instance."""
    global _database_manager
    if _database_manager is None:
        _database_manager = DatabaseManager()
    return _database_manager


@lru_cache()
def get_pinecone_manager() -> PineconeManager:
    """Get Pinecone manager instance."""
    global _pinecone_manager
    if _pinecone_manager is None:
        _pinecone_manager = PineconeManager()
    return _pinecone_manager


@lru_cache()
def get_openai_manager() -> OpenAIManager:
    """Get OpenAI manager instance."""
    global _openai_manager
    if _openai_manager is None:
        _openai_manager = OpenAIManager()
    return _openai_manager


@lru_cache()
def get_embedding_manager() -> EmbeddingManager:
    """Get embedding manager instance."""
    global _embedding_manager
    if _embedding_manager is None:
        _embedding_manager = EmbeddingManager()
    return _embedding_manager


def get_db_session():
    """FastAPI dependency for database sessions."""
    db_manager = get_database_manager()
    db = db_manager.get_db()
    try:
        yield db
    finally:
        db_manager.close_db(db)


async def check_service_health() -> Dict[str, str]:
    """Check health of all external services."""
    health_status = {}
    
    # Check database
    try:
        db_manager = get_database_manager()
        health_status["database"] = "healthy" if db_manager.test_connection() else "unhealthy"
    except Exception:
        health_status["database"] = "unhealthy"
    
    # Check Pinecone
    try:
        pinecone_manager = get_pinecone_manager()
        if pinecone_manager.mock_mode:
            health_status["pinecone"] = "mock_mode"
        else:
            health_status["pinecone"] = "healthy" if pinecone_manager.test_connection() else "unhealthy"
    except Exception:
        health_status["pinecone"] = "unhealthy"
    
    # Check OpenAI
    try:
        openai_manager = get_openai_manager()
        if openai_manager.mock_mode:
            health_status["openai"] = "mock_mode"
        else:
            health_status["openai"] = "healthy" if openai_manager.test_connection() else "unhealthy"
    except Exception:
        health_status["openai"] = "unhealthy"
    
    # Check embedding model (always healthy if loaded)
    try:
        get_embedding_manager()
        health_status["embedding_model"] = "healthy"
    except Exception:
        health_status["embedding_model"] = "unhealthy"
    
    return health_status
