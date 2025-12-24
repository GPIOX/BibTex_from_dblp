from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from typing import List, Optional
import time
import tempfile
import requests
import os
from urllib.parse import urlencode
app = FastAPI(title="DBLP BibTeX Fetcher")

HTTP_PROXY = os.environ.get('HTTP_PROXY', '')
HTTPS_PROXY = os.environ.get('HTTPS_PROXY', '')
PROXIES = None
if HTTP_PROXY or HTTPS_PROXY:
    PROXIES = {}
    if HTTP_PROXY:
        PROXIES['http'] = HTTP_PROXY
    if HTTPS_PROXY:
        PROXIES['https'] = HTTPS_PROXY

class SearchRequest(BaseModel):
    keywords: List[str]
    max_results: int = 10

class BibEntry(BaseModel):
    title: str
    authors: str
    year: Optional[str]
    bibtex: str

def generate_bibtex_simple(title: str, authors: List[str], year: Optional[str], url: Optional[str]) -> str:
    import re
    key_base = re.sub(r'[^a-zA-Z0-9]+', '_', (title or 'entry').lower()).strip('_')
    key_year = year if year and str(year).isdigit() else 'noyear'
    key = f"{key_base[:40]}_{key_year}"
    author_str = ' and '.join([a for a in authors if a]) if authors else 'Unknown'
    lines = []
    lines.append(f"@article{{{key},")
    lines.append(f"  title={{{{ {title} }}}},")
    lines.append(f"  author={{{{ {author_str} }}}},")
    if year:
        lines.append(f"  year={{{{ {year} }}}},")
    if url:
        lines.append(f"  url={{{{ {url} }}}},")
    lines.append("}")
    return "\n".join(lines)

def _dblp_authors(info_authors) -> List[str]:
    names = []
    if isinstance(info_authors, dict) and 'author' in info_authors:
        authors = info_authors['author']
        if isinstance(authors, list):
            for a in authors:
                t = a.get('text') if isinstance(a, dict) else str(a)
                if t:
                    names.append(t)
        elif isinstance(authors, dict):
            t = authors.get('text')
            if t:
                names.append(t)
        else:
            t = str(authors)
            if t:
                names.append(t)
    return names

def _fetch_bibtex_from_info(info: dict) -> Optional[str]:
    urls = []
    u = info.get('url')
    k = info.get('key')
    if u:
        urls.append(u + '.bib' if not u.endswith('.bib') else u)
        urls.append(u + '?view=bibtex')
    if k:
        urls.append(f'https://dblp.org/rec/bibtex/{k}.bib')
        urls.append(f'https://dblp.org/rec/{k}.bib')
    seen = set()
    headers = {'User-Agent': 'Mozilla/5.0'}
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        try:
            r = requests.get(url, timeout=20, proxies=PROXIES, headers=headers, allow_redirects=True)
            if r.status_code == 200 and r.text.strip().startswith('@'):
                return r.text
        except Exception:
            pass
    return None

def search_dblp(query: str, num_results: int = 10) -> List[dict]:
    results = []
    try:
        params = {'q': query, 'h': num_results, 'f': 0, 'format': 'json'}
        url = 'https://dblp.org/search/publ/api?' + urlencode(params)
        r = requests.get(url, timeout=30, proxies=PROXIES, headers={'User-Agent': 'Mozilla/5.0'})
        if r.status_code != 200:
            return results
        data = r.json()
        hits = data.get('result', {}).get('hits', {}).get('hit', [])
        if isinstance(hits, dict):
            hits = [hits]
        for h in hits[:num_results]:
            info = h.get('info', {})
            title = info.get('title', 'N/A')
            authors = _dblp_authors(info.get('authors'))
            year = str(info.get('year')) if info.get('year') else None
            bibtex = _fetch_bibtex_from_info(info) or generate_bibtex_simple(title, authors, year, info.get('url'))
            results.append({'title': title, 'authors': authors, 'year': year, 'bibtex': bibtex})
    except Exception:
        pass
    return results

@app.post("/api/search")
async def search_papers(request: SearchRequest):
    all_results = []
    for i, keyword in enumerate(request.keywords):
        papers = search_dblp(keyword, request.max_results)
        for paper in papers:
            all_results.append({
                'title': paper.get('title', 'N/A'),
                'authors': ', '.join(paper.get('authors', [])) if paper.get('authors') else 'N/A',
                'year': str(paper.get('year', 'N/A')),
                'bibtex': paper.get('bibtex', '')
            })
        if i < len(request.keywords) - 1:
            time.sleep(1.0)
    if not all_results:
        return {"total": 0, "results": []}
    return {"total": len(all_results), "results": all_results}

@app.get("/api/check-dblp")
async def check_dblp():
    try:
        r = requests.get('https://dblp.org/search/publ/api?q=test&h=1&format=json', timeout=10, proxies=PROXIES)
        ok = r.status_code == 200
        return {"reachable": ok}
    except Exception:
        return {"reachable": False}

@app.post("/api/download")
async def download_bibtex(results: List[BibEntry]):
    """下载所有BibTeX为一个文件"""
    bibtex_content = "\n\n".join([entry.bibtex for entry in results])
    
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.bib', encoding='utf-8') as f:
        f.write(bibtex_content)
        temp_path = f.name
    
    return FileResponse(
        temp_path,
        media_type='application/x-bibtex',
        filename='references.bib',
        background=None
    )

@app.get("/", response_class=HTMLResponse)
async def read_root():
    html_content = """
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>DBLP BibTeX 批量获取工具</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }
            
            .container {
                max-width: 1200px;
                margin: 0 auto;
                background: white;
                border-radius: 15px;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                overflow: hidden;
            }
            
            .header {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 30px;
                text-align: center;
            }
            
            .header h1 { font-size: 2em; margin-bottom: 10px; }
            .header p { font-size: 1.1em; opacity: 0.9; }
            
            .api-status {
                padding: 15px;
                margin: 20px 30px;
                border-radius: 8px;
                border-left: 4px solid #667eea;
            }
            
            .api-status.ok { background: #d4edda; border-left-color: #28a745; }
            .api-status.warning { background: #fff3cd; border-left-color: #ffc107; }
            
            .info-box {
                background: #e7f3ff;
                border: 1px solid #2196F3;
                color: #0d47a1;
                padding: 15px;
                border-radius: 8px;
                margin: 20px 30px;
            }
            
            .info-title { font-weight: 600; margin-bottom: 8px; font-size: 1.1em; }
            
            .content { padding: 30px; }
            .input-section { margin-bottom: 20px; }
            
            label {
                display: block;
                margin-bottom: 10px;
                font-weight: 600;
                color: #333;
            }
            
            textarea, input[type="text"], input[type="number"] {
                width: 100%;
                padding: 12px;
                border: 2px solid #e0e0e0;
                border-radius: 8px;
                font-size: 14px;
                font-family: inherit;
                transition: border-color 0.3s;
            }
            
            textarea { resize: vertical; min-height: 120px; }
            input:focus, textarea:focus { outline: none; border-color: #667eea; }
            
            .button-group { display: flex; gap: 15px; margin-top: 20px; }
            
            button {
                flex: 1;
                padding: 15px 30px;
                font-size: 16px;
                font-weight: 600;
                border: none;
                border-radius: 8px;
                cursor: pointer;
                transition: all 0.3s;
            }
            
            .btn-primary {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
            }
            
            .btn-primary:hover:not(:disabled) {
                transform: translateY(-2px);
                box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
            }
            
            .btn-secondary { background: #f0f0f0; color: #333; }
            .btn-secondary:hover:not(:disabled) { background: #e0e0e0; }
            button:disabled { background: #ccc; cursor: not-allowed; transform: none; }
            
            .results-section { margin-top: 30px; }
            
            .result-item {
                background: #f8f9fa;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                padding: 20px;
                margin-bottom: 15px;
                transition: box-shadow 0.3s;
            }
            
            .result-item:hover {
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            }
            
            .result-title {
                font-size: 1.2em;
                font-weight: 600;
                color: #333;
                margin-bottom: 10px;
                line-height: 1.4;
            }
            
            .result-meta { 
                color: #666; 
                margin-bottom: 15px;
                font-size: 0.95em;
            }
            
            .bibtex-code {
                background: #2d2d2d;
                color: #f8f8f2;
                padding: 15px;
                border-radius: 5px;
                font-family: 'Courier New', monospace;
                font-size: 13px;
                overflow-x: auto;
                white-space: pre-wrap;
                line-height: 1.5;
            }
            
            .loading {
                text-align: center;
                padding: 40px;
                color: #667eea;
                font-size: 1.2em;
            }
            
            .spinner {
                border: 4px solid #f3f3f3;
                border-top: 4px solid #667eea;
                border-radius: 50%;
                width: 40px;
                height: 40px;
                animation: spin 1s linear infinite;
                margin: 20px auto;
            }
            
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
            
            .stats {
                background: #e8f4f8;
                padding: 15px;
                border-radius: 8px;
                margin-bottom: 20px;
                text-align: center;
                font-weight: 600;
                font-size: 1.1em;
            }
            
            .error {
                background: #f8d7da;
                border: 1px solid #f5c6cb;
                color: #721c24;
                padding: 15px;
                border-radius: 8px;
                margin: 20px 0;
            }
            
            code {
                background: #f4f4f4;
                padding: 2px 6px;
                border-radius: 3px;
                font-family: 'Courier New', monospace;
                font-size: 0.9em;
            }
            
            .link { 
                color: #667eea; 
                text-decoration: none; 
                font-weight: 600;
                transition: color 0.3s;
            }
            .link:hover { color: #764ba2; text-decoration: underline; }
            
            ul { line-height: 1.8; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>📚 DBLP BibTeX 批量获取工具</h1>
                <p>使用 DBLP Search API 获取 BibTeX</p>
            </div>
            
            <div id="apiStatus" class="api-status">
                <strong>🔄 正在检查 DBLP 连通性...</strong>
            </div>
            
            <div class="info-box">
                <div class="info-title">📖 使用说明</div>
                <ol style="margin-left: 20px; margin-top: 8px;">
                    <li>输入论文标题或关键词，点击开始搜索</li>
                    <li>系统将调用 DBLP 搜索并获取 BibTeX</li>
                    <li>支持批量关键词，每行一个</li>
                </ol>
                <p style="margin-top: 10px;">无需 API Key；若失败，请稍后重试。</p>
            </div>
            
            <div class="content">
                
                
                <div class="input-section">
                    <label for="keywords">搜索关键词或论文标题（每行一个）：</label>
                    <textarea id="keywords" rows="6" placeholder="建议输入完整论文标题以获得最准确的结果，例如：&#10;&#10;Attention is all you need&#10;BERT: Pre-training of Deep Bidirectional Transformers&#10;Deep Residual Learning for Image Recognition"></textarea>
                </div>
                
                <div class="input-section">
                    <label for="maxResults">每个关键词最大结果数（1-10）：</label>
                    <input type="number" id="maxResults" value="5" min="1" max="10">
                    <small style="color: #666; margin-top: 5px; display: block;">
                        注意：每个结果约需2次请求（搜索+获取BibTeX），请合理设置数量
                    </small>
                </div>
                
                <div class="button-group">
                    <button class="btn-primary" onclick="searchPapers()" id="searchBtn">🔍 开始搜索</button>
                    <button class="btn-secondary" onclick="downloadAll()" id="downloadBtn" disabled>💾 下载所有BibTeX</button>
                </div>
                
                <div id="results"></div>
            </div>
        </div>
        
        <script>
            let currentResults = [];
            
            window.addEventListener('DOMContentLoaded', checkAPIStatus);
            
            async function checkAPIStatus() {
                try {
                    const response = await fetch('/api/check-dblp');
                    const data = await response.json();
                    const statusDiv = document.getElementById('apiStatus');
                    
                    if (data.reachable) {
                        statusDiv.className = 'api-status ok';
                        statusDiv.innerHTML = `
                            <strong>✓ DBLP 可访问</strong>
                        `;
                    } else {
                        statusDiv.className = 'api-status warning';
                        statusDiv.innerHTML = `
                            <strong>⚠ 无法访问 DBLP</strong><br>
                            请检查网络连接后重试
                        `;
                    }
                } catch (error) {
                    console.error('Failed to check API status:', error);
                }
            }
            
            async function searchPapers() {
                const keywordsText = document.getElementById('keywords').value;
                const maxResults = parseInt(document.getElementById('maxResults').value);
                
                
                const keywords = keywordsText.split('\\n')
                    .map(k => k.trim())
                    .filter(k => k.length > 0);
                const estimatedCalls = keywords.length * maxResults * 2;
                if (keywords.length === 0) {
                    alert('请输入至少一个关键词或论文标题！');
                    return;
                }
                
                
                
                const resultsDiv = document.getElementById('results');
                const searchBtn = document.getElementById('searchBtn');
                
                searchBtn.disabled = true;
                resultsDiv.innerHTML = `
                    <div class="loading">
                        <div class="spinner"></div>
                        <div>正在从 DBLP 获取数据...</div>
                        <small style="color: #999; margin-top: 10px; display: block;">
                            正在处理 ${keywords.length} 个关键词，每个最多 ${maxResults} 篇论文<br>
                            预计使用 ${estimatedCalls} 次请求
                        </small>
                    </div>
                `;
                
                try {
                    const response = await fetch('/api/search', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            keywords: keywords,
                            max_results: maxResults
                        })
                    });
                    
                    if (!response.ok) {
                        const error = await response.json();
                        throw new Error(error.detail || '搜索失败');
                    }
                    
                    const data = await response.json();
                    currentResults = data.results;
                    if (data.total === 0) {
                        resultsDiv.innerHTML = `
                            <div class="error">
                                <strong>未找到任何论文</strong><br><br>
                                请检查关键词是否完整，或尝试不同的关键词。
                            </div>
                        `;
                    } else {
                        displayResults(data);
                        document.getElementById('downloadBtn').disabled = false;
                    }
                    
                    // 刷新API状态
                    setTimeout(checkAPIStatus, 1000);
                    
                } catch (error) {
                    resultsDiv.innerHTML = `
                        <div class="error">
                            <strong>❌ 搜索失败</strong><br><br>
                            ${error.message}<br><br>
                            <strong>可能的原因：</strong>
                            <ul style="margin-left: 20px; margin-top: 10px;">
                                <li>网络连接问题</li>
                                <li>关键词格式不正确</li>
                                <li>DBLP 暂时不可用</li>
                            </ul>
                            <p style="margin-top: 10px;">DBLP 无需 API Key；请稍后重试。</p>
                        </div>
                    `;
                } finally {
                    searchBtn.disabled = false;
                }
            }
            
            function displayResults(data) {
                const resultsDiv = document.getElementById('results');
                
                let html = `
                    <div class="results-section">
                        <div class="stats">
                            📊 成功获取 ${data.total} 篇论文的 BibTeX 信息
                        </div>
                `;
                
                data.results.forEach((result, index) => {
                    html += `
                        <div class="result-item">
                            <div class="result-title">
                                ${index + 1}. ${escapeHtml(result.title)}
                            </div>
                            <div class="result-meta">
                                👤 作者: ${escapeHtml(result.authors)} | 
                                📅 年份: ${result.year}
                            </div>
                            <div class="bibtex-code">${escapeHtml(result.bibtex)}</div>
                        </div>
                    `;
                });
                
                html += '</div>';
                resultsDiv.innerHTML = html;
            }
            
            async function downloadAll() {
                if (currentResults.length === 0) {
                    alert('没有可下载的结果！');
                    return;
                }
                
                try {
                    const response = await fetch('/api/download', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(currentResults)
                    });
                    
                    if (!response.ok) throw new Error('下载失败');
                    
                    const blob = await response.blob();
                    const url = window.URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = 'references.bib';
                    document.body.appendChild(a);
                    a.click();
                    window.URL.revokeObjectURL(url);
                    document.body.removeChild(a);
                    
                    alert(`成功下载 ${currentResults.length} 篇论文的 BibTeX 信息！`);
                    
                } catch (error) {
                    alert('下载失败: ' + error.message);
                }
            }
            
            function escapeHtml(text) {
                const div = document.createElement('div');
                div.textContent = text;
                return div.innerHTML;
            }
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
