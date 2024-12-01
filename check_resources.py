import os
import sys
import shutil

'''用于检查环境配置是否符合要求，运行以检查资源'''

def create_directory(path):
    """创建目录"""
    if not os.path.exists(path):
        os.makedirs(path)
        print(f"创建目录: {path}")

def check_and_create_config():
    """检查并创建配置文件"""
    config_dir = "GPT-SoVITS-v2-240821/configs"
    config_file = f"{config_dir}/tts_infer.yaml"
    
    create_directory(config_dir)
    
    if not os.path.exists(config_file):
        config_content = """# TTS 配置文件
gpt_path: "GPT_SoVITS/pretrained_models/s1bert25hz-2kh-longer-epoch=68e-step=50232.ckpt"
sovits_path: "GPT_SoVITS/pretrained_models/s2G488k.pth"
bert_path: "GPT_SoVITS/pretrained_models/chinese-roberta-wwm-ext-large"
device: "cuda"
language_reference_rate: 0.7
"""
        with open(config_file, 'w', encoding='utf-8') as f:
            f.write(config_content)
        print(f"创建配置文件: {config_file}")

def check_resources():
    """检查必要的资源文件是否存在"""
    # 创建必要的目录结构
    directories = [
        "resources",
        "resources/samples",
        "GPT-SoVITS-v2-240821/configs",
        "GPT-SoVITS-v2-240821/GPT_SoVITS/pretrained_models"
    ]
    
    for directory in directories:
        create_directory(directory)
    
    # 创建配置文件
    check_and_create_config()
    
    # 检查必要文件
    required_files = [
        "resources/prompt.txt",
        "resources/background.jpg",
        "resources/voice_ref.MP3",
        "GPT-SoVITS-v2-240821/configs/tts_infer.yaml",
    ]
    
    # 检查模型文件（这些文件可能很大，单独列出）
    model_files = [
        "GPT-SoVITS-v2-240821/GPT_SoVITS/pretrained_models/s1bert25hz-2kh-longer-epoch=68e-step=50232.ckpt",
        "GPT-SoVITS-v2-240821/GPT_SoVITS/pretrained_models/s2G488k.pth"
    ]
    
    missing_files = []
    missing_models = []
    
    # 检查基本文件
    for file_path in required_files:
        if not os.path.exists(file_path):
            missing_files.append(file_path)
    
    # 检查模型文件
    for model_path in model_files:
        if not os.path.exists(model_path):
            missing_models.append(model_path)
    
    # 报告缺失文件
    if missing_files:
        print("\n错误：以下必要文件缺失：")
        for file in missing_files:
            print(f"- {file}")
    
    if missing_models:
        print("\n警告：以下模型文件缺失：")
        for model in missing_models:
            print(f"- {model}")
        print("\n请确保已下载必要的模型文件并放置在正确位置。")
    
    # 只有基本文件缺失时返回False
    return len(missing_files) == 0

if __name__ == "__main__":
    print("检查资源文件结构...")
    if not check_resources():
        sys.exit(1)
    print("基本资源文件检查通过！")
    print("请确保模型文件已正确放置。") 