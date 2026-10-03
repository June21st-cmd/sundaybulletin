"""
향린교회 공식 홈페이지 성서읽기 게시판(board_hVTK46) 원문 자동 수집 스크립트

사용법:
    python scripts/fetch_sunday_scripture.py [YYYY-MM-DD]

원칙 (규칙 제0조, 제23조):
    - AI 자체 기억에 의한 성경 본문 인용을 원천 차단하고,
    - 교회 홈페이지 목회마당 '이번주 성서읽기' 게시판의 실제 공식 본문(새번역 2001 개정)만 추출합니다.
"""

import sys
import io
import re
import urllib.request
from datetime import datetime, timedelta

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE_URL = "https://www.hyanglin.org/board_hVTK46"

def get_sunday_date(arg_date=None):
    if arg_date:
        return arg_date
    today = datetime.now()
    # Find upcoming Sunday (weekday 6)
    days_ahead = 6 - today.weekday()
    if days_ahead < 0:
        days_ahead += 7
    target_sunday = today + timedelta(days=days_ahead)
    return target_sunday.strftime("%Y-%m-%d")

def fetch_post_url(target_date: str):
    req = urllib.request.Request(BASE_URL, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=10) as resp:
        html = resp.read().decode('utf-8', errors='ignore')
        # Look for table rows containing the date
        for tr in re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL):
            if target_date in tr:
                m = re.search(r'href="([^"]+)"', tr)
                if m:
                    url = m.group(1)
                    if not url.startswith("http"):
                        url = "https://www.hyanglin.org" + url
                    return url
    return None

def fetch_scripture_content(post_url: str):
    req = urllib.request.Request(post_url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=10) as resp:
        html = resp.read().decode('utf-8', errors='ignore')
        body = re.search(r'<div[^>]+class="[^"]*xe_content[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL)
        if body:
            content = body.group(1)
            content = re.sub(r'<br\s*/?>', '\n', content)
            content = re.sub(r'<p[^>]*>', '\n', content)
            content = re.sub(r'</p>', '\n', content)
            content = re.sub(r'<[^>]+>', '', content)
            return content.strip()
    return ""

def parse_scriptures(raw_text: str):
    sections = {}
    current_key = "INTRO"
    buffer = []
    
    for line in raw_text.split('\n'):
        line_clean = line.strip()
        if not line_clean:
            continue
        m = re.match(r'\[(시편|제1성서|제2성서|복음서)\]\s*(.*)', line_clean)
        if m:
            if buffer:
                sections[current_key] = '\n'.join(buffer).strip()
                buffer = []
            current_key = m.group(1)
            if m.group(2):
                buffer.append(m.group(2))
        else:
            buffer.append(line_clean)
            
    if buffer:
        sections[current_key] = '\n'.join(buffer).strip()
        
    return sections

def main():
    target_date = sys.argv[1] if len(sys.argv) > 1 else get_sunday_date()
    print(f"=== 향린교회 홈페이지 공식 성서읽기 수집 ({target_date}) ===")
    
    post_url = fetch_post_url(target_date)
    if not post_url:
        print(f"❌ 오류: 홈페이지에서 {target_date} 일자의 성서읽기 게시글을 찾을 수 없습니다.")
        sys.exit(1)
        
    print(f"🔗 공식 게시글 URL: {post_url}")
    raw_content = fetch_scripture_content(post_url)
    if not raw_content:
        print("❌ 오류: 본문 내용을 불러올 수 없습니다.")
        sys.exit(1)
        
    sections = parse_scriptures(raw_content)
    print("\n✅ 공식 등록 성서 본문 (새번역 2001 개정):")
    for sec, text in sections.items():
        print(f"\n[{sec}]")
        # Print first few lines
        lines = text.split('\n')
        for l in lines[:5]:
            print(f"  {l}")
        if len(lines) > 5:
            print(f"  ... (총 {len(lines)}행)")

if __name__ == "__main__":
    main()
