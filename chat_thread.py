# chat_thread.py

from PySide6.QtCore import QThread, Signal
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langgraph.graph import StateGraph
from langchain_chroma import Chroma
from langgraph.checkpoint.memory import MemorySaver
from tongyi_embeddings import AliyunEmbeddings
from typing import TypedDict, List, Annotated, Sequence
from langchain_core.messages import BaseMessage
from langchain_core.documents import Document
from langgraph.graph.message import add_messages
from utils import get_resource, read_file
import os
import requests
import tempfile
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from PySide6.QtGui import QPixmap
import matplotlib
matplotlib.use('Agg')  # 使用非交互式后端
import networkx as nx
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from io import BytesIO
from PySide6.QtGui import QPixmap

# 设置中文字体
def get_chinese_font():
    # 根据您的系统调整字体路径
    # 例如，对于Windows，可以使用SimHei字体
    # 对于其他系统，请确保安装了合适的CJK字体
    font_path = 'C:\\Windows\\Fonts\\simhei.ttf'  # Windows上的SimHei字体路径
    if not os.path.exists(font_path):
        font_path = '/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc'  # 示例路径
    if not os.path.exists(font_path):
        raise FileNotFoundError("未找到支持中文的字体，请安装SimHei或Noto Sans CJK字体。")
    return FontProperties(fname=font_path)
# 定义状态类型
class State(TypedDict):
    """定义状态类型，包含消息历史和上下文"""
    messages: Annotated[Sequence[BaseMessage], add_messages]  # 使用Sequence而不是List以匹配LangGraph期望
    context: List[Document]

class ChatThread(QThread):
    message_received = Signal(str)
    chat_completed = Signal(str)
    audio_ready = Signal(str)
    log_signal = Signal(str)       # 日志信号
    graph_signal = Signal(QPixmap) # 图形信号

    def __init__(self, message, enable_tts=True, thread_id="default"):
        super().__init__()
        self.message = message
        self.enable_tts = enable_tts
        self.thread_id = thread_id
        self.tts_url = "http://127.0.0.1:9880/tts"
        
        # 初始化消息存储器
        self.memory = MemorySaver()
        self.log_signal.emit("Initialized MemorySaver.")
        
        # 初始化LLM
        self.llm = ChatOpenAI(
            api_key="sk-f3c14e0485944adbbeb9b6fc26d930f7",
            model="qwen-plus",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            streaming=True
        )
        self.log_signal.emit("Initialized ChatOpenAI LLM.")
        
        # 初始化向量存储
        self.embeddings = AliyunEmbeddings(
            api_key="sk-f3c14e0485944adbbeb9b6fc26d930f7",
            model="text-embedding-v2",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        self.vector_store = Chroma(
            persist_directory="./knowledge_base",
            embedding_function=self.embeddings,
            # metric="cosine"  # 确保使用余弦相似度
        )
        self.log_signal.emit("Initialized Chroma vector store.")
        
        if self.enable_tts:
            self.tts_executor = ThreadPoolExecutor(max_workers=3)
            self.log_signal.emit("Initialized TTS executor.")
            
        # 初始化对话图
        self.workflow = StateGraph(state_schema=State)
        self.setup_chat_workflow()
        self.log_signal.emit("Setup chat workflow.")

    def setup_chat_workflow(self):
        """设置对话工作流"""
        def retrieve(state: State):
            """检索相关文档"""
            self.log_signal.emit("Starting retrieve step.")
            if state["messages"]:
                last_message = state["messages"][-1].content
                self.log_signal.emit(f"Last user message: {last_message}")
                try:
                    collection = self.vector_store._collection
                    total_docs = collection.count()
                    k = min(3, total_docs)
                    
                    self.log_signal.emit(f"Total documents in vector store: {total_docs}. Retrieving top {k} documents.")
                    
                    if k > 0:
                        # 使用默认的L2距离进行检索
                        docs = self.vector_store.similarity_search_with_relevance_scores(
                            last_message,
                            k=k
                        )
                        
                        filtered_docs = []
                        self.log_signal.emit("Retrieved relevant documents:")
                        for i, (doc, score) in enumerate(docs, 1):
                            # 将相关性分数转换为0-1范围
                            similarity = score  
                            if similarity > 0.3:
                                filtered_docs.append((doc, similarity))
                                self.log_signal.emit(f"文档 {i} (相关性: {similarity:.2f}): 内容: {doc.page_content[:200]}...")
                        
                        if filtered_docs:
                            self.log_signal.emit(f"Filtered down to {len(filtered_docs)} documents based on similarity threshold.")
                            return {"context": [doc for doc, _ in filtered_docs]}
                    
                except Exception as e:
                    self.log_signal.emit(f"检索文档时出错: {e}")
            self.log_signal.emit("No relevant context found.")
            return {"context": []}

        def generate(state: State):
            """生成回答"""
            self.log_signal.emit("Starting generate step.")
            context_text = ""
            if state["context"]:
                for doc in state["context"]:
                    context_text += doc.page_content + "\n"
                self.log_signal.emit("Context retrieved for generation.")
            else:
                context_text = "没有找到相关上下文。"
                self.log_signal.emit("No context available for generation.")
    
            # 读取基础系统提示
            base_system_prompt = read_file(r"resources\prompt.txt")
            self.log_signal.emit("Loaded base system prompt.")
    
            # 创建一个新的系统消息，包含上下文信息
            system_with_context = SystemMessage(content=f"{base_system_prompt}\n\n上下文信息如下:\n{context_text}\n\n请记住用户的名字，并在对话中正确使用。")
            self.log_signal.emit("Created system message with context.")
    
            # 构建新的消息列表，包含带上下文的系统消息和所有对话历史
            messages_with_context = [system_with_context] + state["messages"]  # 包含所有消息
            self.log_signal.emit("Constructed messages with context for LLM.")
    
            response = ""
            current_sentence = ""
            
            try:
                for chunk in self.llm.stream(messages_with_context):
                    if chunk.content:
                        response += chunk.content
                        current_sentence += chunk.content
                        self.log_signal.emit(f"LLM response chunk: {chunk.content}")
                        
                        if self.enable_tts and any(punct in chunk.content for punct in ['。', '！', '？', '.', '!', '?']):
                            self.log_signal.emit(f"Detected punctuation in chunk: {chunk.content}")
                            self.handle_tts(current_sentence)
                            self.log_signal.emit(f"Handled TTS for sentence: {current_sentence}")
                            current_sentence = ""
                        
                        self.message_received.emit(chunk.content)
                self.log_signal.emit("LLM generation completed.")
                
                # Store AI message to vector store
                self.vector_store.add_texts([response])
                self.log_signal.emit("Stored AI message to vector database.")
            except Exception as e:
                self.log_signal.emit(f"生成回答时出错: {e}")
    
            # 生成状态图并发送
            self.generate_state_graph()
    
            return {"messages": [AIMessage(content=response)]}

        # 设置工作流
        self.workflow.add_node("retrieve", retrieve)
        self.workflow.add_node("generate", generate)
        self.workflow.add_edge("retrieve", "generate")
        self.workflow.set_entry_point("retrieve")
        self.log_signal.emit("Workflow configured with retrieve and generate nodes.")
        
        # 编译工作流，添加消息存储
        self.graph = self.workflow.compile(checkpointer=self.memory)
        self.log_signal.emit("Compiled workflow with checkpointer.")

    def run(self):
        try:
            # 读取基础系统提示
            base_system_prompt = read_file(r"resources\prompt.txt")
            self.log_signal.emit("Read base system prompt from file.")
            
            # 准备配置，包含 'configurable' 键
            config = {
                "configurable": {
                    "thread_id": self.thread_id,
                    # 可选添加其他键
                    # "checkpoint_ns": "default_namespace",
                    # "checkpoint_id": "default_checkpoint"
                }
            }
            self.log_signal.emit(f"Configured thread with thread_id: {self.thread_id}")
            
            # 准备系统消息和用户消息
            system_message = SystemMessage(content=f"{base_system_prompt}\n\n请记住用户的名字为：小萄。")
            user_message = HumanMessage(content=self.message)
            self.log_signal.emit(f"Initialized system and user messages. User message: {self.message}")
            
            # 准备初始状态
            initial_state = {
                "messages": [system_message, user_message],
                "context": []
            }
            self.log_signal.emit("Prepared initial state with system and user messages.")
            
            # 运行对话图，传递包含 'configurable' 的配置
            self.graph.invoke(initial_state, config)
            self.log_signal.emit("Invoked workflow graph with initial state and config.")
            
            # 存储对话到向量数据库
            self.vector_store.add_texts([self.message])
            self.log_signal.emit("Stored user message to vector database.")
            
            self.chat_completed.emit("")
            self.log_signal.emit("Chat completed successfully.")
            
        except Exception as e:
            self.log_signal.emit(f"对话处理出错: {str(e)}")
    
    def handle_tts(self, text):
        """处理TTS请求"""
        self.log_signal.emit(f"Handling TTS for text: {text}")
        future = self.tts_executor.submit(self.synthesize_speech, text)
        future.add_done_callback(self.handle_tts_result)
    
    def synthesize_speech(self, text):
        """调用TTS API合成语音"""
        self.log_signal.emit("Starting speech synthesis.")
        try:
            ref_audio_path = os.path.abspath(get_resource("resources/voice_ref.MP3"))
            self.log_signal.emit(f"Reference audio path: {ref_audio_path}")
            
            params = {
                "text": text,
                "text_lang": "zh",
                "ref_audio_path": ref_audio_path,
                "prompt_lang": "zh",
                "text_split_method": "cut5",
                "streaming_mode": False,
                "batch_size": 1,
                "speed_factor": 1.0
            }
            
            response = requests.get(self.tts_url, params=params)
            self.log_signal.emit(f"TTS API response status: {response.status_code}")
            
            if response.status_code == 200:
                with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                    temp_file.write(response.content)
                    self.log_signal.emit(f"TTS synthesis successful. Audio saved to: {temp_file.name}")
                    return temp_file.name
            else:
                self.log_signal.emit(f"TTS请求失败: {response.status_code}")
                self.log_signal.emit(f"错误详情: {response.text}")
                return None
                        
        except Exception as e:
            self.log_signal.emit(f"语音合成错误: {str(e)}")
            return None
    
    def handle_tts_result(self, future):
        """处理异步语音合成的结果"""
        self.log_signal.emit("Handling TTS result.")
        try:
            audio_path = future.result()
            if audio_path:
                self.audio_ready.emit(audio_path)
                self.log_signal.emit(f"TTS audio ready: {audio_path}")
            else:
                self.log_signal.emit("TTS audio path is None.")
        except Exception as e:
            self.log_signal.emit(f"处理TTS结果时出错: {str(e)}")
    
    def generate_state_graph(self):
        """生成状态图的图像并发送给主界面"""
        try:
            self.log_signal.emit("Generating state graph.")
            G = nx.DiGraph()
            for node in self.workflow.nodes:
                G.add_node(node)
            for edge in self.workflow.edges:
                G.add_edge(edge[0], edge[1])
            
            plt.figure(figsize=(4, 4))
            pos = nx.spring_layout(G)
            font = get_chinese_font()
            nx.draw(G, pos, with_labels=True, node_color='lightblue', arrows=True, font_family=font.get_name())
            plt.title("对话状态图", fontproperties=font)
            
            buf = BytesIO()
            plt.savefig(buf, format='png', bbox_inches='tight')
            buf.seek(0)
            pixmap = QPixmap()
            pixmap.loadFromData(buf.getvalue())
            self.graph_signal.emit(pixmap)
            plt.close()
            self.log_signal.emit("State graph generated and emitted.")
        except Exception as e:
            self.log_signal.emit(f"生成状态图时出错: {e}")
