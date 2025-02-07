# 使用 Python 3.9 作为基础镜像
FROM python:3.9

# 设置工作目录
WORKDIR /app

# 复制项目文件到工作目录
COPY . .

# 创建虚拟环境
RUN python -m venv venv

# 激活虚拟环境并安装依赖
RUN . venv/bin/activate && pip install -r requirements.txt

# 设置容器启动命令
CMD ["python", "app.py"]
