import sys, os
import logging, subprocess
import requests, time

logger = logging.getLogger(__name__)

def get_resource(relative_path):
    """通过相对路径，获取资源文件的绝对路径。这样获取路径方便程序打包"""
    if hasattr(sys, '_MEIPASS'):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(".")
    
    return os.path.join(base_path, relative_path)

def read_file(file_path):
    '''读取文件内容，用于林黛玉prompt的读取'''
    absolute_path = get_resource(file_path)
    with open(absolute_path, 'r', encoding='utf-8') as file:
        profile = file.read()
    return profile

def start_tts_server():
    """启动TTS服务器"""
    try:
        # 获取GPT-SoVITS目录的绝对路径
        gpt_sovits_dir = os.path.join(os.getcwd(), "GPT-SoVITS-v2-240821")
        
        # 启动TTS服务器进程
        tts_process = subprocess.Popen(
            [sys.executable, "api_v2.py"],
            cwd=gpt_sovits_dir,  # 设置工作目录
            # stdout=subprocess.PIPE,
            # stderr=subprocess.PIPE
        )
        
        # 等待服务器启动
        max_retries = 30
        retry_interval = 1
        for i in range(max_retries):
            try:
                response = requests.get("http://127.0.0.1:9880/tts")
                if response.status_code == 400:  # API正常响应,但缺少参数
                    logger.info("TTS服务器启动成功")
                    return tts_process
            except requests.exceptions.ConnectionError:
                if i < max_retries - 1:
                    time.sleep(retry_interval)
                    continue
                else:
                    raise Exception("TTS服务器启动超时")
                
    except Exception as e:
        logger.error(f"启动TTS服务器失败: {str(e)}")
        raise
