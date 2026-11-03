import unittest
import os
import tempfile
import yaml
from pathlib import Path
import json

from scripts.fetch_session_material import find_latest_session_material
from src.main import run_preflight, is_same_file_path

class TestSourceCollection(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.downloads = Path(self.test_dir.name) / "Downloads"
        self.downloads.mkdir()
        
    def tearDown(self):
        self.test_dir.cleanup()
        
    def test_find_latest_session(self):
        # 1. 연/월이 명확한 정기당회 여러 개 -> 최신 1개 선택
        (self.downloads / "2026 7월 정기당회 회의록.hwp").touch()
        (self.downloads / "2026 9월 정기당회 회의록.pdf").touch()
        (self.downloads / "2025 12월 정기당회.hwp").touch()
        
        res = find_latest_session_material(self.downloads)
        self.assertIsNotNone(res)
        self.assertEqual(res["year"], 2026)
        self.assertEqual(res["month"], 9)
        self.assertIn("9월 정기당회", res["file_name"])

    def test_exclude_other_meetings(self):
        # 2. 임시당회/목회운영위원회 -> 후보 제외
        (self.downloads / "2026 9월 임시당회.hwp").touch()
        (self.downloads / "2026 9월 목회운영위원회.pdf").touch()
        (self.downloads / "2026 8월 제직회.hwp").touch()
        
        res = find_latest_session_material(self.downloads)
        self.assertIsNone(res)

    def test_ambiguous_year(self):
        # 3. 연도 없는 파일 -> 임의 선택 금지 (AMBIGUOUS_YEAR)
        (self.downloads / "9월 정기당회록.hwp").touch()
        
        res = find_latest_session_material(self.downloads)
        self.assertIsNotNone(res)
        self.assertEqual(res.get("error"), "AMBIGUOUS_YEAR")

    def test_manifest_missing(self):
        # 4. Manifest 없음 -> HWPX BLOCK
        yaml_path = self.downloads / "bulletin_20260920.yaml"
        yaml_path.touch()
        
        blocks, warns = run_preflight_sim(yaml_path)
        self.assertTrue(any("Source Manifest 누락" in b for b in blocks))

    def test_manifest_mismatch(self):
        # 5. Manifest가 오래된 정기당회 자료를 가리킴 -> BLOCK
        yaml_path = self.downloads / "bulletin_20260920.yaml"
        yaml_path.touch()
        manifest_path = self.downloads / "bulletin_20260920_manifest.yaml"
        manifest_data = {
            "source_manifest": {
                "session_material": {
                    "file_path": "old_file.hwp"
                }
            }
        }
        with open(manifest_path, 'w', encoding='utf-8') as f:
            yaml.dump(manifest_data, f)
            
        (self.downloads / "2026 9월 정기당회.hwp").touch()
        
        blocks, warns = run_preflight_sim(yaml_path, self.downloads)
        self.assertTrue(any("최신 정기당회 자료와 불일치" in b for b in blocks))

    def test_normal_manifest(self):
        # 6. 정상 Manifest -> 빌드 허용
        yaml_path = self.downloads / "bulletin_20260920.yaml"
        yaml_path.touch()
        manifest_path = self.downloads / "bulletin_20260920_manifest.yaml"
        
        latest_file = self.downloads / "2026 9월 정기당회.hwp"
        latest_file.touch()
        
        manifest_data = {
            "source_manifest": {
                "session_material": {
                    "file_path": str(latest_file)
                }
            }
        }
        with open(manifest_path, 'w', encoding='utf-8') as f:
            yaml.dump(manifest_data, f)
            
        blocks, warns = run_preflight_sim(yaml_path, self.downloads)
        self.assertFalse(any("Source Manifest 누락" in b for b in blocks))
        self.assertFalse(any("최신 정기당회 자료와 불일치" in b for b in blocks))

    def test_manifest_findings_warn(self):
        # 7. 당회 findings에 원고 미포함 일정 존재 -> WARN
        yaml_path = self.downloads / "bulletin_20260920.yaml"
        yaml_path.touch()
        manifest_path = self.downloads / "bulletin_20260920_manifest.yaml"
        
        latest_file = self.downloads / "2026 9월 정기당회.hwp"
        latest_file.touch()
        
        manifest_data = {
            "source_manifest": {
                "session_material": {
                    "file_path": str(latest_file),
                    "findings": [
                        {"item": "기후정의주일", "note": "9/20", "present_in_memo": False}
                    ]
                }
            }
        }
        with open(manifest_path, 'w', encoding='utf-8') as f:
            yaml.dump(manifest_data, f)
            
    def test_is_same_file_path(self):
        f1 = self.downloads / "test_file.hwp"
        f1.touch()
        str_bs = str(f1) # backslash on Windows
        str_fs = str(f1).replace("\\", "/") # forward slash
        self.assertTrue(is_same_file_path(str_bs, str_fs))
        self.assertTrue(is_same_file_path(str_fs, str_bs))
        
        # Non-existent matching paths
        p_bs = "C:\\dummy\\folder\\file.hwp"
        p_fs = "C:/dummy/folder/file.hwp"
        self.assertTrue(is_same_file_path(p_bs, p_fs))
        
        # Different paths
        p_diff = "C:/dummy/folder/other.hwp"
        self.assertFalse(is_same_file_path(p_bs, p_diff))

    def test_direct_run_preflight_mismatch_blocks(self):
        yaml_path = self.downloads / "bulletin_20260920.yaml"
        with open(yaml_path, 'w', encoding='utf-8') as f:
            yaml.dump({"metadata": {"date": "2026-09-20"}}, f)
        manifest_path = self.downloads / "bulletin_20260920_manifest.yaml"
        manifest_data = {
            "source_manifest": {
                "session_material": {
                    "file_path": str(self.downloads / "2026 7월 정기당회.hwp")
                }
            }
        }
        with open(manifest_path, 'w', encoding='utf-8') as f:
            yaml.dump(manifest_data, f)
            
        (self.downloads / "2026 9월 정기당회.hwp").touch()
        (self.downloads / "2026 7월 정기당회.hwp").touch()
        
        # run_preflight directly
        passed = run_preflight({}, yaml_path, downloads_dir=self.downloads)
        self.assertFalse(passed)

    def test_direct_run_preflight_slash_difference_passes(self):
        yaml_path = self.downloads / "bulletin_20260920.yaml"
        with open(yaml_path, 'w', encoding='utf-8') as f:
            yaml.dump({"metadata": {"date": "2026-09-20"}}, f)
        latest_file = self.downloads / "2026 9월 정기당회.hwp"
        latest_file.touch()
        
        # Manifest has forward slashes
        forward_slash_path = str(latest_file).replace("\\", "/")
        manifest_path = self.downloads / "bulletin_20260920_manifest.yaml"
        manifest_data = {
            "source_manifest": {
                "session_material": {
                    "file_path": forward_slash_path
                }
            }
        }
        with open(manifest_path, 'w', encoding='utf-8') as f:
            yaml.dump(manifest_data, f)
            
        passed = run_preflight({}, yaml_path, downloads_dir=self.downloads)
        self.assertTrue(passed)

    def test_hallucinated_scripture_blocks_build(self):
        """Rule 0: Test that hallucinated/arbitrary scripture is strictly blocked with ValueError."""
        from src.hwpx_engine import HwpxEngine
        fake_data = {
            "metadata": {"date_compact": "20261018"},
            "worship_1": {
                "responsive_scripture_1": "듣도 보아도 반가운 내 님의 목소리, 노루처럼 산을 훌쩍 뛰넘고 사슴처럼 언덕을 단숨에 넘어 그가 달려오십니다.",
                "responsive_scripture_2": "내 사랑하는 님은 노루 같기도 하고 사슴 같기도 합니다.",
                "responsive_scripture_3": "내 사랑하는 이가 나를 향하여 말합니다."
            }
        }
        engine = HwpxEngine("templates/hwpx/template.hwpx")
        with self.assertRaises(ValueError) as ctx:
            engine._verify_official_scripture(fake_data)
        self.assertIn("[CRITICAL BLOCKER]", str(ctx.exception))

    def test_official_scripture_passes_verification(self):
        """Rule 0: Test that official homepage scripture passes verification."""
        from src.hwpx_engine import HwpxEngine
        official_data = {
            "metadata": {"date_compact": "20261018"},
            "worship_1": {
                "responsive_scripture_1": "아, 사랑하는 임의 목소리! 저기 오는구나. 산을 넘고 언덕을 넘어서 달려오는구나.",
                "responsive_scripture_2": "사랑하는 나의 임은 노루처럼, 어린 사슴처럼 빠르구나. 벌써 우리 집 담 밖에 서서 창 틈으로 기웃거리며, 창살 틈으로 엿보는구나.",
                "responsive_scripture_3": "아, 사랑하는 이가 나에게 속삭이네. 나의 사랑 그대, 일어나오. 나의 어여쁜 그대, 어서 나오오."
            }
        }
        engine = HwpxEngine("templates/hwpx/template.hwpx")
        # Should not raise ValueError
        engine._verify_official_scripture(official_data)

def run_preflight_sim(yaml_path, downloads_dir=None):
    # This simulates the main.py check so we don't have to patch main.py multiple times for tests
    blocks = []
    warns = []
    m_name = yaml_path.stem + "_manifest.yaml"
    manifest_path = yaml_path.parent / m_name
    
    if not manifest_path.exists():
        blocks.append(f"[Source Manifest 누락] {m_name}")
    else:
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest_data = yaml.safe_load(f)
            session = manifest_data.get("source_manifest", {}).get("session_material", {})
            file_path = session.get("file_path")
            
            if downloads_dir:
                res = find_latest_session_material(downloads_dir)
                if res and "error" not in res:
                    latest_path = res["file_path"]
                    if file_path != latest_path:
                        blocks.append(f"[Source Manifest 불일치] 최신 정기당회 자료와 불일치합니다. 기대:{latest_path}, 실제:{file_path}")
            
            findings = session.get("findings", [])
            for f_item in findings:
                if not f_item.get("present_in_memo", True):
                    warns.append(f"[특별일정 미기재] {f_item.get('item')}")
                    
    return blocks, warns


class TestAnnouncementClassificationAndPreflight(unittest.TestCase):
    """2단계 회귀 테스트: 소식 분류 검증(날짜 경계·성격 우선 범주·에큐메니칼 누락/포괄 예외·6/7대 구조 및 legacy 차단)."""

    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.tmp = Path(self.test_dir.name)
        self.downloads = self.tmp / "Downloads"
        self.downloads.mkdir()
        self.latest_session = self.downloads / "2026 11월 정기당회.hwp"
        self.latest_session.touch()

    def tearDown(self):
        self.test_dir.cleanup()

    def _make_6tier(self, overrides=None):
        overrides = overrides or {}
        titles = [
            "1. 오늘 일정 안내",
            "2. 함께 만드는 향린",
            "3. 이번주 일정 안내",
            "4. 이후 일정 안내",
            "5. 에큐메니칼 소식",
            "6. 감사헌금",
        ]
        return [{"title": t, "items": list(overrides.get(t, []))} for t in titles]

    def _make_7tier(self, overrides=None):
        overrides = overrides or {}
        titles = [
            "1. 오늘 일정 안내",
            "2. 교우 소식",
            "3. 함께 만드는 향린",
            "4. 이번주 일정 안내",
            "5. 이후 일정 안내",
            "6. 에큐메니칼 소식",
            "7. 감사헌금",
        ]
        return [{"title": t, "items": list(overrides.get(t, []))} for t in titles]

    @staticmethod
    def _extract_preflight_blocks(stdout_text: str) -> list[str]:
        if "❌ [Pre-flight 차단]" not in stdout_text:
            return []
        after = stdout_text.split("❌ [Pre-flight 차단]", 1)[1]
        blocks = []
        for line in after.splitlines():
            stripped = line.strip()
            if stripped.startswith("- "):
                blocks.append(stripped[2:].strip())
        return blocks

    def _run_case(self, date_compact: str, payload_extra: dict):
        import contextlib
        import io
        from scripts.validate_bulletin_facts import validate_facts

        data = {
            "metadata": {"date_compact": date_compact},
            "worship_1": {"choir_song_title": "가상찬양", "scripture": "창세기 1:1 (1쪽)"},
        }
        data.update(payload_extra)

        yaml_path = self.tmp / f"bulletin_{date_compact}.yaml"
        manifest_path = self.tmp / f"bulletin_{date_compact}_manifest.yaml"
        yaml_path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
        manifest_data = {
            "source_manifest": {
                "session_material": {"file_path": str(self.latest_session)}
            }
        }
        manifest_path.write_text(yaml.safe_dump(manifest_data, allow_unicode=True), encoding="utf-8")

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            passed = run_preflight(data, yaml_path, downloads_dir=self.downloads)
        facts = validate_facts(str(yaml_path))
        return passed, facts, buf.getvalue()

    def _assert_misplacement_blocked_and_reversible(
        self,
        date_compact: str,
        bad_sections: list[dict],
        valid_sections: list[dict],
        expected_category: str,
    ):
        from src.parser import validate_announcements_sections

        # 1. 오배치 입력 자체가 정상 6대/7대 구조를 갖추고 있음을 검증
        self.assertTrue(validate_announcements_sections(bad_sections))

        # 2. 오배치 시 BLOCK되며, 구조 오류나 무관한 ERROR 없이 의도한 category만 발생했음을 검증
        passed_bad, facts_bad, out_bad = self._run_case(
            date_compact, {"announcements_sections": bad_sections}
        )
        self.assertFalse(passed_bad)
        err_facts = [f for f in facts_bad if f["level"] == "ERROR"]
        self.assertTrue(len(err_facts) >= 1)
        self.assertEqual({f["category"] for f in err_facts}, {expected_category})

        blocks = self._extract_preflight_blocks(out_bad)
        self.assertTrue(len(blocks) >= 1)
        self.assertTrue(
            all(b.startswith(f"[{expected_category}]") for b in blocks),
            msg=f"Unexpected block lines: {blocks}",
        )

        # 3. 동일 항목을 정상 섹션으로 옮기면 PASS함을 검증
        self.assertTrue(validate_announcements_sections(valid_sections))
        passed_ok, facts_ok, _ = self._run_case(
            date_compact, {"announcements_sections": valid_sections}
        )
        self.assertTrue(passed_ok)
        self.assertEqual([f for f in facts_ok if f["level"] == "ERROR"], [])

    def test_valid_6tier_and_7tier_and_empty_future_header_pass_preflight(self):
        from src.parser import validate_announcements_sections

        # 6단 정상 배치 + 빈 '4. 이후 일정 안내' 헤더 유지 + 당일 에큐메니칼 행사
        secs_6 = self._make_6tier({
            "1. 오늘 일정 안내": [{"title": "가상당일모임", "content": "11/15(일) 13:00 친교실(5층)"}],
            "2. 함께 만드는 향린": [{"title": "가상상시모집", "content": "상시 신청 안내"}],
            "3. 이번주 일정 안내": [
                {"title": "가상월요모임", "content": "11/16(월) 19:00"},
                {"title": "가상차주주일모임", "content": "11/22(일) 13:00"},
            ],
            "4. 이후 일정 안내": [],
            "5. 에큐메니칼 소식": [{"title": "NCCK 가상기도회", "content": "11/15(일) 15:00"}],
            "6. 감사헌금": ["가상교우1 가상교우2"],
        })
        self.assertTrue(validate_announcements_sections(secs_6))
        passed_6, facts_6, _ = self._run_case("20261115", {"announcements_sections": secs_6})
        self.assertTrue(passed_6)
        self.assertEqual([f for f in facts_6 if f["level"] == "ERROR"], [])

        # 7단 정상 배치 ('2. 교우 소식' 삽입, 번호 3~7 순차 밀림, 빈 '5. 이후 일정 안내' 유지)
        secs_7 = self._make_7tier({
            "1. 오늘 일정 안내": [{"title": "가상당일모임", "content": "오늘 공동식사 후"}],
            "2. 교우 소식": [{"title": "가상경조사", "content": "11/21(토) 가상안내"}],
            "4. 이번주 일정 안내": [{"title": "가상차주모임", "content": "11/22(일) 13:00"}],
            "5. 이후 일정 안내": [],
            "6. 에큐메니칼 소식": [{"title": "촛불교회 가상연대예배", "content": "11/30(월) 19:00"}],
        })
        self.assertTrue(validate_announcements_sections(secs_7))
        passed_7, facts_7, _ = self._run_case("20261115", {"announcements_sections": secs_7})
        self.assertTrue(passed_7)
        self.assertEqual([f for f in facts_7 if f["level"] == "ERROR"], [])

    def test_date_boundaries_block_in_preflight(self):
        cat = "주간 일정 분류 오류 (Rule 22)"

        # 1. 다음 주일(D+7: 11/22) 내부행사 -> '4. 이후 일정 안내' 오배치 시 BLOCK / '3. 이번주 일정 안내' 배치 시 PASS
        item_next_sun = [{"title": "가상내부행사", "content": "11/22(일) 13:00"}]
        self._assert_misplacement_blocked_and_reversible(
            "20261115",
            self._make_6tier({"4. 이후 일정 안내": item_next_sun}),
            self._make_6tier({"3. 이번주 일정 안내": item_next_sun}),
            cat,
        )

        # 2. D+8(11/23 월) 내부행사 -> '3. 이번주 일정 안내' 오배치 시 BLOCK / '4. 이후 일정 안내' 배치 시 PASS
        item_d_plus_8 = [{"title": "가상내부행사", "content": "11/23(월) 19:00"}]
        self._assert_misplacement_blocked_and_reversible(
            "20261115",
            self._make_6tier({"3. 이번주 일정 안내": item_d_plus_8}),
            self._make_6tier({"4. 이후 일정 안내": item_d_plus_8}),
            cat,
        )

        # 3. 먼 미래(11/30 월) 내부행사 -> '3. 이번주 일정 안내' 오배치 시 BLOCK / '4. 이후 일정 안내' 배치 시 PASS
        item_far_future = [{"title": "가상내부행사", "content": "11/30(월) 13:00"}]
        self._assert_misplacement_blocked_and_reversible(
            "20261115",
            self._make_6tier({"3. 이번주 일정 안내": item_far_future}),
            self._make_6tier({"4. 이후 일정 안내": item_far_future}),
            cat,
        )

        # 4. 당일(D: 11/15) 내부행사 -> '3. 이번주 일정 안내' 오배치 시 BLOCK / '1. 오늘 일정 안내' 배치 시 PASS
        item_today = [{"title": "가상당일내부행사", "content": "11/15(일) 13:00"}]
        self._assert_misplacement_blocked_and_reversible(
            "20261115",
            self._make_6tier({"3. 이번주 일정 안내": item_today}),
            self._make_6tier({"1. 오늘 일정 안내": item_today}),
            cat,
        )

        # 5. 주간(D+7: 11/22) 내부행사 -> '1. 오늘 일정 안내' 오배치 시 BLOCK / '3. 이번주 일정 안내' 배치 시 PASS
        item_next_sun_2 = [{"title": "가상차주내부행사", "content": "11/22(일) 13:00"}]
        self._assert_misplacement_blocked_and_reversible(
            "20261115",
            self._make_6tier({"1. 오늘 일정 안내": item_next_sun_2}),
            self._make_6tier({"3. 이번주 일정 안내": item_next_sun_2}),
            cat,
        )

    def test_month_end_and_year_end_boundaries_in_preflight(self):
        cat = "주간 일정 분류 오류 (Rule 22)"

        # 월말 경계: D = 2026-11-29(일) -> 이번주: 11/30(월)~12/6(일), 이후: 12/7(월)~
        month_end_valid = self._make_6tier({
            "1. 오늘 일정 안내": [{"title": "가상당일모임", "content": "11/29(일) 13:00"}],
            "3. 이번주 일정 안내": [
                {"title": "가상월말모임", "content": "11/30(월) 19:00"},
                {"title": "가상월초주일모임", "content": "12/6(일) 13:00"},
            ],
            "4. 이후 일정 안내": [{"title": "가상이후모임", "content": "12/7(월) 19:00"}],
        })
        passed_m_ok, facts_m_ok, _ = self._run_case("20261129", {"announcements_sections": month_end_valid})
        self.assertTrue(passed_m_ok)
        self.assertEqual([f for f in facts_m_ok if f["level"] == "ERROR"], [])

        item_dec6 = [{"title": "가상월초주일모임", "content": "12/6(일) 13:00"}]
        self._assert_misplacement_blocked_and_reversible(
            "20261129",
            self._make_6tier({"4. 이후 일정 안내": item_dec6}),
            self._make_6tier({"3. 이번주 일정 안내": item_dec6}),
            cat,
        )

        item_dec7 = [{"title": "가상이후모임", "content": "12/7(월) 19:00"}]
        self._assert_misplacement_blocked_and_reversible(
            "20261129",
            self._make_6tier({"3. 이번주 일정 안내": item_dec7}),
            self._make_6tier({"4. 이후 일정 안내": item_dec7}),
            cat,
        )

        # 연말 경계: D = 2026-12-27(일) -> 이번주: 12/28(월)~1/3(일), 이후: 1/4(월)~
        year_end_valid = self._make_6tier({
            "1. 오늘 일정 안내": [{"title": "가상연말당일모임", "content": "12/27(일) 13:00"}],
            "3. 이번주 일정 안내": [
                {"title": "가상연말모임", "content": "12/28(월) 19:00"},
                {"title": "가상신년주일모임", "content": "1/3(일) 13:00"},
            ],
            "4. 이후 일정 안내": [{"title": "가상신년이후모임", "content": "1/4(월) 19:00"}],
        })
        passed_y_ok, facts_y_ok, _ = self._run_case("20261227", {"announcements_sections": year_end_valid})
        self.assertTrue(passed_y_ok)
        self.assertEqual([f for f in facts_y_ok if f["level"] == "ERROR"], [])

        item_jan3 = [{"title": "가상신년주일모임", "content": "1/3(일) 13:00"}]
        self._assert_misplacement_blocked_and_reversible(
            "20261227",
            self._make_6tier({"4. 이후 일정 안내": item_jan3}),
            self._make_6tier({"3. 이번주 일정 안내": item_jan3}),
            cat,
        )

        item_jan4 = [{"title": "가상신년이후모임", "content": "1/4(월) 19:00"}]
        self._assert_misplacement_blocked_and_reversible(
            "20261227",
            self._make_6tier({"3. 이번주 일정 안내": item_jan4}),
            self._make_6tier({"4. 이후 일정 안내": item_jan4}),
            cat,
        )

    def test_past_year_context_not_resolved_to_current_year(self):
        """발행일 2026-11-15 기준 '작년 11/18(화)'를 2026-11-18로 확정하거나 오판 차단하면 안 됨."""
        from src.reviewer.rules import BulletinRuleChecker
        from src.reviewer.models import IssueLevel

        # 1. '1. 오늘 일정 안내' 및 '4. 이후 일정 안내'에 '작년 11/18(화)' 언급이 있어도 2026-11-18(이번주)로 오판해 BLOCK하지 않음
        secs_ref = self._make_6tier({
            "1. 오늘 일정 안내": [{"title": "가상당일모임", "content": "공동식사 후 (작년 11/18(화) 간담회 기록 참고)"}],
            "4. 이후 일정 안내": [{"title": "가상후속모임", "content": "11/29(일) 13:00 (작년 11/18(화) 결의 후속)"}],
        })
        passed, facts, _ = self._run_case("20261115", {"announcements_sections": secs_ref})
        self.assertTrue(passed)
        self.assertEqual([f for f in facts if f["level"] == "ERROR"], [])
        self.assertFalse(any("2026-11-18" in f.get("message", "") for f in facts))

        checker_issues = BulletinRuleChecker(
            {"metadata": {"date_compact": "20261115"}, "announcements_sections": secs_ref}
        ).check_date_weekdays()
        self.assertEqual([i for i in checker_issues if i.level == IssueLevel.ERROR], [])

        # 2. '3. 이번주 일정 안내'에 현재 일정 없이 '작년 11/18(화)'만 적힌 경우 2026-11-18 정상 주간 일정으로 확정하지 않고 확인 필요(WARNING)로 표시
        secs_only_past = self._make_6tier({
            "3. 이번주 일정 안내": [{"title": "가상간담회 자료", "content": "작년 11/18(화) 자료집 확인"}],
        })
        passed_past, facts_past, _ = self._run_case("20261115", {"announcements_sections": secs_only_past})
        self.assertTrue(passed_past)
        self.assertEqual([f for f in facts_past if f["level"] == "ERROR"], [])
        self.assertTrue(
            any(f["level"] == "WARNING" and "확인" in f["category"] for f in facts_past),
            msg=f"Expected confirmation WARNING for past-year-only item, got: {facts_past}",
        )

    def test_cost_ratio_expressions_vs_unclear_slash_tokens(self):
        """발행일 2026-11-15 기준 '참가비 5/6 지원' 등 비용·비율 표현을 행사 날짜(2027-05-06)로 추출하면 안 되며, 근거 부족 슬래시 표현은 확인 대상으로 남김."""
        # 1. 다양한 비용·비율·정족수 표현은 행사 날짜로 추출되지 않고 경고/차단 없이 통과
        secs_cost = self._make_6tier({
            "3. 이번주 일정 안내": [
                {"title": "가상수련회 회비 안내", "content": "참가비 5/6 지원"},
                {"title": "가상교육 등록 안내", "content": "수강료 4/5 감면, 회비의 3/5 보조"},
                {"title": "가상회의 의결 안내", "content": "재적 2/3 이상 출석"},
            ],
        })
        passed_cost, facts_cost, _ = self._run_case("20261115", {"announcements_sections": secs_cost})
        self.assertTrue(passed_cost)
        self.assertEqual([f for f in facts_cost if f["level"] == "ERROR"], [])
        self.assertEqual(
            [f for f in facts_cost if f["level"] == "WARNING" and "날짜" in f["category"]],
            [],
        )

        # 2. 비용·비율 표현도 아니고 요일·시간·일시 근거도 부족한 단독 슬래시('5/6 별도 안내')는 2027-05-06으로 차단하지 않고 확인 대상(WARNING)으로 표시
        secs_unclear = self._make_6tier({
            "3. 이번주 일정 안내": [
                {"title": "가상별도안내", "content": "5/6 별도 안내"},
            ],
        })
        passed_unc, facts_unc, _ = self._run_case("20261115", {"announcements_sections": secs_unclear})
        self.assertTrue(passed_unc)
        self.assertEqual([f for f in facts_unc if f["level"] == "ERROR"], [])
        self.assertFalse(any("2027-05-06" in f.get("message", "") for f in facts_unc))
        self.assertTrue(
            any(f["level"] == "WARNING" and "일정 날짜 확인 요망" in f["category"] for f in facts_unc),
            msg=f"Expected confirmation WARNING for unclear slash token, got: {facts_unc}",
        )

    def test_unconfirmed_year_consistent_across_validators_and_iso_date_supported(self):
        """연도를 확정할 수 없는 날짜에 대해 분류 검사와 요일 검토기가 동일하게 추측 차단을 보류하고 확인 필요로 표시하며, 명시적 ISO date 지정 시 확정 검사함."""
        from src.reviewer.rules import BulletinRuleChecker
        from src.reviewer.models import IssueLevel

        # 1. 발행일 2026-11-15 기준 연도 미표기 '9/2(화)', '2/10(화)' -> 두 검사기 모두 임의 연도 확정 ERROR 없이 WARNING 확인 요청
        secs_unconfirmed = self._make_6tier({
            "4. 이후 일정 안내": [
                {"title": "가상모임A", "content": "9/2(화) 모임 참고"},
                {"title": "가상모임B", "content": "2/10(화) 10:00 예정"},
            ],
        })
        passed_u, facts_u, out_u = self._run_case("20261115", {"announcements_sections": secs_unconfirmed})
        self.assertTrue(passed_u, msg=f"Should not block on unconfirmed year, output:\n{out_u}")
        self.assertEqual([f for f in facts_u if f["level"] == "ERROR"], [])
        self.assertTrue(any(f["level"] == "WARNING" and "일정 날짜 확인 요망" in f["category"] for f in facts_u))

        weekday_issues = BulletinRuleChecker(
            {"metadata": {"date_compact": "20261115"}, "announcements_sections": secs_unconfirmed}
        ).check_date_weekdays()
        self.assertEqual([i for i in weekday_issues if i.level == IssueLevel.ERROR], [])
        self.assertTrue(any(i.level == IssueLevel.WARNING for i in weekday_issues))

        # 2. 항목에 명시적 ISO date('2027-02-10')를 제공하면 확정 날짜로 검증(정상 배치 PASS / 오배치 BLOCK)
        iso_item = [{"title": "가상신년수련회", "date": "2027-02-10", "content": "2/10(수) 10:00"}]
        self._assert_misplacement_blocked_and_reversible(
            "20261115",
            self._make_6tier({"3. 이번주 일정 안내": iso_item}),
            self._make_6tier({"4. 이후 일정 안내": iso_item}),
            "주간 일정 분류 오류 (Rule 22)",
        )

    def test_ambiguous_dates_and_nature_priority_categories_not_guessed_or_blocked(self):
        secs = self._make_6tier({
            "1. 오늘 일정 안내": [{"title": "가상정기모임", "content": "공동식사 후, 친교실(5층)"}],
            "2. 함께 만드는 향린": [{"title": "가상상시활동", "content": "11/30(월)까지 상시 참여"}],
            "3. 이번주 일정 안내": [
                {"title": "가상주간기도회", "content": "매주 목요일 19:00"},
                {"title": "가상회비안내", "content": "참가비 1/2 지원"},
            ],
            "4. 이후 일정 안내": [{"title": "가상연말일정", "content": "12월 중 추후 공지"}],
            "5. 에큐메니칼 소식": [
                {"title": "NCCK 가상당일행사", "content": "11/15(일) 15:00"},
                {"title": "종로시찰 가상차주모임", "content": "11/22(일) 16:00"},
            ],
        })
        passed, facts, _ = self._run_case("20261115", {"announcements_sections": secs})
        self.assertTrue(passed)
        self.assertEqual([f for f in facts if f["level"] == "ERROR"], [])

    def test_ecumenical_misplacement_gaps_and_blanket_exemptions(self):
        ecu_cat = "에큐메니칼 소식 오분류 (Rule 22)"

        # 1. 교우 소식(7단)에 외부 행사 오배치 -> BLOCK / 6. 에큐메니칼 소식 배치 시 PASS
        item_ecu_1 = [{"title": "NCCK 가상행사", "content": "가상내용"}]
        self._assert_misplacement_blocked_and_reversible(
            "20261115",
            self._make_7tier({"2. 교우 소식": item_ecu_1}),
            self._make_7tier({"6. 에큐메니칼 소식": item_ecu_1}),
            ecu_cat,
        )

        # 2. 감사헌금에 외부 행사 오배치 -> BLOCK / 5. 에큐메니칼 소식 배치 시 PASS
        item_ecu_2 = [{"title": "NCCK 가상행사", "content": "가상내용"}]
        self._assert_misplacement_blocked_and_reversible(
            "20261115",
            self._make_6tier({"6. 감사헌금": item_ecu_2}),
            self._make_6tier({"5. 에큐메니칼 소식": item_ecu_2}),
            ecu_cat,
        )

        # 3. 본문에 '주관'이 포함된 외부 행사('NCCK 주관') 포괄 면제 금지 -> BLOCK / 5. 에큐메니칼 소식 배치 시 PASS
        item_ecu_3 = [{"title": "가상행사", "content": "NCCK 주관 가상내용"}]
        self._assert_misplacement_blocked_and_reversible(
            "20261115",
            self._make_6tier({"1. 오늘 일정 안내": item_ecu_3}),
            self._make_6tier({"5. 에큐메니칼 소식": item_ecu_3}),
            ecu_cat,
        )

        # 4. 제목에 '신도회'가 포함된 외부 행사 포괄 면제 금지 -> BLOCK / 5. 에큐메니칼 소식 배치 시 PASS
        item_ecu_4 = [{"title": "가상신도회 행사", "content": "NCCK 가상내용"}]
        self._assert_misplacement_blocked_and_reversible(
            "20261115",
            self._make_6tier({"1. 오늘 일정 안내": item_ecu_4}),
            self._make_6tier({"5. 에큐메니칼 소식": item_ecu_4}),
            ecu_cat,
        )

        # 5. 내부 주체 주관과 외부 장소/연대 언급이 혼재해 성격이 모호한 경우 -> 자동 이동/단정 차단 대신 WARNING 확인 대상 표시
        ambiguous_case = self._make_6tier({
            "3. 이번주 일정 안내": [
                {"title": "가상부서 간담회", "content": "11/18(수) 19:00, 향린교회 사회부 주관, 장소: NCCK 회관"}
            ],
        })
        passed_amb, facts_amb, out_amb = self._run_case("20261115", {"announcements_sections": ambiguous_case})
        self.assertTrue(passed_amb)
        self.assertEqual([f for f in facts_amb if f["level"] == "ERROR"], [])
        self.assertTrue(any(f["level"] == "WARNING" and "에큐메니칼" in f["category"] for f in facts_amb))
        self.assertIn("확인", out_amb)

    def test_structure_violations_and_legacy_announcements_blocked_in_preflight(self):
        # 1. 빈 '이후 일정 안내' 헤더 생략 -> 구조 위반으로 BLOCK
        missing_future = [s for s in self._make_6tier() if "이후 일정" not in s["title"]]
        passed1, facts1, _ = self._run_case("20261115", {"announcements_sections": missing_future})
        self.assertFalse(passed1)
        self.assertEqual(
            {f["category"] for f in facts1 if f["level"] == "ERROR"},
            {"공동관심사 소주제 구조 위반 (Rule 22)"},
        )

        # 2. 임의 섹션명 -> 구조 위반으로 BLOCK
        arbitrary_sec = [{"title": "1. 임의범주", "items": [{"title": "가상행사", "content": "내용"}]}]
        passed2, facts2, _ = self._run_case("20261115", {"announcements_sections": arbitrary_sec})
        self.assertFalse(passed2)
        self.assertEqual(
            {f["category"] for f in facts2 if f["level"] == "ERROR"},
            {"공동관심사 소주제 구조 위반 (Rule 22)"},
        )

        # 3. legacy announcements 입력이 검사 없이 통과하지 않음 -> 레거시 구조 오류 + 내부 외부행사 오분류 모두 검출
        passed_leg, facts_leg, _ = self._run_case(
            "20261115",
            {"announcements": [{"title": "NCCK 가상행사", "content": "오늘 행사"}]},
        )
        self.assertFalse(passed_leg)
        self.assertEqual(
            {f["category"] for f in facts_leg if f["level"] == "ERROR"},
            {"지원되지 않는 레거시 소식 구조 (Rule 22)", "에큐메니칼 소식 오분류 (Rule 22)"},
        )

    def test_cli_main_aborts_before_generation_on_misclassified_schedule(self):
        """실제 src.main.main() CLI 경로에서 다음 주일(D+7) 오배치 시 날짜 분류 오류로 SystemExit(1) 중단되고 산출물이 생성되지 않아야 함."""
        import contextlib
        import io
        import sys
        import zipfile
        from unittest.mock import patch
        from src.main import main as cli_main
        from src.parser import validate_announcements_sections

        from tests.test_hwpx_engine import TestHwpxEngine
        mock_hwpx = TestHwpxEngine._write_synthetic_hwpx_fixture(self.tmp / "mock_cli_template.hwpx")

        item_next_sun = [{"title": "가상차주내부행사", "content": "11/22(일) 13:00"}]
        bad_sections = self._make_6tier({"4. 이후 일정 안내": item_next_sun})
        self.assertTrue(validate_announcements_sections(bad_sections))

        bad_data = {
            "metadata": {"date_compact": "20261115", "season": "창조절"},
            "worship_1": {"choir_song_title": "가상찬양", "scripture": "창세기 1:1 (1쪽)", "sermon_title": "가상설교"},
            "announcements_sections": bad_sections,
        }
        yaml_path = self.tmp / "bulletin_20261115.yaml"
        manifest_path = self.tmp / "bulletin_20261115_manifest.yaml"
        out_dir = self.tmp / "cli_out"
        yaml_path.write_text(yaml.safe_dump(bad_data, allow_unicode=True), encoding="utf-8")
        manifest_path.write_text(
            yaml.safe_dump({"source_manifest": {"session_material": {"file_path": str(self.latest_session)}}}, allow_unicode=True),
            encoding="utf-8",
        )

        cli_argv = [
            "main",
            "--data",
            str(yaml_path),
            "--engine",
            "hwpx",
            "--hwpx-template",
            str(mock_hwpx),
            "--output",
            str(out_dir),
        ]

        stdout_buf = io.StringIO()
        with contextlib.redirect_stdout(stdout_buf), patch(
            "src.main.find_latest_session_material", return_value={"file_path": str(self.latest_session)}
        ), patch.object(sys, "argv", cli_argv):
            with self.assertRaises(SystemExit) as ctx:
                cli_main()
            self.assertEqual(ctx.exception.code, 1)

        self.assertEqual(list(out_dir.glob("*.hwpx")), [])
        cli_out = stdout_buf.getvalue()
        blocks = self._extract_preflight_blocks(cli_out)
        self.assertEqual(len(blocks), 1, msg=f"Expected single date classification block, got: {blocks}\n{cli_out}")
        self.assertTrue(blocks[0].startswith("[주간 일정 분류 오류 (Rule 22)]"), msg=blocks[0])
        self.assertIn("2026-11-22", blocks[0])
        self.assertIn("이번주 일정 안내(D+1~D+7)", blocks[0])

        # 동일 입력에서 해당 항목만 '3. 이번주 일정 안내'로 정상 배치하면 CLI가 통과하고 .hwpx가 실제 생성됨을 대조 검증
        good_data = dict(bad_data, announcements_sections=self._make_6tier({"3. 이번주 일정 안내": item_next_sun}))
        yaml_path.write_text(yaml.safe_dump(good_data, allow_unicode=True), encoding="utf-8")
        ok_buf = io.StringIO()
        with contextlib.redirect_stdout(ok_buf), patch(
            "src.main.find_latest_session_material", return_value={"file_path": str(self.latest_session)}
        ), patch.object(sys, "argv", cli_argv):
            cli_main()
        self.assertEqual(len(list(out_dir.glob("*.hwpx"))), 1)

    def _create_mock_ann_hwpx(self, filename: str = "mock_ann_template.hwpx") -> Path:
        from tests.test_hwpx_engine import TestHwpxEngine

        return TestHwpxEngine._write_synthetic_hwpx_fixture(self.tmp / filename)

    def test_shared_validation_across_cli_engine_and_reviewer(self):
        """3-A 회귀: main CLI, HwpxEngine.generate 직접 호출, BulletinReviewer 및 review_bulletin CLI가 동일한 공통 검증 category를 검출하고 정상 입력은 통과해야 함."""
        import contextlib
        import copy
        import io
        import re
        import sys
        from unittest.mock import patch
        from scripts.review_bulletin import main as review_cli_main
        from scripts.validate_bulletin_facts import validate_bulletin_facts_data, validate_facts
        from src.hwpx_engine import BulletinValidationError, HwpxEngine
        from src.main import main as cli_main
        from src.reviewer.cross_week import CrossWeekComparator
        from src.reviewer.engine import BulletinReviewer
        from src.reviewer.models import IssueLevel

        mock_hwpx = self._create_mock_ann_hwpx()

        defect_cases = [
            (
                "next_sun_in_future",
                {
                    "announcements_sections": self._make_6tier(
                        {"4. 이후 일정 안내": [{"title": "가상차주내부행사", "content": "11/22(일) 13:00"}]}
                    )
                },
                {"주간 일정 분류 오류 (Rule 22)"},
            ),
            (
                "far_future_in_this_week",
                {
                    "announcements_sections": self._make_6tier(
                        {"3. 이번주 일정 안내": [{"title": "가상먼미래행사", "content": "11/30(월) 19:00"}]}
                    )
                },
                {"주간 일정 분류 오류 (Rule 22)"},
            ),
            (
                "ecumenical_in_member_news",
                {
                    "announcements_sections": self._make_7tier(
                        {"2. 교우 소식": [{"title": "NCCK 가상행사", "content": "가상연대모임"}]}
                    )
                },
                {"에큐메니칼 소식 오분류 (Rule 22)"},
            ),
            (
                "legacy_announcements",
                {
                    "announcements": [{"title": "NCCK 가상행사", "content": "오늘 행사"}],
                },
                {"지원되지 않는 레거시 소식 구조 (Rule 22)", "에큐메니칼 소식 오분류 (Rule 22)"},
            ),
            (
                "structure_violation_missing_future",
                {
                    "announcements_sections": [s for s in self._make_6tier() if "이후 일정" not in s["title"]],
                },
                {"공동관심사 소주제 구조 위반 (Rule 22)"},
            ),
        ]

        synth_duties = {
            "w1": {
                "presider": "가상인도자",
                "pastoral_prayer": "가상기도자",
                "scripture_reader": "가상봉독자",
                "preacher": "가상설교자",
                "thanks_prayer": "가상감사자",
            }
        }

        with patch.object(CrossWeekComparator, "_find_and_load_prev_bulletin", return_value=None):
            for label, extra_payload, expected_cats in defect_cases:
                bad_data = {
                    "metadata": {"date_compact": "20261115", "season": "창조절"},
                    "worship_1": {
                        "choir_song_title": "가상찬양",
                        "scripture": "창세기 1:1 (1쪽)",
                        "sermon_title": "가상설교",
                        "responsive_scripture_1": "가상말씀구절",
                    },
                    "duties": copy.deepcopy(synth_duties),
                }
                bad_data.update(extra_payload)
                original_snapshot = copy.deepcopy(bad_data)

                # 1) HwpxEngine.generate 직접 호출 (Manifest/Downloads/온라인 조회 없이도 동일 category로 BLOCK, 파일 미생성)
                isolated_dir = self.tmp / f"engine_only_{label}"
                isolated_dir.mkdir(parents=True, exist_ok=True)
                engine_out = isolated_dir / "direct_out.hwpx"
                engine = HwpxEngine(mock_hwpx, logo_dir=self.tmp / "no-logos")
                with patch("scripts.fetch_sunday_scripture.fetch_post_url") as mock_fetch:
                    with self.assertRaises(BulletinValidationError, msg=f"[{label}] HwpxEngine.generate must block") as eng_ctx:
                        engine.generate(bad_data, engine_out)
                    mock_fetch.assert_not_called()
                self.assertFalse(engine_out.exists(), f"[{label}] 차단 시 출력 파일이 생성되면 안 됨")
                eng_issue_cats = {iss["category"] for iss in eng_ctx.exception.issues}
                eng_line_cats = {
                    re.match(r"^\[([^\[\]]+)\]", ln).group(1)
                    for ln in str(eng_ctx.exception).splitlines()
                    if re.match(r"^\[([^\[\]]+)\]", ln)
                }
                self.assertEqual(eng_issue_cats, expected_cats, f"[{label}] 엔진 issues category 불일치")
                self.assertEqual(eng_line_cats, expected_cats, f"[{label}] 엔진 메시지 category 불일치: {eng_ctx.exception}")
                self.assertEqual(bad_data, original_snapshot, f"[{label}] 엔진 직접 호출이 원본 dict를 변경하면 안 됨")

                # 2) BulletinReviewer 메모리 직접 호출 -> 동일 ERROR category 검출
                report = BulletinReviewer(bad_data).run_review()
                rev_err_cats = {i.category for i in report.issues if i.level == IssueLevel.ERROR}
                self.assertEqual(rev_err_cats, expected_cats, f"[{label}] Reviewer 오류 category 불일치: {rev_err_cats}")
                self.assertEqual(bad_data, original_snapshot, f"[{label}] BulletinReviewer가 원본 dict를 변경하면 안 됨")

                yaml_path = self.tmp / f"bulletin_20261115_{label}.yaml"
                manifest_path = self.tmp / f"bulletin_20261115_{label}_manifest.yaml"
                cli_out_dir = self.tmp / f"cli_out_{label}"
                yaml_path.write_text(yaml.safe_dump(bad_data, allow_unicode=True), encoding="utf-8")
                manifest_path.write_text(
                    yaml.safe_dump(
                        {"source_manifest": {"session_material": {"file_path": str(self.latest_session)}}},
                        allow_unicode=True,
                    ),
                    encoding="utf-8",
                )

                # validate_facts(path) CLI 호환 래퍼와 validate_bulletin_facts_data(data) 메모리 검증 일치 확인
                with patch("scripts.fetch_sunday_scripture.fetch_post_url", return_value=None):
                    file_fact_cats = {i["category"] for i in validate_facts(str(yaml_path)) if i["level"] == "ERROR"}
                mem_fact_cats = {
                    i["category"]
                    for i in validate_bulletin_facts_data(bad_data, check_online_scripture=False)
                    if i["level"] == "ERROR"
                }
                self.assertEqual(file_fact_cats, expected_cats)
                self.assertEqual(mem_fact_cats, expected_cats)

                # 3) main CLI -> SystemExit(1), 파일 미생성, 동일 차단 category
                cli_argv = [
                    "main",
                    "--data",
                    str(yaml_path),
                    "--engine",
                    "hwpx",
                    "--hwpx-template",
                    str(mock_hwpx),
                    "--output",
                    str(cli_out_dir),
                ]
                cli_buf = io.StringIO()
                with contextlib.redirect_stdout(cli_buf), patch(
                    "src.main.find_latest_session_material",
                    return_value={"file_path": str(self.latest_session)},
                ), patch(
                    "scripts.fetch_sunday_scripture.fetch_post_url", return_value=None
                ), patch.object(sys, "argv", cli_argv):
                    with self.assertRaises(SystemExit) as cli_ctx:
                        cli_main()
                    self.assertEqual(cli_ctx.exception.code, 1)
                self.assertEqual(list(cli_out_dir.glob("*.hwpx")), [])
                cli_blocks = self._extract_preflight_blocks(cli_buf.getvalue())
                cli_cats = {re.match(r"^\[([^\[\]]+)\]", b).group(1) for b in cli_blocks if re.match(r"^\[([^\[\]]+)\]", b)}
                self.assertEqual(cli_cats, expected_cats, f"[{label}] main CLI 차단 category 불일치: {cli_blocks}")

                # 4) review_bulletin CLI -> ERROR 존재 시 SystemExit(1) 반환 및 콘솔 보고서에 category 출력
                rev_buf = io.StringIO()
                with contextlib.redirect_stdout(rev_buf), patch.object(
                    sys, "argv", ["review_bulletin", str(yaml_path)]
                ):
                    with self.assertRaises(SystemExit, msg=f"[{label}] review_bulletin CLI must exit non-zero") as rev_ctx:
                        review_cli_main()
                    self.assertEqual(rev_ctx.exception.code, 1)
                for cat in expected_cats:
                    self.assertIn(cat, rev_buf.getvalue())

            # 정상 입력 대조군: main CLI, HwpxEngine.generate(온라인 조회·Manifest 없이), BulletinReviewer / review_bulletin CLI 모두 정상 통과
            valid_data = {
                "metadata": {"date_compact": "20261115", "season": "창조절"},
                "worship_1": {
                    "choir_song_title": "가상찬양",
                    "scripture": "창세기 1:1 (1쪽)",
                    "sermon_title": "가상설교",
                    "responsive_scripture_1": "가상말씀구절",
                },
                "duties": copy.deepcopy(synth_duties),
                "announcements_sections": self._make_7tier(
                    {
                        "1. 오늘 일정 안내": [{"title": "가상당일모임", "content": "11/15(일) 13:00"}],
                        "2. 교우 소식": [{"title": "가상교우안내", "content": "가상내용"}],
                        "4. 이번주 일정 안내": [{"title": "가상차주내부행사", "content": "11/22(일) 13:00"}],
                        "5. 이후 일정 안내": [{"title": "가상먼미래행사", "content": "11/30(월) 19:00"}],
                        "6. 에큐메니칼 소식": [{"title": "NCCK 가상행사", "content": "가상연대모임"}],
                    }
                ),
            }

            direct_valid_out = self.tmp / "engine_valid_only" / "valid_direct.hwpx"
            with patch("scripts.fetch_sunday_scripture.fetch_post_url") as mock_fetch_ok:
                generated = HwpxEngine(mock_hwpx, logo_dir=self.tmp / "no-logos").generate(valid_data, direct_valid_out)
                mock_fetch_ok.assert_not_called()
            self.assertTrue(generated.is_file())

            ok_report = BulletinReviewer(valid_data).run_review()
            self.assertEqual(ok_report.error_count, 0)

            valid_yaml = self.tmp / "bulletin_20261115_valid.yaml"
            valid_manifest = self.tmp / "bulletin_20261115_valid_manifest.yaml"
            valid_cli_out = self.tmp / "cli_valid_out"
            valid_yaml.write_text(yaml.safe_dump(valid_data, allow_unicode=True), encoding="utf-8")
            valid_manifest.write_text(
                yaml.safe_dump(
                    {"source_manifest": {"session_material": {"file_path": str(self.latest_session)}}},
                    allow_unicode=True,
                ),
                encoding="utf-8",
            )

            with contextlib.redirect_stdout(io.StringIO()), patch(
                "src.main.find_latest_session_material", return_value={"file_path": str(self.latest_session)}
            ), patch("scripts.fetch_sunday_scripture.fetch_post_url", return_value=None), patch.object(
                sys,
                "argv",
                [
                    "main",
                    "--data",
                    str(valid_yaml),
                    "--engine",
                    "hwpx",
                    "--hwpx-template",
                    str(mock_hwpx),
                    "--output",
                    str(valid_cli_out),
                ],
            ):
                cli_main()
            self.assertEqual(len(list(valid_cli_out.glob("*.hwpx"))), 1)

            with contextlib.redirect_stdout(io.StringIO()), patch.object(
                sys, "argv", ["review_bulletin", str(valid_yaml)]
            ):
                review_cli_main()

    def test_rule34_auto_before_validation_revalidation_and_blocking(self):
        """3-A 회귀: Rule 34 월례회 AUTO 보정 후 재검증, 보정 불가(오늘 섹션 없음·빈 sections·sections 누락) 시 BLOCK, 중복 삽입 방지 검증."""
        import contextlib
        import copy
        import io
        import re
        import sys
        import zipfile
        from unittest.mock import patch
        from scripts.review_bulletin import main as review_cli_main
        from src.hwpx_engine import BulletinValidationError, HwpxEngine
        from src.main import main as cli_main
        from src.reviewer.cross_week import CrossWeekComparator
        from src.reviewer.engine import BulletinReviewer
        from src.reviewer.models import IssueLevel

        mock_hwpx = self._create_mock_ann_hwpx("mock_rule34_template.hwpx")
        engine = HwpxEngine(mock_hwpx, logo_dir=self.tmp / "no-logos")

        # 1. 보정 불가 케이스: (a) announcements_sections 필드 누락, (b) 오늘 섹션 없음, (c) 빈 sections([])
        unfixable_cases = [
            ("20261101", {}, {"매월 1주 정례 모임 누락 (Rule 34)"}),
            ("20261108", {}, {"매월 2주 정례 모임 누락 (Rule 34)"}),
            (
                "20261101",
                {"announcements_sections": [{"title": "3. 이번주 일정 안내", "items": []}]},
                {"공동관심사 소주제 구조 위반 (Rule 22)", "매월 1주 정례 모임 누락 (Rule 34)"},
            ),
            (
                "20261101",
                {"announcements_sections": []},
                {"공동관심사 소주제 구조 위반 (Rule 22)", "매월 1주 정례 모임 누락 (Rule 34)"},
            ),
            (
                "20261108",
                {"announcements_sections": []},
                {"공동관심사 소주제 구조 위반 (Rule 22)", "매월 2주 정례 모임 누락 (Rule 34)"},
            ),
        ]

        synth_duties = {
            "w1": {
                "presider": "가상인도자",
                "pastoral_prayer": "가상기도자",
                "scripture_reader": "가상봉독자",
                "preacher": "가상설교자",
                "thanks_prayer": "가상감사자",
            }
        }

        with patch.object(CrossWeekComparator, "_find_and_load_prev_bulletin", return_value=None):
            for idx, (date_compact, extra, expected_cats) in enumerate(unfixable_cases):
                payload = {
                    "metadata": {"date_compact": date_compact, "season": "창조절"},
                    "worship_1": {"choir_song_title": "가상찬양", "scripture": "창세기 1:1 (1쪽)", "sermon_title": "가상설교"},
                    "duties": copy.deepcopy(synth_duties),
                }
                payload.update(extra)
                snapshot = copy.deepcopy(payload)

                passed, _, pre_out = self._run_case(date_compact, extra)
                self.assertFalse(passed, f"[case {idx}] 미해결 Rule 34 누락은 run_preflight에서 BLOCK되어야 함:\n{pre_out}")
                blocks = self._extract_preflight_blocks(pre_out)
                block_cats = {re.match(r"^\[([^\[\]]+)\]", b).group(1) for b in blocks if re.match(r"^\[([^\[\]]+)\]", b)}
                self.assertEqual(block_cats, expected_cats, f"[case {idx}] preflight 차단 category 불일치: {blocks}")

                bad_out = self.tmp / f"rule34_blocked_{idx}.hwpx"
                with self.assertRaises(BulletinValidationError) as eng_ctx:
                    engine.generate(payload, bad_out)
                self.assertFalse(bad_out.exists())
                self.assertEqual({iss["category"] for iss in eng_ctx.exception.issues}, expected_cats)

                rep = BulletinReviewer(payload).run_review()
                rep_err_cats = {i.category for i in rep.issues if i.level == IssueLevel.ERROR}
                self.assertEqual(rep_err_cats, expected_cats)
                self.assertEqual(payload, snapshot, "차단 경로에서도 호출자 원본 dict가 변경되면 안 됨")

                y_path = self.tmp / f"bulletin_{date_compact}_unfix_{idx}.yaml"
                m_path = self.tmp / f"bulletin_{date_compact}_unfix_{idx}_manifest.yaml"
                c_out = self.tmp / f"cli_rule34_unfix_{idx}"
                y_path.write_text(yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8")
                m_path.write_text(
                    yaml.safe_dump(
                        {"source_manifest": {"session_material": {"file_path": str(self.latest_session)}}},
                        allow_unicode=True,
                    ),
                    encoding="utf-8",
                )
                cli_buf = io.StringIO()
                with contextlib.redirect_stdout(cli_buf), patch(
                    "src.main.find_latest_session_material", return_value={"file_path": str(self.latest_session)}
                ), patch.object(
                    sys,
                    "argv",
                    ["main", "--data", str(y_path), "--engine", "hwpx", "--hwpx-template", str(mock_hwpx), "--output", str(c_out)],
                ):
                    with self.assertRaises(SystemExit) as c_ctx:
                        cli_main()
                    self.assertEqual(c_ctx.exception.code, 1)
                self.assertEqual(list(c_out.glob("*.hwpx")), [])

                rev_buf = io.StringIO()
                with contextlib.redirect_stdout(rev_buf), patch.object(
                    sys, "argv", ["review_bulletin", str(y_path)]
                ):
                    with self.assertRaises(SystemExit) as r_ctx:
                        review_cli_main()
                    self.assertEqual(r_ctx.exception.code, 1)
                for cat in expected_cats:
                    self.assertIn(cat, rev_buf.getvalue())

            # 2. 정상 오늘 섹션 (1주차 부서 월례회 + 제직회 직후 삽입 / 2주차 신도회 월례회) 및 이미 공지가 있는 경우 중복 삽입 방지
            auto_cases = [
                (
                    "20261101",
                    [{"title": "정기 제직회", "content": "예배 후, 대예배실(2층)"}],
                    "부서 월례회",
                    "공동식사 후, 각 부서 공간",
                    'id="1185698824"',
                ),
                (
                    "20261108",
                    [],
                    "신도회 월례회",
                    "공동식사 후, 각 신도회 모임 공간",
                    'id="1137471996"',
                ),
            ]

            for date_compact, initial_today_items, expected_title, expected_content, expected_box_id in auto_cases:
                # (a) 미기재 시 AUTO 보정 -> 재검증 PASS -> 실제 렌더링 XML 반영 (원본 dict 불변)
                data_missing = {
                    "metadata": {"date_compact": date_compact, "season": "창조절"},
                    "worship_1": {"choir_song_title": "가상찬양", "scripture": "창세기 1:1 (1쪽)", "sermon_title": "가상설교"},
                    "duties": copy.deepcopy(synth_duties),
                    "announcements_sections": self._make_6tier({"1. 오늘 일정 안내": initial_today_items}),
                }
                before_missing = copy.deepcopy(data_missing)

                y_auto = self.tmp / f"bulletin_{date_compact}_auto.yaml"
                m_auto = self.tmp / f"bulletin_{date_compact}_auto_manifest.yaml"
                out_auto_dir = self.tmp / f"cli_auto_{date_compact}"
                y_auto.write_text(yaml.safe_dump(data_missing, allow_unicode=True), encoding="utf-8")
                m_auto.write_text(
                    yaml.safe_dump(
                        {"source_manifest": {"session_material": {"file_path": str(self.latest_session)}}},
                        allow_unicode=True,
                    ),
                    encoding="utf-8",
                )

                passed_auto = run_preflight(data_missing, y_auto, downloads_dir=self.downloads)
                self.assertTrue(passed_auto)
                self.assertEqual(data_missing, before_missing, "run_preflight가 호출자 원본 dict를 변경하면 안 됨")

                rev_auto = BulletinReviewer(data_missing).run_review()
                self.assertEqual(rev_auto.error_count, 0)
                self.assertEqual(data_missing, before_missing, "BulletinReviewer가 호출자 원본 dict를 변경하면 안 됨")

                direct_out = self.tmp / f"direct_auto_{date_compact}.hwpx"
                engine.generate(data_missing, direct_out)
                self.assertEqual(data_missing, before_missing, "HwpxEngine.generate가 호출자 원본 dict를 변경하면 안 됨")

                with zipfile.ZipFile(direct_out) as zf:
                    sec_xml = zf.read("Contents/section0.xml").decode("utf-8")
                self.assertEqual(sec_xml.count(expected_title), 1)
                self.assertIn(expected_content, sec_xml)
                self.assertEqual(sec_xml.count(expected_box_id), 1)
                if initial_today_items:
                    self.assertLess(sec_xml.index("정기 제직회"), sec_xml.index(expected_title))

                # main CLI 전체 경로 실행 시에도 중복 삽입 없이 정확히 1회만 출력
                with contextlib.redirect_stdout(io.StringIO()), patch(
                    "src.main.find_latest_session_material", return_value={"file_path": str(self.latest_session)}
                ), patch.object(
                    sys,
                    "argv",
                    ["main", "--data", str(y_auto), "--engine", "hwpx", "--hwpx-template", str(mock_hwpx), "--output", str(out_auto_dir)],
                ):
                    cli_main()
                cli_files = list(out_auto_dir.glob("*.hwpx"))
                self.assertEqual(len(cli_files), 1)
                with zipfile.ZipFile(cli_files[0]) as zf:
                    cli_xml = zf.read("Contents/section0.xml").decode("utf-8")
                self.assertEqual(cli_xml.count(expected_title), 1)
                self.assertEqual(cli_xml.count(expected_box_id), 1)

                # review_bulletin CLI도 AUTO 보정 후 재검증 통과 (종료 코드 0)
                with contextlib.redirect_stdout(io.StringIO()), patch.object(
                    sys, "argv", ["review_bulletin", str(y_auto)]
                ):
                    review_cli_main()

                # (b) 이미 월례회 공지가 있는 경우 중복 삽입 금지
                already_items = list(initial_today_items) + [{"title": expected_title, "content": expected_content}]
                data_present = {
                    "metadata": {"date_compact": date_compact, "season": "창조절"},
                    "worship_1": {"choir_song_title": "가상찬양", "scripture": "창세기 1:1 (1쪽)", "sermon_title": "가상설교"},
                    "duties": copy.deepcopy(synth_duties),
                    "announcements_sections": self._make_6tier({"1. 오늘 일정 안내": already_items}),
                }
                before_present = copy.deepcopy(data_present)
                present_out = self.tmp / f"direct_present_{date_compact}.hwpx"
                engine.generate(data_present, present_out)
                self.assertEqual(data_present, before_present)
                with zipfile.ZipFile(present_out) as zf:
                    pres_xml = zf.read("Contents/section0.xml").decode("utf-8")
                self.assertEqual(pres_xml.count(expected_title), 1)
                self.assertEqual(pres_xml.count(expected_box_id), 1)


if __name__ == '__main__':
    unittest.main()

