# TexTrans 前端镜像:Next.js standalone 多阶段构建
# 构建阶段用完整 node,运行阶段只带 standalone 产物,镜像小。

# ---- 构建阶段 ----
FROM node:20-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# next.config.js 已设 output:'standalone'
RUN npm run build

# ---- 运行阶段 ----
FROM node:20-slim AS run
WORKDIR /app
ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME=0.0.0.0
# standalone 产物自带最小 node_modules 与 server.js
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
EXPOSE 3000
CMD ["node", "server.js"]
