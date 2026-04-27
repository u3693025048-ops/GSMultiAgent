#!/usr/bin/env python3
"""
RAG Knowledge Base
基于 ChromaDB 的向量知识库，支持可配置的 Embedding 模型
"""

import logging
import os
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class EmbeddingConfig:
    """Embedding 模型配置"""

    provider: str = "local"  # "local", "openai", "anthropic"
    model: str = "sentence-transformers/all-MiniLM-L6-v2"  # 本地模型
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    dimension: int = 384


@dataclass
class RAGConfig:
    """RAG 知识库配置"""

    persist_directory: str = "./chroma_db"
    collection_name: str = "knowledge_base"
    embedding_config: EmbeddingConfig = field(default_factory=EmbeddingConfig)


class RAGKnowledgeBase:
    """
    基于 ChromaDB 的 RAG 知识库

    支持多种 Embedding 模型：
    - local: 使用 sentence-transformers 本地模型
    - openai: 使用 OpenAI Embedding API
    - anthropic: 使用 Anthropic Embedding API
    """

    def __init__(
        self,
        config: Optional[RAGConfig] = None,
        embedding_config: Optional[EmbeddingConfig] = None,
    ):
        from ..config_loader import get_config

        app_cfg = get_config()
        rag_cfg = app_cfg.rag
        llm_cfg = app_cfg.llm

        if config is None:
            config = RAGConfig(
                persist_directory=rag_cfg.persist_dir,
                collection_name=rag_cfg.collection,
            )

        if embedding_config is None:
            # 优先从 RAG 配置中取，如果 provider 没有指定 api_key/base_url，则 fallback 到全局大模型的 API_KEY/BASE_URL
            embedding_config = EmbeddingConfig(
                provider=rag_cfg.embedding_provider,
                model=rag_cfg.embedding_model,
                api_key=rag_cfg.embedding_api_key or llm_cfg.api_key, 
                base_url=rag_cfg.embedding_base_url or llm_cfg.base_url,
                dimension=rag_cfg.embedding_dim,
            )

        self.config = config
        self.embedding_config = embedding_config
        self._client = None
        self._collection = None
        self._embedding_function = None

    async def initialize(self) -> bool:
        """初始化 ChromaDB 和 Embedding 模型"""
        try:
            import chromadb
            from chromadb.config import Settings

            self._client = chromadb.PersistentClient(
                path=self.config.persist_directory, settings=Settings(anonymized_telemetry=False)
            )

            self._embedding_function = self._create_embedding_function()

            self._collection = self._client.get_or_create_collection(
                name=self.config.collection_name,
                embedding_function=self._embedding_function,
                metadata={"description": "RAG Knowledge Base"},
            )

            logger.info(
                f"Initialized RAG with {self.embedding_config.provider}/{self.embedding_config.model}"
            )
            return True

        except ImportError:
            logger.error("ChromaDB not installed. Run: pip install chromadb sentence-transformers")
            return False
        except Exception as e:
            logger.error(f"Failed to initialize RAG: {e}")
            return False

    def _create_embedding_function(self):
        """创建 Embedding 函数"""
        if self.embedding_config.provider == "local":
            return self._create_local_embedding_function()
        elif self.embedding_config.provider == "openai":
            return self._create_openai_embedding_function()
        elif self.embedding_config.provider == "anthropic":
            return self._create_anthropic_embedding_function()
        elif self.embedding_config.provider == "custom":
            return self._create_custom_embedding_function()
        else:
            return self._create_local_embedding_function()

    def _create_local_embedding_function(self):
        """创建本地 Embedding 函数"""
        try:
            from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

            return SentenceTransformerEmbeddingFunction(model_name=self.embedding_config.model)
        except ImportError:
            logger.warning("sentence-transformers not installed, using default")
            return None

    def _create_openai_embedding_function(self):
        """创建 OpenAI Embedding 函数"""
        try:
            from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

            return OpenAIEmbeddingFunction(
                api_key=self.embedding_config.api_key or os.getenv("OPENAI_API_KEY"),
                model_name=self.embedding_config.model or "text-embedding-3-small",
            )
        except ImportError:
            logger.error("OpenAI embedding not available")
            return None

    def _create_custom_embedding_function(self):
        """创建自定义 OpenAI-Like Embedding 函数"""
        try:
            from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

            base_url = self.embedding_config.base_url or os.getenv("EMBEDDING_BASE_URL")
            if not base_url:
                logger.warning("Custom embedding provider requires EMBEDDING_BASE_URL, falling back to local")
                return self._create_local_embedding_function()

            # For chromadb OpenAIEmbeddingFunction, we might need to set openai.api_base directly 
            # or pass api_base instead of base_url depending on chromadb version.
            # Usually, chromadb uses `api_base` or `api_base` parameter in OpenAIEmbeddingFunction.
            return OpenAIEmbeddingFunction(
                api_key=self.embedding_config.api_key,
                model_name=self.embedding_config.model or "text-embedding-3-small",
                api_base=base_url,
            )
        except ImportError:
            logger.error("OpenAI embedding function not available")
            return None

    def _create_anthropic_embedding_function(self):
        """创建 Anthropic Embedding 函数"""
        logger.warning("Anthropic does not provide standalone embedding API, falling back to local")
        return self._create_local_embedding_function()

    async def index_documents(
        self,
        documents: List[Dict[str, Any]],
        metadata: Dict[str, Any] = None,
    ) -> int:
        """索引文档到 ChromaDB"""
        if self._collection is None:
            await self.initialize()

        if self._collection is None:
            return 0

        try:
            ids = []
            contents = []
            metas = []

            for i, doc_data in enumerate(documents):
                content = doc_data.get("content", "")
                doc_metadata = {**(metadata or {}), **doc_data.get("metadata", {})}

                doc_id = doc_data.get("id") or f"doc_{i}_{hash(content) % 100000}"

                ids.append(doc_id)
                contents.append(content)
                metas.append(doc_metadata)

            self._collection.add(
                ids=ids,
                documents=contents,
                metadatas=metas,
            )

            logger.info(f"Indexed {len(documents)} documents")
            return len(documents)

        except Exception as e:
            logger.error(f"Failed to index documents: {e}")
            return 0

    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        filters: Dict[str, Any] = None,
    ) -> List[Dict[str, Any]]:
        """检索相关文档"""
        if self._collection is None:
            await self.initialize()

        if self._collection is None:
            return []

        try:
            where_filter = None
            if filters:
                where_filter = filters

            results = self._collection.query(
                query_texts=[query],
                n_results=top_k,
                where=where_filter,
            )

            retrieved = []
            if results and results.get("documents"):
                for i, doc in enumerate(results["documents"][0]):
                    metadata = results["metadatas"][0][i] if results.get("metadatas") else {}
                    distance = results["distances"][0][i] if results.get("distances") else 0.0

                    retrieved.append(
                        {
                            "doc_id": results["ids"][0][i],
                            "content": doc,
                            "score": 1.0 - distance if distance else 0.0,
                            "metadata": metadata,
                        }
                    )

            return retrieved

        except Exception as e:
            logger.error(f"Failed to retrieve documents: {e}")
            return []

    async def similarity_search(
        self,
        query: str,
        threshold: float = 0.7,
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        """相似性搜索"""
        results = await self.retrieve(query, top_k=top_k * 2)
        filtered = [r for r in results if r["score"] >= threshold]
        return filtered[:top_k]

    async def get_document(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """获取指定文档"""
        if self._collection is None:
            return None

        try:
            result = self._collection.get(ids=[doc_id])
            if result and result.get("documents"):
                return {
                    "doc_id": doc_id,
                    "content": result["documents"][0],
                    "metadata": result["metadatas"][0] if result.get("metadatas") else {},
                }
            return None
        except Exception as e:
            logger.error(f"Failed to get document: {e}")
            return None

    async def delete_document(self, doc_id: str) -> bool:
        """删除文档"""
        if self._collection is None:
            return False

        try:
            self._collection.delete(ids=[doc_id])
            return True
        except Exception as e:
            logger.error(f"Failed to delete document: {e}")
            return False

    async def update_document(
        self,
        doc_id: str,
        content: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """更新文档"""
        if self._collection is None:
            return False

        try:
            update_data = {"id": doc_id}
            if content is not None:
                update_data["documents"] = [content]
            if metadata is not None:
                update_data["metadatas"] = [metadata]

            self._collection.update(**update_data)
            return True
        except Exception as e:
            logger.error(f"Failed to update document: {e}")
            return False

    async def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        if self._collection is None:
            return {"total_documents": 0}

        try:
            count = self._collection.count()
            return {
                "total_documents": count,
                "collection_name": self.config.collection_name,
                "persist_directory": self.config.persist_directory,
                "embedding_provider": self.embedding_config.provider,
                "embedding_model": self.embedding_config.model,
                "embedding_dimension": self.embedding_config.dimension,
            }
        except Exception as e:
            logger.error(f"Failed to get statistics: {e}")
            return {"error": str(e)}

    async def clear(self) -> bool:
        """清空知识库"""
        if self._collection is None:
            return False

        try:
            self._client.delete_collection(self.config.collection_name)
            self._collection = self._client.get_or_create_collection(
                name=self.config.collection_name,
                embedding_function=self._embedding_function,
            )
            return True
        except Exception as e:
            logger.error(f"Failed to clear collection: {e}")
            return False

    def close(self):
        """关闭连接"""
        if self._client:
            self._client = None
            self._collection = None
