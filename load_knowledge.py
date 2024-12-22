from langchain_chroma import Chroma
from tongyi_embeddings import AliyunEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import (
    DirectoryLoader,
    TextLoader,
    PyPDFLoader,
    UnstructuredMarkdownLoader
)
import os
import numpy as np
from chromadb.config import Settings

def load_knowledge_base():
    try:
        # 初始化embeddings
        embeddings = AliyunEmbeddings(
            api_key="sk-5af05cf94fbe4be8b1c6c55bf3d0a8fe",
            model="text-embedding-v2",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        
        # 初始化向量存储，添加客户端设置
        vector_store = Chroma(
            persist_directory="./knowledge_base",
            embedding_function=embeddings,
            client_settings=Settings(
                anonymized_telemetry=False,
                is_persistent=True
            )
        )
        
        # 如果向量存储已存在，先清空
        try:
            vector_store.delete_collection()
            vector_store = Chroma(
                persist_directory="./knowledge_base",
                embedding_function=embeddings,
                client_settings=Settings(
                    anonymized_telemetry=False,
                    is_persistent=True
                )
            )
            print("已清空现有向量存储")
        except Exception as e:
            print(f"清空向量存储时出错（如果是首次运行可以忽略）: {e}")
        
        # 检查目录是否存在
        base_dirs = {
            "txt": "./knowledge/txt",
            "pdf": "./knowledge/pdf",
            "md": "./knowledge/md"
        }
        
        # 确保目录存在
        for dir_type, dir_path in base_dirs.items():
            if not os.path.exists(dir_path):
                os.makedirs(dir_path)
                print(f"创建目录: {dir_path}")
        
        # 加载文档
        loaders = {}
        for doc_type, dir_path in base_dirs.items():
            if os.path.exists(dir_path) and os.listdir(dir_path):  # 只在目录非空时创建loader
                if doc_type == "txt":
                    loaders[doc_type] = DirectoryLoader(
                        dir_path, 
                        glob="**/*.txt", 
                        loader_cls=TextLoader,
                        loader_kwargs={'encoding': 'utf-8'}  # 明确指定编码
                    )
                elif doc_type == "pdf":
                    loaders[doc_type] = DirectoryLoader(dir_path, glob="**/*.pdf", loader_cls=PyPDFLoader)
                elif doc_type == "md":
                    loaders[doc_type] = DirectoryLoader(dir_path, glob="**/*.md", loader_cls=UnstructuredMarkdownLoader)
        
        documents = []
        for doc_type, loader in loaders.items():
            try:
                print(f"开始加载 {doc_type} 文件...")
                docs = loader.load()
                print(f"成功从 {doc_type} 文件加载了 {len(docs)} 个文档")
                documents.extend(docs)
            except Exception as e:
                print(f"加载 {doc_type} 文档时出错: {str(e)}")
                print(f"目录 {base_dirs[doc_type]} 中的文件列表:")
                try:
                    files = os.listdir(base_dirs[doc_type])
                    for file in files:
                        print(f"  - {file}")
                except Exception as e:
                    print(f"无法列出目录内容: {str(e)}")
        
        if not documents:
            print("警告：没有成功加载任何文档！")
            return 0
            
        # 文本分割
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=50,
            separators=["\n\n", "\n", "。", "！", "？", ".", "!", "?"]
        )
        
        splits = text_splitter.split_documents(documents)
        print(f"文档分割完成，共生成 {len(splits)} 个文本块")
        
        if not splits:
            print("警告：文档分割后没有生成任何文本块！")
            return 0
            
        # 批量处理文档，避免一次性处理太多
        batch_size = 50  # 减小批次大小
        total_added = 0
        for i in range(0, len(splits), batch_size):
            batch = splits[i:i + batch_size]
            try:
                # 确保每个文档都有唯一的ID
                ids = [f"doc_{i+j}" for j in range(len(batch))]
                texts = [doc.page_content for doc in batch]
                metadatas = [doc.metadata for doc in batch]
                
                # 使用add_texts而不是add_documents
                vector_store.add_texts(
                    texts=texts,
                    metadatas=metadatas,
                    ids=ids
                )
                total_added += len(batch)
                print(f"成功添加第 {i+1} 到 {min(i+batch_size, len(splits))} 个文本块到向量存储")
            except Exception as e:
                print(f"添加文档批次 {i//batch_size + 1} 到向量存储时出错: {e}")
                print("尝试单个文档添加...")
                # 如果批量添加失败，尝试逐个添加
                for j, doc in enumerate(batch):
                    try:
                        vector_store.add_texts(
                            texts=[doc.page_content],
                            metadatas=[doc.metadata],
                            ids=[f"doc_{i+j}"]
                        )
                        total_added += 1
                    except Exception as e:
                        print(f"添加单个文档 {i+j} 失败: {e}")
        
        # 移除persist调用，因为Chroma会自动持久化
        print("向量存储更新完成")
        
        return total_added
        
    except Exception as e:
        print(f"知识库加载过程中发生错误: {e}")
        return 0

if __name__ == "__main__":
    count = load_knowledge_base()
    print(f"处理完成：共有 {count} 个文档片段被成功添加到知识库") 