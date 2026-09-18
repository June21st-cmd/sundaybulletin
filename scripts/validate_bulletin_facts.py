"""
향린교회 주보 팩트 및 임의 추정 원천 차단 검증기 (validate_bulletin_facts.py)

검증 영역:
1. 향린교회 정례 모임 골든 기준표(Golden DB) 대조
   - 목회운영위원회: 통상 16:00, 친교실(5층)
   - 교육부 월례회: 통상 12:40, 세미나실(4층)
   - 전체여신도회 임원모임: 통상 13:00, 담임목사실(4층)
2. 인접 항목 복붙 오염(Leaked Value) 감지
   - 윗줄 항목의 시간/장소와 완전히 동일한 값이 아랫줄에 연달아 나타날 때 경고
3. 원고 출처 격리 감사 (Source Leaking Audit)
   - 사용자가 제공한 원고 파일에 없는 모임/행사가 임의로 끼어들어갔는지 대조
"""

import re
import sys
import yaml
from pathlib import Path

# 향린교회 주요 정례 모임 표준 기준표 (2026 골든 레퍼런스 기준)
GOLDEN_MEETING_RULES = {
    "목회운영위원회": {
        "expected_time": "16:00",
        "expected_place": "친교실(5층)",
        "warning": "목회운영위원회는 2026년 기준 통상 16:00, 친교실(5층)에서 열립니다."
    },
    "정기 목회운영위원회": {
        "expected_time": "16:00",
        "expected_place": "친교실(5층)",
        "warning": "정기 목회운영위원회는 2026년 기준 통상 16:00, 친교실(5층)에서 열립니다."
    },
    "교육부 월례회": {
        "expected_time": "12:40",
        "expected_place": "세미나실(4층)",
        "warning": "교육부 월례회는 통상 12:40, 세미나실(4층)에서 열립니다."
    },
    "전체여신도회 임원 모임": {
        "expected_time": "13:00",
        "expected_place": "담임목사실(4층)",
        "warning": "전체여신도회 임원 모임은 통상 13:00, 담임목사실(4층)에서 열립니다."
    },
    "전체여신도회 임원모임": {
        "expected_time": "13:00",
        "expected_place": "담임목사실(4층)",
        "warning": "전체여신도회 임원 모임은 통상 13:00, 담임목사실(4층)에서 열립니다."
    }
}

def validate_facts(bulletin_yaml_path, raw_input_path=None):
    issues = []
    
    yaml_file = Path(bulletin_yaml_path)
    if not yaml_file.exists():
        return [f"❌ YAML 파일을 찾을 수 없습니다: {bulletin_yaml_path}"]
        
    with open(yaml_file, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
        
    raw_text = ""
    if raw_input_path and Path(raw_input_path).exists():
        with open(raw_input_path, "r", encoding="utf-8") as f:
            raw_text = f.read()

    # 1. announcements_sections 순회 검증
    sections = data.get("announcements_sections", [])
    all_items = []
    
    for sec in sections:
        sec_title = sec.get("title", "")
        items = sec.get("items", [])
        prev_time = None
        prev_place = None
        prev_title = None
        
        for item in items:
            if isinstance(item, dict):
                title = item.get("title", "").strip()
                content = item.get("content", "").strip()
            elif isinstance(item, str):
                title = ""
                content = item.strip()
            else:
                continue
            all_items.append((sec_title, title, content))
            
            # [A] 골든 미팅 기준표 검증
            for meeting_key, rule in GOLDEN_MEETING_RULES.items():
                if meeting_key in title:
                    exp_time = rule["expected_time"]
                    exp_place = rule["expected_place"]
                    
                    if exp_time not in content:
                        issues.append({
                            "level": "ERROR",
                            "category": "정례 모임 시간 불일치",
                            "section": sec_title,
                            "item": title,
                            "content": content,
                            "message": f"'{title}'의 시간이 표준({exp_time})과 다릅니다! {rule['warning']}"
                        })
                    if exp_place not in content:
                        issues.append({
                            "level": "WARNING",
                            "category": "정례 모임 장소 누락/불일치",
                            "section": sec_title,
                            "item": title,
                            "content": content,
                            "message": f"'{title}'에 표준 장소({exp_place})가 명시되지 않았거나 다릅니다."
                        })

            # [B] 인접 항목 복붙 오염 검증
            # 시간 추출 (HH:MM)
            time_match = re.search(r'\b\d{1,2}:\d{2}\b', content)
            curr_time = time_match.group(0) if time_match else None
            
            # 장소 추출 (...층, ...실)
            place_match = re.search(r'([가-힣]+실\([0-9]+층\)|\([0-9]+층\))', content)
            curr_place = place_match.group(0) if place_match else None
            
            if prev_time and curr_time and prev_time == curr_time and prev_title:
                # 같은 시간에 연속된 회의가 열리는지 확인 경고
                issues.append({
                    "level": "INFO",
                    "category": "인접 항목 동일 시간 감지 (복붙 확인 요망)",
                    "section": sec_title,
                    "item": title,
                    "content": content,
                    "message": f"윗 항목('{prev_title}')과 시간이 동일하게 '{curr_time}'입니다. 단순 복사 실수가 아닌지 확인하세요."
                })
                
            prev_time = curr_time
            prev_place = curr_place
            prev_title = title

            # [C] 원고 텍스트 대비 임의 추가(환각) 감사
            if raw_text and title:
                # 간단한 키워드 검사 (2글자 이상 핵심 명사)
                clean_title = re.sub(r'[^가-힣a-zA-Z0-9]', '', title)
                # 중요한 모임명인데 원고에 전혀 언급이 없는 경우
                if len(clean_title) >= 3 and clean_title not in raw_text:
                    # 성서일과나 고정 광고는 제외
                    if not any(k in title for k in ["성서일과", "신학공부", "우리가락", "국악학교", "심방", "생활실천"]):
                        issues.append({
                            "level": "WARNING",
                            "category": "원고 미언급 항목 (외부자료 임의 추가 의심)",
                            "section": sec_title,
                            "item": title,
                            "content": content,
                            "message": f"'{title}'은(는) 사용자가 전달한 원고 텍스트에 없습니다. 외부 회의자료에서 임의로 추가된 것이 아닌지 반드시 확인하세요."
                        })

    return issues

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding='utf-8')
    yaml_path = sys.argv[1] if len(sys.argv) > 1 else "data/inputs/bulletin_20260920.yaml"
    raw_path = sys.argv[2] if len(sys.argv) > 2 else "data/inputs/2026-09-20_주보원고.md"
    
    print(f"=== 주보 팩트 및 임의 추정 검증 시작 ===")
    print(f"대상 파일: {yaml_path}")
    if raw_path:
        print(f"원고 파일: {raw_path}")
    print("-" * 50)
    
    results = validate_facts(yaml_path, raw_path)
    
    if not results:
        print("🟢 [검증 통과] 팩트 불일치나 임의 추정 항목이 발견되지 않았습니다.")
        sys.exit(0)
        
    error_cnt = sum(1 for r in results if r["level"] == "ERROR")
    warn_cnt = sum(1 for r in results if r["level"] == "WARNING")
    info_cnt = sum(1 for r in results if r["level"] == "INFO")
    
    print(f"발견된 문제: ERROR {error_cnt}건, WARNING {warn_cnt}건, INFO {info_cnt}건\n")
    
    for r in results:
        icon = "🔴" if r["level"] == "ERROR" else ("🟠" if r["level"] == "WARNING" else "ℹ️")
        print(f"{icon} [{r['level']}] [{r['category']}] {r['section']} > {r['item']}")
        print(f"   내용: {r['content']}")
        print(f"   지침: {r['message']}")
        print()
        
    if error_cnt > 0:
        sys.exit(1)
    sys.exit(0)
