import os
import asyncio
from dotenv import load_dotenv
import chromadb
from langchain_nvidia_ai_endpoints import NVIDIAEmbeddings

load_dotenv()


class KnowledgeBase:
    """RAG knowledge base using ChromaDB and NVIDIA embeddings."""

    def __init__(self) -> None:
        self.client = chromadb.PersistentClient(path="./chroma_db")
        self.collection = self.client.get_or_create_collection(name="ioai_knowledge")
        self.embeddings = NVIDIAEmbeddings()

    async def ingest_text(self, text: str, doc_id: str, metadata: dict | None = None) -> None:
        """Ingest a text document into the knowledge base."""
        try:
            embedding = await asyncio.to_thread(
                self.embeddings.embed_query, text
            )
            await asyncio.to_thread(
                self.collection.upsert,
                ids=[doc_id],
                embeddings=[embedding],
                documents=[text],
                metadatas=[metadata or {}],
            )
        except Exception as e:
            raise RuntimeError(f"Failed to ingest text: {e}") from e

    async def retrieve_context(self, query: str, n_results: int = 3) -> str:
        """Retrieve relevant context for a given query."""
        try:
            query_embedding = await asyncio.to_thread(
                self.embeddings.embed_query, query
            )
            results = await asyncio.to_thread(
                self.collection.query,
                query_embeddings=[query_embedding],
                n_results=n_results,
            )
            documents = results.get("documents", [[]])[0]
            return "\n\n".join(documents) if documents else ""
        except Exception as e:
            raise RuntimeError(f"Failed to retrieve context: {e}") from e


rag_db = KnowledgeBase()
