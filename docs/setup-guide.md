# 개발 환경 셋업 및 실행 가이드 (Setup Guide)

## 1. 요구 사항
- Python 3.9 이상
- (선택) Typst CLI (Typst PDF 엔진 사용 시)
- (선택) 한컴오피스 한글 (HWPX 파일 편집 및 인쇄 시)

## 2. 설치 방법

### 가상환경 생성 및 패키지 설치
```bash
# 가상환경 생성 및 활성화
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt
```

## 3. 주보 생성 실행

### A. CLI 명령어
```bash
# 샘플 데이터를 사용한 주보 생성 (HWPX + Typst PDF)
python3 src/main.py --data data/samples/sample_20260816.yaml --engine all --output output/
```

### B. 윈도우 원클릭 실행 (Windows Batch)
- `scripts/generate_bulletin.bat` 더블클릭

### C. 리눅스/macOS 셸 스크립트 실행
```bash
./scripts/generate_bulletin.sh
```

## 4. 테스트 실행
```bash
python3 -m unittest discover tests
# 또는 pytest 설치 시
pytest tests/ -v
```
