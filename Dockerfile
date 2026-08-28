# 标准 Docker 化部署：多阶段构建，最终镜像同源托管「前端 UI + 后端 API」。
#
# 阶段1 用 node 镜像把 Vue3 前端 build 成静态文件（dist/）；
# 阶段2 用 python 镜像跑 FastAPI，并把阶段1 的 dist/ 拷进 /app/static，
# 由 main.py 挂载，使访问根路径即中文 UI、/api 仍是后端接口（同源、免 CORS）。
#
# 为什么锁 python 3.12：chroma-hnswlib 没有 cp313 的官方 wheel，只能现场编译。
# 为什么锁 node 20：vite 5 在 node 18+ 均兼容，20 为 LTS 稳妥之选。

# ---- 阶段1：构建前端 ----
FROM node:20-slim AS frontend-build
WORKDIR /fe
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ .
# VITE_API_BASE 留空 → 前端走相对路径 /api（同源部署），无需 CORS
RUN npm run build

# ---- 阶段2：后端 ----
FROM python:3.12-slim
WORKDIR /app

# 先 copy requirements 单独装依赖，最大化利用 Docker 缓存
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 再 copy 业务代码
COPY backend/ .

# 从阶段1 拷贝前端构建产物到 /app/static
COPY --from=frontend-build /fe/dist ./static

# Render 会注入 $PORT 环境变量；本地 8000 默认
ENV PORT=8000
EXPOSE 8000

# 用 Python 启动脚本读 PORT 环境变量，避免 shell 展开 + Railway 'cd' 包装器的坑
CMD ["python", "start.py"]
