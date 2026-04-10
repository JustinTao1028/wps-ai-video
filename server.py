#!/usr/bin/env python3
"""
WPS AI Video — 代理服务器 (Python 版)
零第三方依赖，仅使用 Python 标准库
功能：解决 CORS、隐藏 API Key、代理火山引擎 + Pexels 请求、托管静态文件

本地使用：  python3 server.py → 浏览器打开 http://localhost:3000
线上部署：  Render / Railway 等平台通过环境变量注入 PORT 和 API Key
"""

import http.server
import json
import ssl
import os
import sys
from urllib.request import Request, urlopen
from urllib.parse import urlparse, parse_qs, urlencode, quote
from urllib.error import HTTPError, URLError

PORT = int(os.environ.get('PORT', 3000))
DIR = os.path.dirname(os.path.abspath(__file__))

# ===== API Keys: 优先从环境变量读取（线上部署），否则用本地默认值（开发用） =====
VOLC_KEY = os.environ.get('VOLC_KEY', '9e8d92ce-efb9-43f7-8ce4-e626ce9f3be5')
PEXELS_KEY = os.environ.get('PEXELS_KEY', '3GwAf7wP2Ko2D8AzMqw0jwG0JifazL29f6H1kuMrFPiWf3YXmV7pD9pl')

# SSL Context (忽略证书验证，开发环境适用)
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

MIME_MAP = {
    '.html': 'text/html; charset=utf-8', '.css': 'text/css', '.js': 'application/javascript',
    '.json': 'application/json', '.png': 'image/png', '.jpg': 'image/jpeg',
    '.gif': 'image/gif', '.svg': 'image/svg+xml', '.ico': 'image/x-icon', '.mp4': 'video/mp4'
}


class ProxyHandler(http.server.BaseHTTPRequestHandler):
    """处理所有 HTTP 请求"""

    def log_message(self, fmt, *args):
        """自定义日志格式"""
        print(f"  [{self.command}] {args[0]}" if args else "")

    def _cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        try:
            # ---------- GET /api/task/:id ----------
            if path.startswith('/api/task/'):
                task_id = path.replace('/api/task/', '')
                print(f"  [代理] 查询任务: {task_id}")
                url = f"https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks/{task_id}"
                req = Request(url, method='GET', headers={'Authorization': f'Bearer {VOLC_KEY}'})
                resp = urlopen(req, context=ctx, timeout=30)
                body = resp.read()
                self.send_response(resp.status)
                self._cors_headers()
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(body)
                return

            # ---------- GET /api/pexels/videos ----------
            if path == '/api/pexels/videos':
                query = qs.get('query', ['technology'])[0]
                per_page = qs.get('per_page', ['8'])[0]
                page = qs.get('page', ['1'])[0]
                print(f"  [代理] Pexels 搜索: {query}")
                url = f"https://api.pexels.com/videos/search?query={quote(query)}&per_page={per_page}&page={page}"
                req = Request(url, method='GET', headers={
                    'Authorization': PEXELS_KEY,
                    'User-Agent': 'WPS-AI-Video/1.0'
                })
                resp = urlopen(req, context=ctx, timeout=15)
                body = resp.read()
                self.send_response(resp.status)
                self._cors_headers()
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(body)
                return

            # ---------- GET /api/proxy-download ----------
            if path == '/api/proxy-download':
                target_url = qs.get('url', [None])[0]
                if not target_url:
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b'Missing url param')
                    return
                print(f"  [代理] 下载视频: {target_url[:60]}...")
                req = Request(target_url, method='GET')
                resp = urlopen(req, context=ctx, timeout=120)
                self.send_response(200)
                self._cors_headers()
                self.send_header('Content-Type', resp.headers.get('Content-Type', 'video/mp4'))
                self.send_header('Content-Disposition', 'attachment; filename="wps_ai_video.mp4"')
                self.end_headers()
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                return

            # ---------- 静态文件 ----------
            file_path = path
            if file_path == '/':
                file_path = '/ai_studio_code.html'
            file_path = os.path.join(DIR, file_path.lstrip('/'))
            file_path = os.path.realpath(file_path)

            # 安全检查：防止目录遍历
            if not file_path.startswith(DIR):
                self.send_response(403)
                self.end_headers()
                return

            if os.path.isfile(file_path):
                ext = os.path.splitext(file_path)[1].lower()
                ct = MIME_MAP.get(ext, 'application/octet-stream')
                with open(file_path, 'rb') as f:
                    data = f.read()
                self.send_response(200)
                self._cors_headers()
                self.send_header('Content-Type', ct)
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            else:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b'404 Not Found')

        except HTTPError as e:
            print(f"  [HTTP错误] {e.code}: {e.reason}")
            body = e.read() if hasattr(e, 'read') else b'{}'
            self.send_response(e.code)
            self._cors_headers()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            print(f"  [异常] {str(e)}")
            self.send_response(502)
            self._cors_headers()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': str(e)}).encode())

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        try:
            # ---------- POST /api/generate ----------
            if path == '/api/generate':
                content_length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(content_length)
                print(f"  [代理] POST 创建任务 ({content_length} bytes)")

                url = 'https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks'
                req = Request(url, data=body, method='POST', headers={
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {VOLC_KEY}'
                })
                resp = urlopen(req, context=ctx, timeout=60)
                resp_body = resp.read()
                print(f"  [代理] 火山引擎响应: {resp.status}")

                self.send_response(resp.status)
                self._cors_headers()
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(resp_body)
                return

            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Not Found')

        except HTTPError as e:
            print(f"  [HTTP错误] {e.code}: {e.reason}")
            body = e.read() if hasattr(e, 'read') else b'{}'
            self.send_response(e.code)
            self._cors_headers()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            print(f"  [异常] {str(e)}")
            self.send_response(502)
            self._cors_headers()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': str(e)}).encode())


if __name__ == '__main__':
    server = http.server.HTTPServer(('0.0.0.0', PORT), ProxyHandler)
    print()
    print('  ╔══════════════════════════════════════════════════╗')
    print('  ║   🚀 WPS AI Video 本地代理服务器已就绪            ║')
    print(f'  ║   🌐 浏览器打开: http://localhost:{PORT}             ║')
    print(f'  ║   📁 目录: {DIR[:36]:<37s}║')
    print('  ╚══════════════════════════════════════════════════╝')
    print()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n  ⏹ 服务器已停止')
        server.server_close()
