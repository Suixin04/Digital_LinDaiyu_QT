from langchain_chroma import Chroma
from tongyi_embeddings import AliyunEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import (
    DirectoryLoader,
    TextLoader,
    PyPDFLoader,
    UnstructuredMarkdownLoader
)

def load_knowledge_base():
    # 初始化embeddings
    embeddings = AliyunEmbeddings(
        api_key="sk-f3c14e0485944adbbeb9b6fc26d930f7",
        model="text-embedding-v2",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
    
    # 初始化向量存储
    vector_store = Chroma(
        persist_directory="./knowledge_base",  # 持久化存储路径
        embedding_function=embeddings
    )
    
    # 加载文档
    loaders = {
        "txt": DirectoryLoader("./knowledge/txt", glob="**/*.txt", loader_cls=TextLoader),
        "pdf": DirectoryLoader("./knowledge/pdf", glob="**/*.pdf", loader_cls=PyPDFLoader),
        "md": DirectoryLoader("./knowledge/md", glob="**/*.md", loader_cls=UnstructuredMarkdownLoader),
    }
    
    documents = []
    for loader in loaders.values():
        try:
            documents.extend(loader.load())
        except Exception as e:
            print(f"加载文档时出错: {e}")
    
    # 文本分割
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50,
        separators=["\n\n", "\n", "。", "！", "？", ".", "!", "?"]
    )
    
    splits = text_splitter.split_documents(documents)
    
    # 将文档加入向量存储
    vector_store.add_documents(splits)
    
    return len(splits)

if __name__ == "__main__":
    count = load_knowledge_base()
    print(f"成功加载 {count} 个文档片段到知识库") 