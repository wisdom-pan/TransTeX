/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // 生成自包含产物,便于做精简 Docker 镜像
  output: 'standalone',
  // 把 /api 与 /ws 代理到 FastAPI 后端,避免 CORS 并隐藏后端地址
  async rewrites() {
    const backend = process.env.TEXTRANS_API_URL || 'http://127.0.0.1:8000'
    return [
      { source: '/api/:path*', destination: `${backend}/api/:path*` },
      { source: '/ws/:path*', destination: `${backend}/ws/:path*` },
    ]
  },
}

export default nextConfig
