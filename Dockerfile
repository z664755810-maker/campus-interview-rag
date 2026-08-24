# 标准 Docker 化部署：用官方 python:3.12-slim 镜像
#
# 为什么放弃 nixpacks：
#   1) nixpacks 的 python312 默认不带 pip（要靠 ensurepip）
#   2) nixpacks 的 ensurepip 又被 Nix 的 PEP 668 拦了（/nix/store 只读）
#   3) 加 python312Packages.pip 又触发 cffi 在 Py3.12 现场编译失败
#   三个坑连踩三次后，Dockerfile 是最稳的工业级方案。
#
# 为什么锁 3.12：chroma-hnswlib 没有 cp313 的官方 wheel，只能现场编译。
FROM python:3.12-slim

# 容器内工作目录
WORKDIR /app

# 先 copy requirements 单独装依赖，最大化利用 Docker 缓存
# （下次只改代码不会重装依赖）
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 再 copy 业务代码
COPY backend/ .

# Railway 会注入 $PORT 环境变量；本地 8000 默认
ENV PORT=8000
EXPOSE 8000

# 用 Python 启动脚本读 PORT 环境变量，避免 shell 展开 + Railway 'cd' 包装器的坑
CMD ["python", "start.py"]
