Anaconda工具下载：
https://www.anaconda.com/download/success?reg=skipped

# 1. 设定清华源 (如果之前设过可以跳过)
conda config --add channels https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/free/
conda config --add channels https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/main/
conda config --set show_channel_urls yes

# 2. 创建 Python 3.12 环境
conda create -n traffic_cpu python=3.12 -y

# 3. 激活环境
conda activate traffic_cpu

# 设定 pip 清华源加速
pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

# 安装核心库 (会自动安装轻量版 Torch 和所有依赖)
pip install ultralytics deep-sort-realtime pandas openpyxl pillow opencv-python
