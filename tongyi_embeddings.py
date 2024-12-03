from typing import Generator, List
import dashscope
from http import HTTPStatus

import logging
import warnings
from typing import (
    Any,
    Dict,
    Iterable,
    List,
    Literal,
    Mapping,
    Optional,
    Sequence,
    Set,
    Tuple,
    Union,
    cast,
)

import openai
import tiktoken
from langchain_core.embeddings import Embeddings
from langchain_core.utils import from_env, get_pydantic_field_names, secret_from_env
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator
from typing_extensions import Self

DASHSCOPE_MAX_BATCH_SIZE = 25  # 根据示例中的最大批次大小

class AliyunEmbeddings(BaseModel, Embeddings):
    """阿里云嵌入模型集成。"""

    client: Any = Field(default=None, exclude=True)
    model: str = "text-embedding-v2"
    api_key: Optional[str] = Field(alias="api_key")
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    chunk_size: int = 1000

    def batched(self, inputs: List, batch_size: int = DASHSCOPE_MAX_BATCH_SIZE) -> Generator[List, None, None]:
        for i in range(0, len(inputs), batch_size):
            yield inputs[i:i + batch_size]

    def embed_documents(self, texts: List[str], chunk_size: int | None = None) -> List[List[float]]:
        """调用阿里云的嵌入API来生成文本嵌入。"""

        chunk_size_ = chunk_size or self.chunk_size

        embeddings: List[List[float]] = []

        # 分批处理文本
        for batch in self.batched(texts, batch_size=DASHSCOPE_MAX_BATCH_SIZE):
            resp = dashscope.TextEmbedding.call(
                model=dashscope.TextEmbedding.Models.text_embedding_v1,
                input=batch
            )
            if resp.status_code == HTTPStatus.OK:
                for emb in resp.output['embeddings']:
                    embeddings.append(emb['embedding'])  # 根据实际响应结构调整
            else:
                print(f"嵌入创建失败: {resp}")
                raise Exception(f"嵌入创建失败: {resp}")
        
        return embeddings

    def embed_query(self, text: str) -> List[float]:
        """嵌入单个查询文本。"""
        return self.embed_documents([text])[0]
