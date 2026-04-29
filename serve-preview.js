// 轻量静态服务器，将 ai-tools-guide 目录暴露在 PORT 端口
const http = require('http');
const fs   = require('fs');
const path = require('path');

const PORT  = process.env.PORT || 8899;
const ROOT  = path.resolve(__dirname, '../../../../../ai-tools-guide');

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js':   'application/javascript',
  '.css':  'text/css',
  '.json': 'application/json',
  '.md':   'text/plain; charset=utf-8',
  '.png':  'image/png',
  '.svg':  'image/svg+xml',
};

http.createServer((req, res) => {
  let pathname = req.url.split('?')[0];
  if (pathname === '/') pathname = '/index.html';

  const filePath = path.join(ROOT, pathname);

  // Security: stay inside ROOT
  if (!filePath.startsWith(ROOT)) {
    res.writeHead(403); res.end('Forbidden'); return;
  }

  fs.readFile(filePath, (err, data) => {
    if (err) { res.writeHead(404); res.end('Not found'); return; }
    const ext  = path.extname(filePath);
    const type = MIME[ext] || 'application/octet-stream';
    res.writeHead(200, { 'Content-Type': type });
    res.end(data);
  });
}).listen(PORT, () => console.log(`AI Tools Guide preview → http://localhost:${PORT}`));
