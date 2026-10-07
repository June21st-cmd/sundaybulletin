import os
import re
import struct
import olefile
import zlib
from pathlib import Path
import json
import sys

def get_hwp_text(filepath):
    try:
        f = olefile.OleFileIO(filepath)
    except Exception:
        return ""
    
    text = ""
    for stream in f.listdir():
        if stream[0] == 'BodyText' and stream[1].startswith('Section'):
            try:
                data = f.openstream(stream).read()
                decomp = zlib.decompress(data, -15)
            except Exception:
                continue
                
            i = 0
            while i + 4 <= len(decomp):
                header = struct.unpack('<I', decomp[i:i+4])[0]
                tag_id = header & 0x3FF
                size = (header >> 20) & 0xFFF
                i += 4
                if size == 0xFFF:
                    if i + 4 > len(decomp): break
                    size = struct.unpack('<I', decomp[i:i+4])[0]
                    i += 4
                
                if tag_id == 67: # HWPTAG_PARA_TEXT
                    rec = decomp[i:i+size]
                    j = 0
                    while j + 2 <= len(rec):
                        ch = struct.unpack('<H', rec[j:j+2])[0]
                        if ch >= 0x0020 and ch != 0x007F:
                            text += chr(ch)
                        elif ch == 0x000D or ch == 0x000A:
                            text += '\n'
                        j += 2
                    text += '\n'
                i += size
    return text

def extract_text(filepath):
    if filepath.endswith('.hwp'):
        return get_hwp_text(filepath)
    return ""

def find_latest_session_material(downloads_dir=None):
    if downloads_dir is None:
        downloads_dir = Path.home() / "Downloads"
    else:
        downloads_dir = Path(downloads_dir)
        
    candidates = []
    
    for root, _, files in os.walk(downloads_dir):
        for file in files:
            if "정기당회" in file and not any(x in file for x in ["임시당회", "제직회", "목회운영위원회", "목운위"]):
                if file.endswith((".hwp", ".hwpx", ".pdf")):
                    candidates.append(Path(root) / file)
                    
    if not candidates:
        return None
        
    def get_sort_key(filepath):
        name = filepath.name
        year_match = re.search(r'(20\d{2})', name)
        month_match = re.search(r'(\d+)월', name)
        
        year = int(year_match.group(1)) if year_match else 0
        month = int(month_match.group(1)) if month_match else 0
        
        return (year, month, filepath.stat().st_mtime)

    candidates.sort(key=get_sort_key, reverse=True)
    best = candidates[0]
    best_key = get_sort_key(best)
    
    if best_key[0] == 0:
        return {"error": "AMBIGUOUS_YEAR", "message": "최신 정기당회 자료 파일명에 연도가 표기되지 않아 임의 확정을 금지합니다."}
        
    return {
        "file_path": str(best),
        "file_name": best.name,
        "year": best_key[0],
        "month": best_key[1],
        "reason": f"파일명 '정기당회' 매칭 및 연/월 파싱 기반 최신성({best_key[0]}년 {best_key[1]}월) 확정",
        "text": extract_text(str(best))
    }

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding='utf-8')
    res = find_latest_session_material()
    if res is None:
        print(json.dumps({"error": "NOT_FOUND", "message": "정기당회 자료를 찾을 수 없습니다."}, ensure_ascii=False))
    else:
        print(json.dumps(res, ensure_ascii=False))
