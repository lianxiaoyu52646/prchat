# 基于 Python 3.9 镜像
FROM python:3.9

# 设置工作目录
WORKDIR /app

# 复制项目文件到工作目录
COPY . .

# 安装依赖
RUN pip install -r requirements.txt

# 暴露端口
EXPOSE 8025

# 启动命令
CMD ["python", "WsH.py"]
