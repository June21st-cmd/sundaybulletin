"""Unit tests for HWPX template engine."""
import tempfile
import unittest
import zipfile
from pathlib import Path

from src.hwpx_engine import HwpxEngine
from src.parser import load_bulletin_data


class TestHwpxEngine(unittest.TestCase):
    @staticmethod
    def _canonical_6tier(today_items=None):
        return [
            {"title": "1. 오늘 일정 안내", "items": list(today_items or [])},
            {"title": "2. 함께 만드는 향린", "items": []},
            {"title": "3. 이번주 일정 안내", "items": []},
            {"title": "4. 이후 일정 안내", "items": []},
            {"title": "5. 에큐메니칼 소식", "items": []},
            {"title": "6. 감사헌금", "items": []},
        ]

    @staticmethod
    def _build_synthetic_header_xml(extra_charprs: str = "", override_46_bold: bool = False) -> str:
        specs = [
            ("0", "3", "1000", False),
            ("7", "3", "1000", False),
            ("21", "1", "1550", False),
            ("24", "3", "1500", False),
            ("25", "3", "1000", False),
            ("26", "3", "1000", False),
            ("30", "3", "1500", False),
            ("38", "3", "1500", False),
            ("46", "1", "1550", override_46_bold),
            ("66", "0", "1700", False),
            ("68", "3", "1000", False),
            ("72", "3", "1000", False),
            ("79", "3", "1500", False),
            ("119", "3", "1000", False),
            ("122", "3", "1000", False),
            ("125", "3", "600", False),
            ("127", "3", "1500", True),
            ("133", "3", "1500", False),
            ("143", "9", "1500", False),
            ("147", "3", "1550", True),
            ("152", "3", "1000", False),
            ("160", "1", "1550", False),
            ("173", "6", "1500", False),
            ("193", "3", "1500", False),
            ("195", "3", "1200", False),
        ]
        cpr_list = []
        for cid, fref, height, is_bold in specs:
            bold_xml = "<hh:bold/>" if is_bold else ""
            cpr_list.append(
                f'<hh:charPr id="{cid}" height="{height}" textColor="#000000" shadeColor="none" '
                f'useFontSpace="0" useKerning="0" symMark="NONE" borderFillIDRef="1">'
                f'<hh:fontRef hangul="{fref}" latin="{fref}" hanja="{fref}" japanese="{fref}" other="{fref}" symbol="{fref}" user="{fref}"/>'
                f'<hh:ratio hangul="96" latin="96" hanja="96" japanese="96" other="96" symbol="96" user="96"/>'
                f'<hh:spacing hangul="0" latin="0" hanja="0" japanese="0" other="0" symbol="0" user="0"/>'
                f'{bold_xml}'
                f'</hh:charPr>'
            )
        if extra_charprs:
            cpr_list.append(extra_charprs)
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>'
            '<hh:head xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head" '
            'xmlns:hc="http://www.hancom.co.kr/hwpml/2011/core" version="1.4" secCnt="1">'
            '<hh:refList>'
            '<hh:fontfaces itemCnt="1">'
            '<hh:fontface lang="HANGUL" fontCnt="5">'
            '<hh:font id="0" face="경기천년바탕 Bold" type="TTF" isEmbedded="0"/>'
            '<hh:font id="1" face="경기천년바탕 Regular" type="TTF" isEmbedded="0"/>'
            '<hh:font id="3" face="리디바탕" type="TTF" isEmbedded="0"/>'
            '<hh:font id="6" face="함초롬돋움" type="TTF" isEmbedded="0"/>'
            '<hh:font id="9" face="HY견고딕" type="TTF" isEmbedded="0"/>'
            '</hh:fontface>'
            '</hh:fontfaces>'
            f'<hh:charProperties itemCnt="{len(cpr_list)}">'
            + "".join(cpr_list)
            + '</hh:charProperties>'
            '</hh:refList>'
            '</hh:head>'
        )

    @staticmethod
    def _create_synthetic_png(width: int, height: int) -> bytes:
        import zlib
        import struct
        sig = b"\x89PNG\r\n\x1a\n"
        ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
        ihdr_crc = struct.pack(">I", zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF)
        ihdr = struct.pack(">I", len(ihdr_data)) + b"IHDR" + ihdr_data + ihdr_crc
        raw_pixel_data = b"\x00" + (b"\x00\x00\x00\x00" * width)
        compressed = zlib.compress(raw_pixel_data * height)
        idat_crc = struct.pack(">I", zlib.crc32(b"IDAT" + compressed) & 0xFFFFFFFF)
        idat = struct.pack(">I", len(compressed)) + b"IDAT" + compressed + idat_crc
        iend = struct.pack(">I", 0) + b"IEND" + struct.pack(">I", zlib.crc32(b"IEND") & 0xFFFFFFFF)
        return sig + ihdr + idat + iend

    @classmethod
    def _write_synthetic_hwpx_fixture(
        cls,
        dest_path: Path,
        *,
        include_ann_boundary: bool = True,
        include_table10: bool = True,
        include_healing3_slot: bool = True,
        include_logos: bool = False,
        extra_bindata: dict[str, bytes] | None = None,
        extra_section_xml: str = "",
        raw_section_xml: str | None = None,
        raw_header_xml: str | None = None,
        extra_charprs: str = "",
        override_46_bold: bool = False,
    ) -> Path:
        header_xml = raw_header_xml if raw_header_xml is not None else cls._build_synthetic_header_xml(
            extra_charprs=extra_charprs,
            override_46_bold=override_46_bold,
        )
        if raw_section_xml is not None:
            section_xml = raw_section_xml
        else:
            parts = [
                '<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>',
                '<ns1:sec xmlns:ns1="http://www.hancom.co.kr/hwpml/2011/paragraph" '
                'xmlns:ns2="http://www.hancom.co.kr/hwpml/2011/core">',
                '<ns1:p id="0" paraPrIDRef="0"><ns1:run charPrIDRef="0"><ns1:t>{{설교제목}}</ns1:t></ns1:run></ns1:p>',
                '<ns1:p id="0" paraPrIDRef="0"><ns1:run charPrIDRef="0"><ns1:t>{{창립주년}}</ns1:t></ns1:run></ns1:p>',
                '<ns1:p id="0" paraPrIDRef="0"><ns1:run charPrIDRef="0"><ns1:t>{{ad5_title}}</ns1:t></ns1:run></ns1:p>',
                '<ns1:p id="0" paraPrIDRef="0"><ns1:run charPrIDRef="0"><ns1:t>신 앙 고 백 송</ns1:t></ns1:run></ns1:p>',
                '<ns1:p id="0" paraPrIDRef="0"><ns1:run charPrIDRef="0"><ns1:t>국악찬송 254장</ns1:t></ns1:run></ns1:p>',
            ]
            if include_ann_boundary:
                parts.extend([
                    '<ns1:p id="1" paraPrIDRef="94"><ns1:run charPrIDRef="143"><ns1:t>1. 오늘 일정 안내</ns1:t></ns1:run></ns1:p>',
                    '<ns1:p id="2" paraPrIDRef="0"><ns1:run charPrIDRef="0"><ns1:t>[온라인헌금 안내]</ns1:t></ns1:run></ns1:p>',
                ])
            if include_table10:
                h3_p = (
                    '<ns1:p id="0" paraPrIDRef="98"><ns1:run charPrIDRef="160"><ns1:t>{{healing_prayer_3}}</ns1:t></ns1:run></ns1:p>'
                    if include_healing3_slot
                    else ""
                )
                parts.append(
                    '<ns1:p id="0" paraPrIDRef="0"><ns1:run charPrIDRef="0">'
                    '<ns1:tbl id="1111275716" rowCnt="1" colCnt="1">'
                    '<ns1:sz width="51741" widthRelTo="ABSOLUTE" height="38484" heightRelTo="ABSOLUTE" protect="0"/>'
                    '<ns1:tr><ns1:tc borderFillIDRef="1">'
                    '<ns1:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="CENTER">'
                    '<ns1:p id="0" paraPrIDRef="98"><ns1:run charPrIDRef="66"><ns1:t>▯등록 새교우 (2026)</ns1:t></ns1:run></ns1:p>'
                    '<ns1:p id="0" paraPrIDRef="99"><ns1:run charPrIDRef="21"><ns1:t> 가상누적교우(가상회, 01/01)</ns1:t></ns1:run></ns1:p>'
                    '<ns1:p id="0" paraPrIDRef="100"><ns1:run charPrIDRef="66"><ns1:t>▯건강회복을 위해</ns1:t></ns1:run></ns1:p>'
                    '<ns1:p id="0" paraPrIDRef="98"><ns1:run charPrIDRef="160"><ns1:t>{{healing_prayer_1}} {{healing_prayer_2}}</ns1:t></ns1:run></ns1:p>'
                    f'{h3_p}'
                    '<ns1:p id="0" paraPrIDRef="100"><ns1:run charPrIDRef="66"><ns1:t>▯군복무 중 건강과 안전을 위해╻</ns1:t></ns1:run>'
                    '<ns1:run charPrIDRef="46"><ns1:t> {{military_prayer_names}}</ns1:t></ns1:run></ns1:p>'
                    '<ns1:p id="0" paraPrIDRef="100"><ns1:run charPrIDRef="66"><ns1:t>▯해외 체류 중인 교우들을 위해</ns1:t></ns1:run></ns1:p>'
                    '<ns1:p id="0" paraPrIDRef="98"><ns1:run charPrIDRef="160"><ns1:t>{{overseas_prayer_1}}</ns1:t></ns1:run></ns1:p>'
                    '<ns1:p id="0" paraPrIDRef="98"><ns1:run charPrIDRef="160"><ns1:t>{{overseas_prayer_2}}</ns1:t></ns1:run></ns1:p>'
                    '</ns1:subList>'
                    '<ns1:cellAddr colAddr="0" rowAddr="0"/><ns1:cellSpan colSpan="1" rowSpan="1"/><ns1:cellSz width="51741" height="38484"/>'
                    '</ns1:tc></ns1:tr>'
                    '</ns1:tbl>'
                    '</ns1:run></ns1:p>'
                )
            if include_logos:
                parts.extend([
                    '<ns1:p id="0" paraPrIDRef="0"><ns1:run charPrIDRef="0">'
                    '<ns1:pic id="1111275668" zOrder="2" numberingType="PICTURE" textWrap="TOP_AND_BOTTOM" textFlow="BOTH_SIDES" lock="0" dropcapstyle="None" href="" groupLevel="0" instid="37533845" reverse="0">'
                    '<ns1:orgSz width="18840" height="21240"/><ns1:curSz width="7007" height="7898"/>'
                    '<ns1:renderingInfo><ns2:scaMatrix e1="0.371921" e2="0" e3="0" e4="0" e5="0.371893" e6="0"/></ns1:renderingInfo>'
                    '<ns2:img binaryItemIDRef="image3"/>'
                    '<ns1:sz width="7007" widthRelTo="ABSOLUTE" height="7899" heightRelTo="ABSOLUTE" protect="0"/>'
                    '</ns1:pic></ns1:run></ns1:p>',
                    '<ns1:p id="0" paraPrIDRef="0"><ns1:run charPrIDRef="0">'
                    '<ns1:pic id="1111275670" zOrder="1" numberingType="PICTURE" textWrap="TOP_AND_BOTTOM" textFlow="BOTH_SIDES" lock="0" dropcapstyle="None" href="" groupLevel="0" instid="37533847" reverse="0">'
                    '<ns1:orgSz width="52500" height="15540"/><ns1:curSz width="20542" height="6080"/>'
                    '<ns1:renderingInfo><ns2:scaMatrix e1="0.391276" e2="0" e3="0" e4="0" e5="0.391248" e6="0"/></ns1:renderingInfo>'
                    '<ns2:img binaryItemIDRef="image4"/>'
                    '<ns1:sz width="20542" widthRelTo="ABSOLUTE" height="6080" heightRelTo="ABSOLUTE" protect="0"/>'
                    '</ns1:pic></ns1:run></ns1:p>',
                ])
            if extra_section_xml:
                parts.append(extra_section_xml)
            parts.append("</ns1:sec>")
            section_xml = "".join(parts)

        with zipfile.ZipFile(dest_path, "w") as z:
            z.writestr("mimetype", "application/hwp+zip", compress_type=zipfile.ZIP_STORED)
            z.writestr("Contents/header.xml", header_xml.encode("utf-8"))
            z.writestr("Contents/section0.xml", section_xml.encode("utf-8"))
            written_bin = set()
            if extra_bindata:
                for b_name, b_bytes in extra_bindata.items():
                    z.writestr(b_name, b_bytes)
                    written_bin.add(b_name)
            if include_logos:
                if "BinData/image3.png" not in written_bin:
                    z.writestr("BinData/image3.png", cls._create_synthetic_png(251, 283))
                if "BinData/image4.png" not in written_bin:
                    z.writestr("BinData/image4.png", cls._create_synthetic_png(700, 207))
        return dest_path

    def test_hwpx_flattening(self):
        data = {
            "metadata": {
                "foundation_year": "73",
                "season": "성령강림주일",
                "headline_left": "초청 하늘뜻펴기",
            },
            "worship_1": {
                "sermon_title": "새 하늘과 새 땅",
            },
            "announcements": [
                {"title": "광고1번", "content": "내용1"},
                {"title": "광고2번", "content": "내용2"},
            ],
        }
        flat = HwpxEngine.flatten_data(data)
        self.assertEqual(flat["foundation_year"], "73")
        self.assertEqual(flat["창립주년"], "73")
        self.assertEqual(flat["설교제목"], "새 하늘과 새 땅")
        self.assertEqual(flat["광고1_제목"], "광고1번")
        self.assertEqual(flat["ad1_title"], "광고1번")
        self.assertEqual(flat["ad3_title"], "")

    def test_mock_substitution_and_autoclean(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            mock_hwpx = self._write_synthetic_hwpx_fixture(temp_path / "mock.hwpx")

            engine = HwpxEngine(mock_hwpx, logo_dir=temp_path / "no-logos")
            out_hwpx = temp_path / "out.hwpx"

            legacy_data = {
                "worship_1": {"sermon_title": "희망의 노래"},
                "announcements": [{"title": "첫번째 광고"}],
            }
            with self.assertRaises(ValueError):
                engine.generate(legacy_data, out_hwpx)
            self.assertFalse(out_hwpx.exists())

            data = {
                "metadata": {"date_compact": "20261115", "foundation_year": "73"},
                "worship_1": {"sermon_title": "희망의 노래"},
                "announcements_sections": self._canonical_6tier(),
            }
            result = engine.generate(data, out_hwpx)
            
            with zipfile.ZipFile(result, "r") as z_out:
                extracted_xml = z_out.read("Contents/section0.xml").decode("utf-8")
                self.assertIn("희망의 노래", extracted_xml)
                self.assertIn("73", extracted_xml)
                self.assertNotIn("{{ad5_title}}", extracted_xml)

    def test_liturgical_hymn_substitution(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            mock_hwpx = self._write_synthetic_hwpx_fixture(temp_path / "mock.hwpx")

            # 1. 1,5,9월: 주기도문송(1) 245장 입력 시 -> 좌측 "주 기 도 송", 우측 "국악찬송 245장"으로 정규화 및 치환
            engine = HwpxEngine(mock_hwpx, logo_dir=temp_path / "no-logos")
            out_hwpx1 = temp_path / "out1.hwpx"
            data1 = {
                "metadata": {"date": "2026-09-13"},
                "worship_1": {"confession_or_lord_prayer": "주기도문송(1) 245장"},
                "announcements_sections": self._canonical_6tier(),
            }
            engine.generate(data1, out_hwpx1)
            with zipfile.ZipFile(out_hwpx1, "r") as z_out:
                res1 = z_out.read("Contents/section0.xml").decode("utf-8")
                self.assertIn("주 기 도 송", res1)
                self.assertIn("국악찬송 245장", res1)
                self.assertNotIn("주기도문송", res1)
                self.assertNotIn("신 앙 고 백 송", res1)

            # 2. 3,7,11월: 3월에 "주기도송"만 지정 시 -> 좌측 "주 기 도 송", 우측 "국악찬송 246장" 기본값 보완
            out_hwpx2 = temp_path / "out2.hwpx"
            data2 = {
                "metadata": {"date": "2026-03-08"},
                "worship_1": {"confession_or_lord_prayer": "주기도송"},
                "announcements_sections": self._canonical_6tier(),
            }
            engine.generate(data2, out_hwpx2)
            with zipfile.ZipFile(out_hwpx2, "r") as z_out:
                res2 = z_out.read("Contents/section0.xml").decode("utf-8")
                self.assertIn("주 기 도 송", res2)
                self.assertIn("국악찬송 246장", res2)


    def test_real_master_template_generation(self):
        import os

        template_path = Path("templates/hwpx/template.hwpx").resolve()
        sample_data_path = Path("data/samples/sample_hyanglin_20260816.yaml").resolve()
        
        if template_path.is_file():
            with tempfile.TemporaryDirectory() as temp_dir:
                tmp_path = Path(temp_dir)
                engine = HwpxEngine(template_path, logo_dir=tmp_path / "no-logos")

                if sample_data_path.is_file():
                    legacy_data = load_bulletin_data(sample_data_path)
                    blocked_out = tmp_path / "blocked_legacy.hwpx"
                    with self.assertRaises(ValueError):
                        engine.generate(legacy_data, blocked_out)
                    self.assertFalse(blocked_out.exists())

                valid_data = {
                    "metadata": {"date_compact": "20261115", "season": "창조절"},
                    "worship_1": {"sermon_title": "가상설교제목"},
                    "announcements_sections": self._canonical_6tier(
                        [{"title": "가상당일모임", "content": "11/15(일) 13:00"}]
                    ),
                }
                out_path = tmp_path / "[주보] 20261115.hwpx"
                old_cwd = os.getcwd()
                try:
                    os.chdir(tmp_path)
                    result = engine.generate(valid_data, out_path)
                finally:
                    os.chdir(old_cwd)
                self.assertTrue(result.is_file())
                self.assertGreater(result.stat().st_size, 1000)

    def test_custom_asset_qr_and_announcement_spacing(self):
        template_path = Path("templates/hwpx/template.hwpx")
        data_path = Path("data/inputs/bulletin_20260913.yaml")
        if template_path.is_file() and data_path.is_file():
            data = load_bulletin_data(data_path)
            data.setdefault("metadata", {})["skip_scripture_verification"] = True
            engine = HwpxEngine(template_path)
            with tempfile.TemporaryDirectory() as temp_dir:
                out_path = Path(temp_dir) / "test_qr.hwpx"
                result = engine.generate(data, out_path)
                with zipfile.ZipFile(result, "r") as z:
                    names = z.namelist()
                    self.assertIn("BinData/image6.bmp", names)  # 교독송 후렴 악보 안전 보존
                    self.assertIn("BinData/image8.png", names)  # QR코드 독립 ID
                    sec0 = z.read("Contents/section0.xml").decode("utf-8")
                    self.assertIn("1191766890", sec0)  # pic ID
                    self.assertIn("2gtkk.png", sec0)
                    self.assertIn("김은주(새청, 9/06)", sec0)
                    self.assertIn('cellSz width="39958"', sec0)  # 하늘뜻펴기 확장 병합 셀
                    hdr = z.read("Contents/header.xml").decode("utf-8")
                    self.assertIn('lineSpacing type="PERCENT" value="165"', hdr)  # 165% 줄간격
                    self.assertIn('ratio hangul="90"', hdr)  # 장평 90%
                    self.assertIn('spacing hangul="0"', hdr)  # 자간 0%

    def test_prayer_roster_formatting_and_healing3_retention(self):
        """회귀 테스트: 완전 가상 fixture 기반 1단계 명단 서식 및 내용 보존 검증.
        1. 완전 가상 fixture:
           - 원본 부가파일(Preview, BinData) 복사 배제, 필수 구조 파일만 명시적 패키징.
           - 광범위한 부분문자열('하' 등) 및 연락처 보호 문자열 완전 제거.
           - 비구조적 본문은 '가상문구'로 치환, 치환 태그는 태그만 보존.
           - 정적 경계는 정확한 문구로 재구성하고, 불필요한 원문 잔존을 차단하는 가상 반례 검사 수행.
           - 테스트가 직접 생성한 가상 바이너리(synth_dummy.png)를 주입하여 바이너리 보존 검증.
        2. 9가지 입력 조합 검증:
           - 건강회복·군복무·해외체류 명단의 실제 글꼴(경기천년바탕 Regular), 크기(15.5pt), bold=False(cid 46).
           - 건강회복 3행의 유실·중복 없음.
           - 누적 명단 7개 행 전체의 순서·개수·내용 100% 보존.
           - 명단 소제목 Bold(cid 66) 및 일반 소식 제목 Bold(cid 127) 보존.
           - Table 10 고유 규격(51741x38484) 및 타 11개 표 해시 불변 검증.
        """
        import copy
        import hashlib
        import os
        import re
        from lxml import etree as E

        template_path = Path("templates/hwpx/template.hwpx").resolve()
        if not template_path.is_file():
            self.skipTest("template.hwpx fixture not available")

        NSH = "http://www.hancom.co.kr/hwpml/2011/head"

        # 1x1 최소 가상 PNG 바이너리
        SYNTH_PNG = (
            b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
            b'\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00'
            b'\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
        )

        def get_styles(header_xml_bytes):
            root = E.fromstring(header_xml_bytes)
            fonts = {x.get("id"): x.get("face") for x in root.xpath('//*[local-name()="fontface"][@lang="HANGUL"]/*[local-name()="font"]')}
            out = {}
            for x in root.xpath('//*[local-name()="charPr"]'):
                cid = x.get("id")
                f = x.find(f"{{{NSH}}}fontRef")
                face = fonts.get(f.get("hangul")) if f is not None else None
                has_bold_tag = x.find(f"{{{NSH}}}bold") is not None
                is_bold = has_bold_tag or ("Bold" in (face or ""))
                out[cid] = {
                    "bold": is_bold,
                    "height": x.get("height"),
                    "face": face,
                }
            return out

        # [요구사항 1] 완전 가상 fixture 구성 함수 (광범위 매칭 및 연락처 배제)
        def create_synthetic_template(src_template, dest_template):
            with zipfile.ZipFile(src_template) as z:
                sec_xml = z.read("Contents/section0.xml").decode("utf-8")
                header_xml = z.read("Contents/header.xml")
                content_hpf = z.read("Contents/content.hpf").decode("utf-8")
                settings_xml = z.read("settings.xml")
                version_xml = z.read("version.xml")
                container_xml = z.read("META-INF/container.xml")

            root = E.fromstring(sec_xml.encode("utf-8"))

            # 엔진 파싱에 반드시 필요한 최소 정적 경계 매핑 (광범위 '하' 및 연락처 완전 배제)
            EXACT_BOUNDARIES = {
                "등록 새교우": "▯등록 새교우 (2026)",
                "건강회복": "▯건강회복을 위해",
                "군복무": "▯군복무 중 건강과 안전을 위해╻",
                "해외 체류": "▯해외 체류 중인 교우들을 위해",
                "오늘 일정 안내": "1. 오늘 일정 안내",
                "온라인헌금": "[온라인헌금 안내]",
                "교회탄소중립": "[교회탄소중립]",
            }

            tbl10 = root.xpath('//*[local-name()="tbl"][@id="1111275716"]')[0]
            cumul_rows = []
            cumul_counter = 0

            # Table 10 누적 명단: 7개 행에 고유한 독립 가상 토큰 부여
            for p in tbl10.xpath('.//*[local-name()="p"]'):
                for r in p.xpath('./*[local-name()="run"][@charPrIDRef="21"]'):
                    t_node = r.find('{*}t')
                    if t_node is not None and t_node.text and "{{" not in t_node.text:
                        cumul_counter += 1
                        tok = f"가상누적_행{cumul_counter}_1(가상회, 01/01)  가상누적_행{cumul_counter}_2(가상회, 01/08)"
                        t_node.text = f" {tok}"
                        cumul_rows.append(tok)

            # 본문 가상화: 태그는 태그만 보존, 정적 경계는 정확한 단일 문구로 재구성, 나머지는 가상문구
            for t_elem in root.xpath('//*[local-name()="t"]'):
                txt = (t_elem.text or "").strip()
                if not txt:
                    continue
                if any(r in txt for r in cumul_rows):
                    continue

                tags = re.findall(r'\{\{[^{}]+\}\}', txt)
                if tags:
                    # 치환 태그와 일반 텍스트가 섞인 노드는 태그만 보존하고 나머지는 가상화
                    t_elem.text = " " + " ".join(tags)
                    continue

                matched = False
                for kw, exact_val in EXACT_BOUNDARIES.items():
                    if kw in txt:
                        # 불필요한 원문 잔존 없이 정확한 정적 경계 문구로만 치환
                        t_elem.text = exact_val
                        matched = True
                        break

                if not matched:
                    t_elem.text = "가상문구"

            sanitized_sec = E.tostring(root, encoding="utf-8")

            # content.hpf에 가상 바이너리 아이템 등록
            if '<opf:item id="synth_dummy"' not in content_hpf:
                content_hpf = content_hpf.replace(
                    '</opf:manifest>',
                    '<opf:item id="synth_dummy" href="BinData/synth_dummy.png" media-type="image/png" isEmbeded="1"/></opf:manifest>'
                )

            # 필요한 파일만 명시적으로 포함 (원본 Preview, 원본 BinData 복사 배제, 직접 만든 가상 바이너리 주입)
            with zipfile.ZipFile(dest_template, "w") as z:
                z.writestr("mimetype", "application/hwp+zip", compress_type=zipfile.ZIP_STORED)
                z.writestr("Contents/header.xml", header_xml)
                z.writestr("Contents/section0.xml", sanitized_sec)
                z.writestr("Contents/content.hpf", content_hpf.encode("utf-8"))
                z.writestr("settings.xml", settings_xml)
                z.writestr("version.xml", version_xml)
                z.writestr("META-INF/container.xml", container_xml)
                z.writestr("BinData/synth_dummy.png", SYNTH_PNG)

            return cumul_rows, list(EXACT_BOUNDARIES.values())

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            synth_tmpl = tmp / "synth_template.hwpx"
            cumul_rows, exact_boundary_values = create_synthetic_template(template_path, synth_tmpl)
            self.assertEqual(len(cumul_rows), 7, "가상 누적 명단 행수가 7개가 아님")

            # [반례 검증] 정적 경계 뒤에 원문이 덧붙은 형태가 통과하지 못하도록 전수 검증
            with zipfile.ZipFile(synth_tmpl) as z_check:
                check_root = E.fromstring(z_check.read("Contents/section0.xml"))
                for t_node in check_root.xpath('//*[local-name()="t"]'):
                    t_str = (t_node.text or "").strip()
                    if not t_str:
                        continue
                    # 허용되는 형태: 정확한 경계 문구, 누적 가상행, 태그 전용, 또는 '가상문구'
                    is_exact_boundary = t_str in exact_boundary_values
                    is_cumul = any(r in t_str for r in cumul_rows)
                    is_tag_only = bool(re.match(r'^(\{\{[^{}]+\}\}\s*)+$', t_str))
                    is_pure_synth = (t_str == "가상문구")
                    self.assertTrue(
                        is_exact_boundary or is_cumul or is_tag_only or is_pure_synth,
                        f"불필요한 원문이 붙은 비정상 노드 발견: {repr(t_str)}"
                    )

            engine = HwpxEngine(synth_tmpl, logo_dir=tmp / "no-logos")

            base_data = {
                "metadata": {"date_compact": "20261115", "season": "창조절"},
                "prayer_requests": {
                    "military": "가상군복무교우",
                    "overseas_1": "가상해외교우1",
                    "overseas_2": "가상해외교우2",
                },
                "announcements_sections": self._canonical_6tier(
                    [{"title": "가상소식제목", "content": "가상소식본문"}]
                ),
            }

            ref_other_tables_hash = None

            # ----------------------------------------------------
            # 9가지 조합 검증: 건강 1/2/3행 x 새교우 누락/빈목록/1건입력
            # ----------------------------------------------------
            for h_count in [1, 2, 3]:
                for n_mode, n_val in [("omitted", None), ("empty", []), ("present", ["가상등록교우(가상회, 11/15)"])]:
                    case_label = f"h{h_count}_{n_mode}"
                    data = copy.deepcopy(base_data)
                    for i in range(1, h_count + 1):
                        data["prayer_requests"][f"healing_{i}"] = f"가상치유교우{i}"
                    if n_val is not None:
                        data["new_members"] = n_val

                    out_path = tmp / f"{case_label}.hwpx"
                    old_cwd = os.getcwd()
                    try:
                        # 가상 작업 디렉터리로 격리하여 data/assets/images/* 등 로컬 실사용 에셋 접근을 원천 차단
                        os.chdir(tmp)
                        engine.generate(data, out_path)
                    finally:
                        os.chdir(old_cwd)

                    with zipfile.ZipFile(out_path) as z:
                        sec_bytes = z.read("Contents/section0.xml")
                        sec_text = sec_bytes.decode("utf-8")
                        root = E.fromstring(sec_bytes)
                        styles = get_styles(z.read("Contents/header.xml"))

                        # 실에셋 유입 차단 및 가상 바이너리 보존 검증: BinData에는 synth_dummy.png 단 1개만 존재해야 함
                        bindata_entries = [n for n in z.namelist() if n.startswith("BinData/")]
                        self.assertEqual(
                            bindata_entries,
                            ["BinData/synth_dummy.png"],
                            f"[{case_label}] 로컬 실사용 에셋 유입 또는 가상 바이너리 목록 불일치: {bindata_entries}",
                        )
                        self.assertEqual(z.read("BinData/synth_dummy.png"), SYNTH_PNG, f"[{case_label}] 가상 바이너리 손상")

                    # (1) 명단 상자(Table 10) 밖의 다른 11개 표가 일체 변경되지 않았는지 hash 검증
                    other_tbls = root.xpath('//*[local-name()="tbl"][@id!="1111275716"]')
                    other_tbls_bytes = b"".join(E.tostring(t) for t in other_tbls)
                    curr_hash = hashlib.sha256(other_tbls_bytes).hexdigest()
                    if ref_other_tables_hash is None:
                        ref_other_tables_hash = curr_hash
                    else:
                        self.assertEqual(
                            curr_hash,
                            ref_other_tables_hash,
                            f"[{case_label}] 명단 상자(Table 10) 외의 표에 의도치 않은 변경 발생"
                        )

                    # (2) Table 10 고유 규격 보존 검증 (width 51741, height 38484)
                    tbl10 = root.xpath('//*[local-name()="tbl"][@id="1111275716"]')[0]
                    cell_sz = tbl10.xpath('.//*[local-name()="cellSz"]')[0]
                    self.assertEqual(cell_sz.get("width"), "51741", f"[{case_label}] Table 10 너비 변경됨")
                    self.assertEqual(cell_sz.get("height"), "38484", f"[{case_label}] Table 10 높이 변경됨")

                    # (3) 건강 1~3행의 유실·중복 없음 검증
                    for i in range(1, h_count + 1):
                        tok = f"가상치유교우{i}"
                        self.assertIn(tok, sec_text, f"[{case_label}] {tok} 유실 발생")
                        self.assertEqual(sec_text.count(tok), 1, f"[{case_label}] {tok} 중복 발생")
                    for i in range(h_count + 1, 4):
                        tok = f"가상치유교우{i}"
                        self.assertNotIn(tok, sec_text, f"[{case_label}] 미입력 {tok}가 출력에 잔존")

                    # 군복무, 해외체류 명단 보존 검증
                    self.assertIn("가상군복무교우", sec_text, f"[{case_label}] 군복무 명단 유실")
                    self.assertIn("가상해외교우1", sec_text, f"[{case_label}] 해외체류1 유실")
                    self.assertIn("가상해외교우2", sec_text, f"[{case_label}] 해외체류2 유실")

                    # Table 10 내부 run 수집
                    runs = []
                    for r in tbl10.xpath('.//*[local-name()="run"]'):
                        t = "".join(r.xpath('./*[local-name()="t"]/text()')).strip()
                        cid = r.get("charPrIDRef")
                        st = styles.get(cid, {})
                        runs.append({"text": t, "cid": cid, **st})

                    # (4) 건강회복·군복무·해외체류 명단 본문 Regular(46) 속성 전수 검증
                    expected_prayers = [f"가상치유교우{i}" for i in range(1, h_count + 1)] + [
                        "가상군복무교우", "가상해외교우1", "가상해외교우2"
                    ]
                    for tok in expected_prayers:
                        m_runs = [r for r in runs if tok in r["text"]]
                        self.assertEqual(len(m_runs), 1, f"[{case_label}] {tok} run 개수 오류({len(m_runs)})")
                        m = m_runs[0]
                        self.assertFalse(m["bold"], f"[{case_label}] {tok}에 bold 적용됨 (cid={m['cid']})")
                        self.assertEqual(m["cid"], "46", f"[{case_label}] {tok} cid가 46이 아님 ({m['cid']})")
                        self.assertEqual(m["face"], "경기천년바탕 Regular", f"[{case_label}] {tok} 글꼴 오류")
                        self.assertEqual(m["height"], "1550", f"[{case_label}] {tok} 크기 오류")

                    # (5) 명단 소제목 Bold(66) 보존 검증
                    for subhdr in ["▯건강회복을 위해", "▯해외 체류 중인 교우들을 위해"]:
                        s_runs = [r for r in runs if subhdr in r["text"]]
                        self.assertGreaterEqual(len(s_runs), 1, f"[{case_label}] {subhdr} 소제목 누락")
                        for s in s_runs:
                            self.assertTrue(s["bold"], f"[{case_label}] {subhdr} Bold 손실됨 (cid={s['cid']})")
                            self.assertEqual(s["cid"], "66", f"[{case_label}] {subhdr} cid 오류 ({s['cid']})")
                            self.assertEqual(s["face"], "경기천년바탕 Bold", f"[{case_label}] {subhdr} 글꼴 오류")
                            self.assertEqual(s["height"], "1700", f"[{case_label}] {subhdr} 크기 오류")

                    # [요구사항 3] 누적 명단 전체(7개 행 전수) 순서·개수·내용 보존 검증
                    if n_mode in ["omitted", "empty"]:
                        last_pos = -1
                        for row_idx, r_tok in enumerate(cumul_rows):
                            # 내용 및 손실 여부
                            self.assertIn(r_tok, sec_text, f"[{case_label}] 누적 {row_idx+1}행 유실 발생")
                            # 중복 여부
                            self.assertEqual(sec_text.count(r_tok), 1, f"[{case_label}] 누적 {row_idx+1}행 중복 발생")
                            # 순서 보존 여부
                            curr_pos = sec_text.find(r_tok)
                            self.assertGreater(curr_pos, last_pos, f"[{case_label}] 누적 명단 순서 역전 ({row_idx+1}행)")
                            last_pos = curr_pos
                    else:
                        self.assertIn("가상등록교우(가상회, 11/15)", sec_text, f"[{case_label}] 신규 등록 새교우 누락")
                        self.assertEqual(sec_text.count("가상등록교우(가상회, 11/15)"), 1)
                        nm_runs = [r for r in runs if "가상등록교우" in r["text"]]
                        self.assertEqual(len(nm_runs), 1)
                        self.assertFalse(nm_runs[0]["bold"], f"[{case_label}] 새교우 본문 bold 오류")
                        self.assertEqual(nm_runs[0]["cid"], "21", f"[{case_label}] 새교우 본문 cid 오류")
                        self.assertEqual(nm_runs[0]["face"], "경기천년바탕 Regular")

                    # (7) 일반 소식 제목의 정상적인 Bold(127) 보존 검증
                    ann_title_runs = []
                    for r in root.xpath('//*[local-name()="run"]'):
                        t = "".join(r.xpath('./*[local-name()="t"]/text()')).strip()
                        if "가상소식제목" in t:
                            cid = r.get("charPrIDRef")
                            ann_title_runs.append({"text": t, "cid": cid, **styles.get(cid, {})})
                    self.assertGreaterEqual(len(ann_title_runs), 1, "일반 소식 제목 run 누락")
                    for a in ann_title_runs:
                        self.assertTrue(a["bold"], f"[{case_label}] 일반 소식 제목 Bold 손실됨")
                        self.assertEqual(a["cid"], "127", f"[{case_label}] 일반 소식 제목 cid 오류")

    def test_stage3b_artifact_gate_blocks_defects_and_allows_equivalent_cloned_style(self):
        """3-B 회귀 1: 저장 전 산출물 검증 게이트 결함 차단(1~5) 및 실제 속성 기반 동등 복제 스타일 허용 검증."""
        from lxml import etree as E
        from src.hwpx_engine import HwpxArtifactValidationError, validate_generated_hwpx

        secret_roster_token = "가상비공개치유명단교우"
        secret_body_token = "가상비공개원고본문토큰"

        base_data = {
            "metadata": {"date_compact": "20261115", "season": "창조절"},
            "worship_1": {"sermon_title": "가상설교제목"},
            "new_members": ["가상새교우A(가상회, 11/15)"],
            "prayer_requests": {
                "healing_1": "가상치유교우1",
                "healing_2": "가상치유교우2",
                "healing_3": secret_roster_token,
                "military": "가상군복무교우",
                "overseas_1": "가상해외교우1",
                "overseas_2": "가상해외교우2",
            },
            "announcements_sections": self._canonical_6tier(
                [{"title": "이번주 성서일과", "content": secret_body_token}]
            ),
        }

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)

            # 0. 정상 대조군 및 재입력(204~219 중복 등록 방지) 검증
            ok_tpl = self._write_synthetic_hwpx_fixture(tmp / "ok_tpl.hwpx")
            ok_out = tmp / "ok_out.hwpx"
            res_ok = HwpxEngine(ok_tpl, logo_dir=tmp / "no-logos").generate(base_data, ok_out)
            self.assertTrue(res_ok.is_file())

            refeed_out = tmp / "refeed_out.hwpx"
            res_refeed = HwpxEngine(res_ok, logo_dir=tmp / "no-logos").generate(base_data, refeed_out)
            self.assertTrue(res_refeed.is_file())

            # 0-B. 사용자 편집으로 복제된 동등 Regular 스타일 ID(id="350", 경기천년바탕 Regular, 1550, bold=False) 허용 검증
            cloned_hwpx = tmp / "cloned_style.hwpx"
            with zipfile.ZipFile(res_ok, "r") as zin:
                hdr_root = E.fromstring(zin.read("Contents/header.xml"))
                sec_root = E.fromstring(zin.read("Contents/section0.xml"))
            char_props = hdr_root.xpath('//*[local-name()="charProperties"]')[0]
            cloned_cpr = E.fromstring(
                '<hh:charPr xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head" id="350" height="1550" '
                'textColor="#000000" shadeColor="none" useFontSpace="0" useKerning="0" symMark="NONE" borderFillIDRef="1">'
                '<hh:fontRef hangul="1" latin="1" hanja="1" japanese="1" other="1" symbol="1" user="1"/>'
                '<hh:ratio hangul="96" latin="96" hanja="96" japanese="96" other="96" symbol="96" user="96"/>'
                '<hh:spacing hangul="0" latin="0" hanja="0" japanese="0" other="0" symbol="0" user="0"/>'
                "</hh:charPr>"
            )
            char_props.append(cloned_cpr)
            char_props.set("itemCnt", str(int(char_props.get("itemCnt", "0")) + 1))
            tbl10 = sec_root.xpath('//*[local-name()="tbl"][@id="1111275716"]')[0]
            for run in tbl10.xpath('.//*[local-name()="run"]'):
                txt = "".join(run.xpath('./*[local-name()="t"]/text()')).strip()
                if txt and not txt.startswith("▯"):
                    run.set("charPrIDRef", "350")
            with zipfile.ZipFile(cloned_hwpx, "w") as zout:
                zout.writestr("mimetype", "application/hwp+zip", compress_type=zipfile.ZIP_STORED)
                zout.writestr("Contents/header.xml", E.tostring(hdr_root, encoding="utf-8"))
                zout.writestr("Contents/section0.xml", E.tostring(sec_root, encoding="utf-8"))
            validate_generated_hwpx(cloned_hwpx, base_data)

            # 1-A. 명단 본문 Bold 결함 (charPr 147 적용) -> roster_body_bold 차단
            bold147_hwpx = tmp / "bold147.hwpx"
            sec_147 = E.fromstring(E.tostring(sec_root, encoding="utf-8"))
            for run in sec_147.xpath('//*[local-name()="tbl"][@id="1111275716"]//*[local-name()="run"]'):
                txt = "".join(run.xpath('./*[local-name()="t"]/text()')).strip()
                if "가상치유교우1" in txt:
                    run.set("charPrIDRef", "147")
            with zipfile.ZipFile(bold147_hwpx, "w") as zout:
                zout.writestr("mimetype", "application/hwp+zip", compress_type=zipfile.ZIP_STORED)
                zout.writestr("Contents/header.xml", E.tostring(hdr_root, encoding="utf-8"))
                zout.writestr("Contents/section0.xml", E.tostring(sec_147, encoding="utf-8"))
            with self.assertRaises(HwpxArtifactValidationError) as ctx_147:
                validate_generated_hwpx(bold147_hwpx, base_data)
            self.assertIn("roster_body_bold", {i["check"] for i in ctx_147.exception.issues})

            # 1-B. ID는 46이지만 header.xml에서 실제 속성이 Bold로 정의된 경우 -> 엔진 저장 전 차단 & 파일 미생성
            tpl_46_bold = self._write_synthetic_hwpx_fixture(tmp / "tpl_46_bold.hwpx", override_46_bold=True)
            out_46_bold = tmp / "out_46_bold.hwpx"
            with self.assertRaises(HwpxArtifactValidationError) as ctx_46b:
                HwpxEngine(tpl_46_bold, logo_dir=tmp / "no-logos").generate(base_data, out_46_bold)
            self.assertFalse(out_46_bold.exists())
            self.assertIn("roster_body_bold", {i["check"] for i in ctx_46b.exception.issues})
            self.assertNotIn(secret_roster_token, str(ctx_46b.exception))

            # 2-A. healing_3 3행 유실 (new_members 미입력 경로에서 템플릿의 {{healing_prayer_3}} 슬롯 누락) -> roster_content_missing 차단
            data_no_nm = dict(base_data)
            data_no_nm.pop("new_members")
            tpl_no_h3 = self._write_synthetic_hwpx_fixture(tmp / "tpl_no_h3.hwpx", include_healing3_slot=False)
            out_no_h3 = tmp / "out_no_h3.hwpx"
            with self.assertRaises(HwpxArtifactValidationError) as ctx_h3:
                HwpxEngine(tpl_no_h3, logo_dir=tmp / "no-logos").generate(data_no_nm, out_no_h3)
            self.assertFalse(out_no_h3.exists())
            h3_checks = {i["check"] for i in ctx_h3.exception.issues}
            self.assertIn("roster_content_missing", h3_checks)
            self.assertTrue(any("prayer_requests.healing_3" in i["detail"] for i in ctx_h3.exception.issues))
            self.assertNotIn(secret_roster_token, str(ctx_h3.exception))

            # 2-B. 명단 행 의도치 않은 중복 -> roster_content_duplicate 차단
            dup_roster_hwpx = tmp / "dup_roster.hwpx"
            sec_dup = E.fromstring(E.tostring(sec_root, encoding="utf-8"))
            sub_dup = sec_dup.xpath('//*[local-name()="tbl"][@id="1111275716"]//*[local-name()="subList"]')[0]
            for p_el in list(sub_dup):
                if "가상치유교우2" in "".join(p_el.itertext()):
                    sub_dup.insert(list(sub_dup).index(p_el) + 1, E.fromstring(E.tostring(p_el, encoding="utf-8")))
                    break
            with zipfile.ZipFile(dup_roster_hwpx, "w") as zout:
                zout.writestr("mimetype", "application/hwp+zip", compress_type=zipfile.ZIP_STORED)
                zout.writestr("Contents/header.xml", E.tostring(hdr_root, encoding="utf-8"))
                zout.writestr("Contents/section0.xml", E.tostring(sec_dup, encoding="utf-8"))
            with self.assertRaises(HwpxArtifactValidationError) as ctx_dup_r:
                validate_generated_hwpx(dup_roster_hwpx, base_data)
            self.assertIn("roster_content_duplicate", {i["check"] for i in ctx_dup_r.exception.issues})

            # 3-A. charPr ID 중복 -> charpr_duplicate 차단
            dup_cpr_xml = (
                '<hh:charPr id="46" height="1550" textColor="#000000" shadeColor="none" '
                'useFontSpace="0" useKerning="0" symMark="NONE" borderFillIDRef="1">'
                '<hh:fontRef hangul="1" latin="1" hanja="1" japanese="1" other="1" symbol="1" user="1"/>'
                "</hh:charPr>"
            )
            tpl_dup_cpr = self._write_synthetic_hwpx_fixture(tmp / "tpl_dup_cpr.hwpx", extra_charprs=dup_cpr_xml)
            out_dup_cpr = tmp / "out_dup_cpr.hwpx"
            with self.assertRaises(HwpxArtifactValidationError) as ctx_dc:
                HwpxEngine(tpl_dup_cpr, logo_dir=tmp / "no-logos").generate(base_data, out_dup_cpr)
            self.assertFalse(out_dup_cpr.exists())
            self.assertIn("charpr_duplicate", {i["check"] for i in ctx_dc.exception.issues})

            # 3-B. 미정의 charPrIDRef 참조 -> charpr_undefined_ref 차단
            tpl_undef_cpr = self._write_synthetic_hwpx_fixture(
                tmp / "tpl_undef_cpr.hwpx",
                extra_section_xml='<ns1:p id="0" paraPrIDRef="0"><ns1:run charPrIDRef="999"><ns1:t>가상문구</ns1:t></ns1:run></ns1:p>',
            )
            out_undef_cpr = tmp / "out_undef_cpr.hwpx"
            with self.assertRaises(HwpxArtifactValidationError) as ctx_uc:
                HwpxEngine(tpl_undef_cpr, logo_dir=tmp / "no-logos").generate(base_data, out_undef_cpr)
            self.assertFalse(out_undef_cpr.exists())
            self.assertIn("charpr_undefined_ref", {i["check"] for i in ctx_uc.exception.issues})

            # 4-A & 4-B. section0.xml / header.xml XML 문법 깨짐 -> xml_syntax 차단
            tpl_bad_sec = self._write_synthetic_hwpx_fixture(
                tmp / "tpl_bad_sec.hwpx",
                raw_section_xml='<?xml version="1.0" encoding="UTF-8"?><ns1:sec xmlns:ns1="http://www.hancom.co.kr/hwpml/2011/paragraph"><ns1:p></ns1:sec>',
            )
            out_bad_sec = tmp / "out_bad_sec.hwpx"
            with self.assertRaises(HwpxArtifactValidationError) as ctx_bs:
                HwpxEngine(tpl_bad_sec, logo_dir=tmp / "no-logos").generate(base_data, out_bad_sec)
            self.assertFalse(out_bad_sec.exists())
            self.assertIn("xml_syntax", {i["check"] for i in ctx_bs.exception.issues})

            tpl_bad_hdr = self._write_synthetic_hwpx_fixture(
                tmp / "tpl_bad_hdr.hwpx",
                raw_header_xml='<?xml version="1.0" encoding="UTF-8"?><hh:head xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head"><hh:refList></hh:head>',
            )
            out_bad_hdr = tmp / "out_bad_hdr.hwpx"
            with self.assertRaises(HwpxArtifactValidationError) as ctx_bh:
                HwpxEngine(tpl_bad_hdr, logo_dir=tmp / "no-logos").generate(base_data, out_bad_hdr)
            self.assertFalse(out_bad_hdr.exists())
            self.assertIn("xml_syntax", {i["check"] for i in ctx_bh.exception.issues})

            # 5-A. 경계 불일치로 요청한 소식 영역 미반영 -> boundary_substitution_failed 차단
            tpl_no_ann = self._write_synthetic_hwpx_fixture(tmp / "tpl_no_ann.hwpx", include_ann_boundary=False)
            out_no_ann = tmp / "out_no_ann.hwpx"
            with self.assertRaises(HwpxArtifactValidationError) as ctx_na:
                HwpxEngine(tpl_no_ann, logo_dir=tmp / "no-logos").generate(base_data, out_no_ann)
            self.assertFalse(out_no_ann.exists())
            self.assertIn("boundary_substitution_failed", {i["check"] for i in ctx_na.exception.issues})
            self.assertNotIn(secret_body_token, str(ctx_na.exception))

            # 5-B. 경계 불일치로 요청한 명단 상자(Table 10) 미반영 -> roster_boundary_missing 차단
            tpl_no_t10 = self._write_synthetic_hwpx_fixture(tmp / "tpl_no_t10.hwpx", include_table10=False)
            out_no_t10 = tmp / "out_no_t10.hwpx"
            with self.assertRaises(HwpxArtifactValidationError) as ctx_nt10:
                HwpxEngine(tpl_no_t10, logo_dir=tmp / "no-logos").generate(base_data, out_no_t10)
            self.assertFalse(out_no_t10.exists())
            self.assertIn("roster_boundary_missing", {i["check"] for i in ctx_nt10.exception.issues})

            # 5-C. 미치환 태그({{...}}) 잔존 -> unreplaced_placeholder 차단
            leftover_tag_hwpx = tmp / "leftover_tag.hwpx"
            sec_tag = E.fromstring(E.tostring(sec_root, encoding="utf-8"))
            first_t = sec_tag.xpath('//*[local-name()="t"]')[0]
            first_t.text = "{{미치환필수태그}}"
            with zipfile.ZipFile(leftover_tag_hwpx, "w") as zout:
                zout.writestr("mimetype", "application/hwp+zip", compress_type=zipfile.ZIP_STORED)
                zout.writestr("Contents/header.xml", E.tostring(hdr_root, encoding="utf-8"))
                zout.writestr("Contents/section0.xml", E.tostring(sec_tag, encoding="utf-8"))
            with self.assertRaises(HwpxArtifactValidationError) as ctx_tag:
                validate_generated_hwpx(leftover_tag_hwpx, base_data)
            self.assertIn("unreplaced_placeholder", {i["check"] for i in ctx_tag.exception.issues})

    def test_stage3b_rule34_final_box_and_wording_cases(self):
        """3-B 회귀 2: Rule 34 최종 산출물 공지+공간 안내 박스 동시 검증 및 4가지 문구 표현 케이스 검증."""
        import copy
        from lxml import etree as E
        from scripts.validate_bulletin_facts import validate_bulletin_facts_data
        from src.hwpx_engine import HwpxArtifactValidationError, validate_generated_hwpx

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            tpl = self._write_synthetic_hwpx_fixture(tmp / "rule34_tpl.hwpx")
            engine = HwpxEngine(tpl, logo_dir=tmp / "no-logos")

            # Case 1: dict 형식 월례회 공지 -> 공지 + 공간 안내 박스 정확히 1회씩 생성 및 PASS
            dict_w1 = {
                "metadata": {"date_compact": "20261101", "season": "창조절"},
                "announcements_sections": self._canonical_6tier(
                    [{"title": "부서 월례회", "content": "공동식사 후, 각 부서 공간"}]
                ),
            }
            out_dict_w1 = tmp / "out_dict_w1.hwpx"
            engine.generate(dict_w1, out_dict_w1)
            with zipfile.ZipFile(out_dict_w1, "r") as z:
                xml_dict_w1 = z.read("Contents/section0.xml").decode("utf-8")
            self.assertEqual(xml_dict_w1.count("부서 월례회"), 1)
            self.assertEqual(xml_dict_w1.count('id="1185698824"'), 1)

            # Case 2: 문자열 형식 월례회 공지(1주차/2주차) -> 원본 불변 정규화 후 공지 + 공간 안내 박스 모두 렌더링 및 PASS
            for date_compact, str_notice, expected_title, box_id in [
                ("20261101", "부서 월례회: 공동식사 후, 각 부서 공간", "부서 월례회", 'id="1185698824"'),
                ("20261108", "신도회 월례회: 공동식사 후, 각 신도회 모임 공간", "신도회 월례회", 'id="1137471996"'),
            ]:
                str_data = {
                    "metadata": {"date_compact": date_compact, "season": "창조절"},
                    "announcements_sections": self._canonical_6tier([str_notice]),
                }
                snapshot = copy.deepcopy(str_data)
                out_str = tmp / f"out_str_{date_compact}.hwpx"
                engine.generate(str_data, out_str)
                self.assertEqual(str_data, snapshot, "호출자 원본 문자열 항목이 변경되면 안 됨")
                with zipfile.ZipFile(out_str, "r") as z:
                    xml_str = z.read("Contents/section0.xml").decode("utf-8")
                self.assertEqual(xml_str.count(expected_title), 1)
                self.assertEqual(xml_str.count(box_id), 1)

            # Case 3: 관련 단어만 포함된 다른 공지('부서 월례회 자료 안내') -> Rule 34 충족으로 오인 금지
            related_only_data = {
                "metadata": {"date_compact": "20261101", "season": "창조절"},
                "announcements_sections": self._canonical_6tier(
                    [{"title": "부서 월례회 자료 안내", "content": "사무실 비치"}]
                ),
            }
            # (3-a) AUTO 보정 전 직접 데이터 검사에서는 Rule 34 누락 ERROR가 발생해야 함
            raw_issues = validate_bulletin_facts_data(related_only_data, check_online_scripture=False)
            self.assertIn(
                "매월 1주 정례 모임 누락 (Rule 34)",
                {i["category"] for i in raw_issues if i["level"] == "ERROR"},
            )
            # (3-b) 엔진 전체 실행 시에는 실제 '부서 월례회' 공지와 공간 안내 박스가 AUTO 보정되어 함께 출력되어야 함
            out_related_auto = tmp / "out_related_auto.hwpx"
            engine.generate(related_only_data, out_related_auto)
            with zipfile.ZipFile(out_related_auto, "r") as z:
                hdr_bytes = z.read("Contents/header.xml")
                sec_auto_bytes = z.read("Contents/section0.xml")
            sec_auto_txt = sec_auto_bytes.decode("utf-8")
            self.assertIn("부서 월례회 자료 안내", sec_auto_txt)
            self.assertIn('id="1185698824"', sec_auto_txt)

            # (3-c) 산출물에 '부서 월례회 자료 안내'만 있고 실제 월례회 공지/박스가 없으면 산출물 검증 게이트가 BLOCK해야 함
            fake_related_hwpx = tmp / "fake_related_only.hwpx"
            sec_fake = E.fromstring(sec_auto_bytes)
            for p_el in list(sec_fake):
                p_txt = "".join(p_el.itertext())
                if "공동식사 후, 각 부서 공간" in p_txt or p_el.xpath('.//*[local-name()="tbl"][@id="1185698824"]'):
                    sec_fake.remove(p_el)
            with zipfile.ZipFile(fake_related_hwpx, "w") as zout:
                zout.writestr("mimetype", "application/hwp+zip", compress_type=zipfile.ZIP_STORED)
                zout.writestr("Contents/header.xml", hdr_bytes)
                zout.writestr("Contents/section0.xml", E.tostring(sec_fake, encoding="utf-8"))
            with self.assertRaises(HwpxArtifactValidationError) as ctx_rel:
                validate_generated_hwpx(fake_related_hwpx, related_only_data)
            rel_checks = {i["check"] for i in ctx_rel.exception.issues}
            self.assertIn("rule34_notice_missing", rel_checks)
            self.assertIn("rule34_box_missing", rel_checks)

            # Case 4: 공지는 있으나 공간 안내 박스가 누락된 산출물 / 박스는 있으나 공지가 누락된 산출물 -> 각각 BLOCK
            no_box_hwpx = tmp / "no_box.hwpx"
            sec_no_box = E.fromstring(sec_auto_bytes)
            for p_el in list(sec_no_box):
                if p_el.xpath('.//*[local-name()="tbl"][@id="1185698824"]'):
                    sec_no_box.remove(p_el)
            with zipfile.ZipFile(no_box_hwpx, "w") as zout:
                zout.writestr("mimetype", "application/hwp+zip", compress_type=zipfile.ZIP_STORED)
                zout.writestr("Contents/header.xml", hdr_bytes)
                zout.writestr("Contents/section0.xml", E.tostring(sec_no_box, encoding="utf-8"))
            with self.assertRaises(HwpxArtifactValidationError) as ctx_nb:
                validate_generated_hwpx(no_box_hwpx, dict_w1)
            self.assertEqual({i["check"] for i in ctx_nb.exception.issues}, {"rule34_box_missing"})

            no_notice_hwpx = tmp / "no_notice.hwpx"
            sec_no_notice = E.fromstring(sec_auto_bytes)
            for p_el in list(sec_no_notice):
                p_txt = "".join(p_el.itertext())
                if "공동식사 후, 각 부서 공간" in p_txt or "부서 월례회 자료 안내" in p_txt:
                    sec_no_notice.remove(p_el)
            with zipfile.ZipFile(no_notice_hwpx, "w") as zout:
                zout.writestr("mimetype", "application/hwp+zip", compress_type=zipfile.ZIP_STORED)
                zout.writestr("Contents/header.xml", hdr_bytes)
                zout.writestr("Contents/section0.xml", E.tostring(sec_no_notice, encoding="utf-8"))
            with self.assertRaises(HwpxArtifactValidationError) as ctx_nn:
                validate_generated_hwpx(
                    no_notice_hwpx,
                    {
                        "metadata": {"date_compact": "20261101", "season": "창조절"},
                        "announcements_sections": self._canonical_6tier([]),
                    },
                )
            self.assertEqual({i["check"] for i in ctx_nn.exception.issues}, {"rule34_notice_missing"})

    def test_stage3b_failure_handling_preserves_existing_file_and_permission_fallback(self):
        """3-B 회귀 3: 기존 파일 덮어쓰기 방지, 부분 쓰기 후 OSError 안전 정리, PermissionError/버전 충돌 보존, 검증 실패 차단 검증."""
        import contextlib
        import io
        import sys
        from unittest.mock import patch
        import yaml
        import src.hwpx_engine as hwpx_mod
        from src.hwpx_engine import HwpxArtifactValidationError
        from src.main import main as cli_main
        from src.reviewer.cross_week import CrossWeekComparator

        secret_name = "가상보호대상교우성명"
        secret_manuscript = "가상보호대상소식본문문장"

        payload = {
            "metadata": {"date_compact": "20261115", "season": "창조절"},
            "worship_1": {
                "choir_song_title": "가상찬양",
                "scripture": "창세기 1:1 (1쪽)",
                "sermon_title": "가상설교",
            },
            "duties": {
                "w1": {
                    "presider": "가상인도",
                    "pastoral_prayer": "가상기도",
                    "scripture_reader": "가상봉독",
                    "preacher": "가상설교",
                    "thanks_prayer": "가상감사",
                }
            },
            "prayer_requests": {
                "healing_1": "가상치유1",
                "healing_2": "가상치유2",
                "healing_3": secret_name,
            },
            "announcements_sections": self._canonical_6tier(
                [{"title": "가상당일모임", "content": f"11/15(일) 13:00 {secret_manuscript}"}]
            ),
        }

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            bad_tpl = self._write_synthetic_hwpx_fixture(tmp / "bad_tpl.hwpx", include_healing3_slot=False)
            good_tpl = self._write_synthetic_hwpx_fixture(tmp / "good_tpl.hwpx", include_healing3_slot=True)

            out_dir = tmp / "out"
            out_dir.mkdir()
            existing_target = out_dir / "[주보] 20261115.hwpx"
            sentinel_bytes = b"EXISTING_VALID_HWPX_SENTINEL"
            existing_target.write_bytes(sentinel_bytes)

            # 1. 산출물 검증 실패 시: 실제 validate_generated_hwpx 도달 확인, 파일 미생성, 기존 파일 바이트 보존, 완료 메시지 미출력, 개인정보 비노출
            real_validate = hwpx_mod.validate_generated_hwpx
            validation_calls = []

            def spy_validate(hwpx_path, data, fallback_stem=""):
                validation_calls.append(Path(hwpx_path).name)
                return real_validate(hwpx_path, data, fallback_stem=fallback_stem)

            with patch("src.hwpx_engine.validate_generated_hwpx", side_effect=spy_validate):
                with self.assertRaises(HwpxArtifactValidationError) as eng_ctx:
                    HwpxEngine(bad_tpl, logo_dir=tmp / "no-logos").generate(payload, existing_target)
            self.assertEqual(len(validation_calls), 1, "산출물 검증 게이트에 실제 도달해야 함")
            self.assertEqual(existing_target.read_bytes(), sentinel_bytes)
            self.assertEqual(list(out_dir.glob("*_v*.hwpx")), [])
            self.assertEqual(list(out_dir.glob("*.part")), [])
            err_msg = str(eng_ctx.exception)
            self.assertIn("roster_content_missing", err_msg)
            self.assertNotIn(secret_name, err_msg)
            self.assertNotIn(secret_manuscript, err_msg)

            downloads = tmp / "Downloads"
            downloads.mkdir()
            session_file = downloads / "2026 11월 정기당회.hwp"
            session_file.touch()

            yaml_path = tmp / "bulletin_20261115.yaml"
            manifest_path = tmp / "bulletin_20261115_manifest.yaml"
            yaml_path.write_text(yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8")
            manifest_path.write_text(
                yaml.safe_dump(
                    {"source_manifest": {"session_material": {"file_path": str(session_file)}}},
                    allow_unicode=True,
                ),
                encoding="utf-8",
            )

            cli_buf = io.StringIO()
            cli_argv_bad = [
                "main",
                "--data",
                str(yaml_path),
                "--engine",
                "hwpx",
                "--hwpx-template",
                str(bad_tpl),
                "--output",
                str(out_dir),
                "--no-version",
            ]
            with contextlib.redirect_stdout(cli_buf), patch.object(
                CrossWeekComparator, "_find_and_load_prev_bulletin", return_value=None
            ), patch(
                "src.main.find_latest_session_material", return_value={"file_path": str(session_file)}
            ), patch.object(sys, "argv", cli_argv_bad):
                with self.assertRaises(SystemExit) as cli_ctx:
                    cli_main()
                self.assertEqual(cli_ctx.exception.code, 1)

            cli_stdout = cli_buf.getvalue()
            self.assertEqual(existing_target.read_bytes(), sentinel_bytes)
            self.assertEqual(list(out_dir.glob("*_v*.hwpx")), [])
            self.assertNotIn("✅ HWPX 인쇄본 생성 완료", cli_stdout)
            self.assertNotIn("🎉 모든 주보 생성 작업이 완료되었습니다.", cli_stdout)
            self.assertNotIn(secret_name, cli_stdout)
            self.assertNotIn(secret_manuscript, cli_stdout)

            # 2. 기존 출력 파일이 존재할 때 정상 산출물 내보내기 (엔진 직접 호출 & --no-version CLI 모두 기존 파일 덮어쓰기 금지)
            saved_direct = HwpxEngine(good_tpl, logo_dir=tmp / "no-logos").generate(payload, existing_target)
            self.assertEqual(existing_target.read_bytes(), sentinel_bytes, "기존 파일이 덮어써지면 안 됨")
            self.assertEqual(saved_direct, out_dir / "[주보] 20261115_v2.hwpx")
            self.assertTrue(saved_direct.is_file())
            v2_bytes = saved_direct.read_bytes()
            self.assertNotEqual(v2_bytes, sentinel_bytes)

            cli_ok_buf = io.StringIO()
            cli_argv_good_no_ver = [
                "main",
                "--data",
                str(yaml_path),
                "--engine",
                "hwpx",
                "--hwpx-template",
                str(good_tpl),
                "--output",
                str(out_dir),
                "--no-version",
            ]
            with contextlib.redirect_stdout(cli_ok_buf), patch.object(
                CrossWeekComparator, "_find_and_load_prev_bulletin", return_value=None
            ), patch(
                "src.main.find_latest_session_material", return_value={"file_path": str(session_file)}
            ), patch.object(sys, "argv", cli_argv_good_no_ver):
                cli_main()

            self.assertEqual(existing_target.read_bytes(), sentinel_bytes, "--no-version에서도 기존 파일 보존")
            self.assertEqual(saved_direct.read_bytes(), v2_bytes, "기존 _v2 파일도 보존")
            saved_v3 = out_dir / "[주보] 20261115_v3.hwpx"
            self.assertTrue(saved_v3.is_file(), "충돌 없는 새 버전(_v3)으로 확정되어야 함")
            self.assertIn("✅ HWPX 인쇄본 생성 완료", cli_ok_buf.getvalue())
            self.assertIn("🎉 모든 주보 생성 작업이 완료되었습니다.", cli_ok_buf.getvalue())

            # 3. 쓰기 도중 일부 바이트(64바이트) 기록 후 OSError 발생: 기존 파일 보존, 불완전 최종 파일 및 임시 파일 미잔존, 완료 메시지 미출력
            partial_dir = tmp / "partial_out"
            partial_dir.mkdir()
            partial_existing = partial_dir / "[주보] 20261115.hwpx"
            partial_existing.write_bytes(sentinel_bytes)

            partial_state = {"reached": False, "written_size": 0, "temp_path": None}

            def fail_after_partial_write(src_path: Path, temp_dst_path: Path, chunk_size: int = 65536) -> None:
                data_chunk = Path(src_path).read_bytes()[:64]
                with open(temp_dst_path, "xb") as f_dst:
                    f_dst.write(data_chunk)
                    f_dst.flush()
                partial_state["reached"] = True
                partial_state["written_size"] = temp_dst_path.stat().st_size
                partial_state["temp_path"] = temp_dst_path
                raise OSError("simulated disk write error after partial bytes")

            with patch.object(HwpxEngine, "_copy_to_temp_export", side_effect=fail_after_partial_write):
                with self.assertRaises(OSError):
                    HwpxEngine(good_tpl, logo_dir=tmp / "no-logos").generate(
                        payload, partial_dir / "[주보] 20261115_new.hwpx"
                    )
            self.assertTrue(partial_state["reached"], "부분 쓰기 실패 지점에 실제 도달해야 함")
            self.assertEqual(partial_state["written_size"], 64)
            self.assertFalse(partial_state["temp_path"].exists(), "실패한 임시 파일은 즉시 정리되어야 함")
            self.assertEqual(partial_existing.read_bytes(), sentinel_bytes)
            self.assertEqual(list(partial_dir.iterdir()), [partial_existing])

            # CLI 경로에서 부분 쓰기 OSError 발생 시에도 완료 메시지가 출력되지 않고 종료 코드 1로 중단되어야 함
            partial_state["reached"] = False
            cli_io_buf = io.StringIO()
            cli_argv_io = [
                "main",
                "--data",
                str(yaml_path),
                "--engine",
                "hwpx",
                "--hwpx-template",
                str(good_tpl),
                "--output",
                str(partial_dir),
                "--no-version",
            ]
            with contextlib.redirect_stdout(cli_io_buf), patch.object(
                CrossWeekComparator, "_find_and_load_prev_bulletin", return_value=None
            ), patch(
                "src.main.find_latest_session_material", return_value={"file_path": str(session_file)}
            ), patch.object(
                HwpxEngine, "_copy_to_temp_export", side_effect=fail_after_partial_write
            ), patch.object(sys, "argv", cli_argv_io):
                with self.assertRaises(SystemExit) as io_ctx:
                    cli_main()
                self.assertEqual(io_ctx.exception.code, 1)
            self.assertTrue(partial_state["reached"])
            self.assertEqual(partial_existing.read_bytes(), sentinel_bytes)
            self.assertEqual(list(partial_dir.iterdir()), [partial_existing])
            self.assertNotIn("✅ HWPX 인쇄본 생성 완료", cli_io_buf.getvalue())
            self.assertNotIn("🎉 모든 주보 생성 작업이 완료되었습니다.", cli_io_buf.getvalue())

            # 4. PermissionError 대체 경로 및 경로 확인 이후 발생한 버전 이름 충돌에서도 기존 파일 덮어쓰기 금지
            locked_dir = tmp / "locked_out"
            locked_dir.mkdir()
            locked_base = locked_dir / "[주보] 20261115.hwpx"
            locked_v2 = locked_dir / "[주보] 20261115_v2.hwpx"
            locked_v3 = locked_dir / "[주보] 20261115_v3.hwpx"
            v2_sentinel = b"EXISTING_V2_CONFLICT_SENTINEL"
            v3_sentinel = b"RACE_CREATED_V3_SENTINEL"
            locked_base.write_bytes(sentinel_bytes)

            real_commit = HwpxEngine._commit_temp_export_no_overwrite
            commit_events = {"perm_error_on_v2": False, "race_created_v3": False}

            def simulated_commit(temp_export: Path, target_path: Path) -> None:
                if target_path.resolve() == locked_v2.resolve() and not commit_events["perm_error_on_v2"]:
                    commit_events["perm_error_on_v2"] = True
                    locked_v2.write_bytes(v2_sentinel)
                    raise PermissionError("simulated lock/permission error on _v2")
                if target_path.resolve() == locked_v3.resolve() and not commit_events["race_created_v3"]:
                    commit_events["race_created_v3"] = True
                    # 경로 확인 이후 다른 프로세스가 _v3 파일을 먼저 생성한 경쟁 상황 재현
                    locked_v3.write_bytes(v3_sentinel)
                return real_commit(temp_export, target_path)

            # (4-a) 불량 산출물은 커밋 단계에 도달하기 전에 차단되므로 대체 파일도 생성되지 않음
            with patch.object(HwpxEngine, "_commit_temp_export_no_overwrite", side_effect=simulated_commit):
                with self.assertRaises(HwpxArtifactValidationError):
                    HwpxEngine(bad_tpl, logo_dir=tmp / "no-logos").generate(payload, locked_base)
            self.assertFalse(commit_events["perm_error_on_v2"])
            self.assertEqual(locked_base.read_bytes(), sentinel_bytes)
            self.assertEqual(list(locked_dir.glob("*_v*.hwpx")), [])

            # (4-b) 정상 산출물: base 존재 -> _v2 PermissionError -> _v3 사후 파일 생성 충돌 -> _v4로 안전 확정 (기존 파일 전수 보존)
            with patch.object(HwpxEngine, "_commit_temp_export_no_overwrite", side_effect=simulated_commit):
                final_saved = HwpxEngine(good_tpl, logo_dir=tmp / "no-logos").generate(payload, locked_base)
            self.assertTrue(commit_events["perm_error_on_v2"], "_v2 PermissionError 지점에 실제 도달해야 함")
            self.assertTrue(commit_events["race_created_v3"], "_v3 사후 생성 충돌 지점에 실제 도달해야 함")
            self.assertEqual(final_saved, locked_dir / "[주보] 20261115_v4.hwpx")
            self.assertTrue(final_saved.is_file())
            self.assertEqual(locked_base.read_bytes(), sentinel_bytes)
            self.assertEqual(locked_v2.read_bytes(), v2_sentinel)
            self.assertEqual(locked_v3.read_bytes(), v3_sentinel)
            self.assertEqual(list(locked_dir.glob("*.part")), [])

    def test_stage3b_persistent_permission_error_terminates_with_oserror(self):
        """3-B 회귀 4: 지속적인 PermissionError 발생 시 무한 루프 없이 유한 횟수 내 OSError 종료, 기존 바이트 보존 및 임시 파일 정리 검증."""
        import contextlib
        import io
        import sys
        from unittest.mock import patch
        import yaml
        from src.hwpx_engine import HwpxEngine
        from src.main import main as cli_main
        from src.reviewer.cross_week import CrossWeekComparator

        payload = {
            "metadata": {"date_compact": "20261115", "season": "창조절"},
            "worship_1": {
                "choir_song_title": "가상찬양",
                "scripture": "창세기 1:1 (1쪽)",
                "sermon_title": "가상설교",
            },
            "duties": {
                "w1": {
                    "presider": "가상인도",
                    "pastoral_prayer": "가상기도",
                    "scripture_reader": "가상봉독",
                    "preacher": "가상설교",
                    "thanks_prayer": "가상감사",
                }
            },
            "prayer_requests": {
                "healing_1": "가상치유1",
                "healing_2": "가상치유2",
                "healing_3": "가상치유3",
            },
            "announcements_sections": self._canonical_6tier(
                [{"title": "가상모임", "content": "11/15(일) 13:00 가상내용"}]
            ),
        }

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            good_tpl = self._write_synthetic_hwpx_fixture(tmp / "good_tpl.hwpx", include_healing3_slot=True)

            out_dir = tmp / "persistent_perm_out"
            out_dir.mkdir()
            base_hwpx = out_dir / "[주보] 20261115.hwpx"
            sentinel_bytes = b"EXISTING_ORIGINAL_BYTES_SENTINEL"
            base_hwpx.write_bytes(sentinel_bytes)

            commit_attempts = []

            def always_fail_commit(temp_export: Path, target_path: Path) -> None:
                commit_attempts.append(target_path.name)
                if len(commit_attempts) > 40:
                    raise RuntimeError("무한 루프 감지: 40회 초과 시도됨")
                raise PermissionError(f"Simulated persistent PermissionError on {target_path.name}")

            # 1. 엔진 직접 호출 시: 유한 횟수(<= 20) 내 OSError 발생, 기존 파일 보존, 임시 파일 정리
            with patch.object(HwpxEngine, "_commit_temp_export_no_overwrite", side_effect=always_fail_commit):
                with self.assertRaises(OSError) as eng_ctx:
                    HwpxEngine(good_tpl, logo_dir=tmp / "no-logos").generate(payload, base_hwpx)

            self.assertIn("내보내기 대상 파일 확정 실패", str(eng_ctx.exception))
            self.assertGreater(len(commit_attempts), 0, "커밋 시도 함수가 최소 1회 이상 호출되어야 함")
            self.assertLessEqual(len(commit_attempts), 20, "최대 시도 횟수를 초과해 무한 루프를 돌면 안 됨")
            self.assertEqual(base_hwpx.read_bytes(), sentinel_bytes, "기존 파일 바이트가 온전히 보존되어야 함")
            self.assertEqual(list(out_dir.glob("*_v*.hwpx")), [], "새 파일이 남겨져서는 안 됨")
            self.assertEqual(list(out_dir.glob("*.part")), [], "임시 .part 파일이 정리되어야 함")

            # 2. CLI 호출 시: exit code 1, 오류 메시지 출력, 완료 메시지 미출력, 기존 파일 보존, 임시 파일 정리
            downloads = tmp / "Downloads"
            downloads.mkdir()
            session_file = downloads / "2026 11월 정기당회.hwp"
            session_file.touch()

            yaml_path = tmp / "bulletin_20261115.yaml"
            manifest_path = tmp / "bulletin_20261115_manifest.yaml"
            yaml_path.write_text(yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8")
            manifest_path.write_text(
                yaml.safe_dump(
                    {"source_manifest": {"session_material": {"file_path": str(session_file)}}},
                    allow_unicode=True,
                ),
                encoding="utf-8",
            )

            cli_attempts = []

            def cli_always_fail_commit(temp_export: Path, target_path: Path) -> None:
                cli_attempts.append(target_path.name)
                if len(cli_attempts) > 40:
                    raise RuntimeError("무한 루프 감지: 40회 초과 시도됨")
                raise PermissionError(f"Simulated persistent PermissionError on {target_path.name}")

            cli_io_buf = io.StringIO()
            cli_argv = [
                "main",
                "--data",
                str(yaml_path),
                "--engine",
                "hwpx",
                "--hwpx-template",
                str(good_tpl),
                "--output",
                str(out_dir),
                "--no-version",
            ]
            with contextlib.redirect_stdout(cli_io_buf), patch.object(
                CrossWeekComparator, "_find_and_load_prev_bulletin", return_value=None
            ), patch(
                "src.main.find_latest_session_material", return_value={"file_path": str(session_file)}
            ), patch.object(
                HwpxEngine, "_commit_temp_export_no_overwrite", side_effect=cli_always_fail_commit
            ), patch.object(sys, "argv", cli_argv):
                with self.assertRaises(SystemExit) as cli_ctx:
                    cli_main()
                self.assertEqual(cli_ctx.exception.code, 1)

            self.assertIn("[최종 HWPX 파일 확정 실패]", cli_io_buf.getvalue())
            self.assertNotIn("✅ HWPX 인쇄본 생성 완료", cli_io_buf.getvalue())
            self.assertNotIn("🎉 모든 주보 생성 작업이 완료되었습니다.", cli_io_buf.getvalue())
            self.assertGreater(len(cli_attempts), 0)
            self.assertLessEqual(len(cli_attempts), 20)
            self.assertEqual(base_hwpx.read_bytes(), sentinel_bytes)
            self.assertEqual(list(out_dir.glob("*.part")), [])

    def test_stage3b_logo_gate_aspect_ratio_and_error_handling(self):
        """1면 로고 2종(심볼, 글씨) 왜곡 방지 및 검증 게이트 회귀 테스트:
        1) Pillow 부재 환경에서도 정상 생성
        2) 손상 이미지 크기 판독 실패 시 명시적 오류 차단 및 기존 파일 보존
        3) 이미지 교체 후 이전 크기·배율이 잔존한 경우 최종 산출물 게이트 차단
        4) 지원하는 절기별(창조절, 성령강림절, 사순절) 정상 로고 규격 통과
        """
        import sys
        from unittest.mock import patch
        from lxml import etree
        from src.hwpx_engine import HwpxEngine, validate_generated_hwpx, HwpxArtifactValidationError

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            tpl = self._write_synthetic_hwpx_fixture(tmp / "tpl_with_logos.hwpx", include_logos=True)

            payload_creation = {
                "metadata": {"date_compact": "20261101", "season": "창조절"},
                "worship_1": {"sermon_title": "가상설교"},
                "announcements_sections": self._canonical_6tier([{"title": "가상모임", "content": "11/01(일) 13:00"}]),
            }

            # 1. Pillow 부재 환경(sys.modules['PIL']=None)에서도 표준 PNG 헤더로 정상 크기 판독 및 HWPX 생성
            logo_dir_creation = tmp / "logos_creation"
            logo_dir_creation.mkdir()
            (logo_dir_creation / "주현절, 창조절 (1).png").write_bytes(self._create_synthetic_png(336, 482))
            (logo_dir_creation / "주현절, 창조절 (2).png").write_bytes(self._create_synthetic_png(1084, 373))

            out_creation = tmp / "out_creation.hwpx"
            with patch.dict(sys.modules, {"PIL": None, "PIL.Image": None}):
                eng_no_pil = HwpxEngine(tpl, logo_dir=logo_dir_creation)
                saved_hwpx = eng_no_pil.generate(payload_creation, out_creation)

            self.assertTrue(saved_hwpx.is_file())
            with zipfile.ZipFile(saved_hwpx) as z_check:
                sec0_xml = z_check.read("Contents/section0.xml").decode("utf-8")
                # Rule 11 창조절 목표 규격 검증
                self.assertIn('curSz width="5437" height="7800"', sec0_xml)
                self.assertIn('curSz width="18018" height="6200"', sec0_xml)
                self.assertIn('orgSz width="25200" height="36150"', sec0_xml)
                self.assertIn('orgSz width="81300" height="27975"', sec0_xml)

            # 2. 이미지 판독 실패 시 조용히 넘어가지 않고 명시적 ValueError로 차단 및 기존 파일 보존
            corrupt_logo_dir = tmp / "logos_corrupt"
            corrupt_logo_dir.mkdir()
            (corrupt_logo_dir / "주현절, 창조절 (1).png").write_bytes(b"CORRUPTED_NOT_A_PNG_DATA")
            (corrupt_logo_dir / "주현절, 창조절 (2).png").write_bytes(self._create_synthetic_png(1084, 373))

            existing_file = tmp / "existing_protected.hwpx"
            sentinel_bytes = b"ORIGINAL_BYTES_PRESERVED"
            existing_file.write_bytes(sentinel_bytes)

            eng_corrupt = HwpxEngine(tpl, logo_dir=corrupt_logo_dir)
            with self.assertRaises(ValueError) as err_ctx:
                eng_corrupt.generate(payload_creation, existing_file)
            self.assertIn("로고 이미지 크기 판독 실패", str(err_ctx.exception))
            self.assertEqual(existing_file.read_bytes(), sentinel_bytes, "손상 이미지 차단 시 기존 파일이 보존되어야 함")

            # 3. 이미지 교체 후 이전 크기·배율이 남은 경우 최종 HWPX 검증 게이트에서 차단
            distorted_hwpx = tmp / "distorted.hwpx"
            # 템플릿의 성령강림절 크기(7007x7899, 20542x6080)를 유지한 채 창조절 이미지(336x482, 1084x373)만 BinData에 복사된 비정상 HWPX
            extra_bindata_distorted = {
                "BinData/image3.png": self._create_synthetic_png(336, 482),
                "BinData/image4.png": self._create_synthetic_png(1084, 373),
            }
            self._write_synthetic_hwpx_fixture(
                distorted_hwpx,
                include_logos=True,
                extra_bindata=extra_bindata_distorted,
            )
            with self.assertRaises(HwpxArtifactValidationError) as gate_ctx:
                validate_generated_hwpx(distorted_hwpx, payload_creation)
            distorted_checks = {i["check"] for i in gate_ctx.exception.issues}
            self.assertTrue(
                {"logo_size_mismatch", "logo_ratio_distortion", "logo_orgsz_mismatch"}.intersection(distorted_checks),
                f"의도한 로고 결함이 검증 게이트에서 검출되어야 함: {distorted_checks}",
            )

            # 4. 지원하는 절기별 정상 로고 통과 검증 (창조절, 성령강림절, 사순절)
            # 4-a. 성령강림절
            logo_dir_pentecost = tmp / "logos_pentecost"
            logo_dir_pentecost.mkdir()
            (logo_dir_pentecost / "성령강림절 (1).png").write_bytes(self._create_synthetic_png(251, 283))
            (logo_dir_pentecost / "성령강림절 (2).png").write_bytes(self._create_synthetic_png(700, 207))

            payload_pentecost = {
                "metadata": {"date_compact": "20260524", "season": "성령강림절"},
                "worship_1": {"sermon_title": "가상설교"},
                "announcements_sections": self._canonical_6tier([{"title": "가상모임", "content": "05/24(일) 13:00"}]),
            }
            out_pentecost = tmp / "out_pentecost.hwpx"
            eng_pentecost = HwpxEngine(tpl, logo_dir=logo_dir_pentecost)
            saved_pente = eng_pentecost.generate(payload_pentecost, out_pentecost)
            self.assertTrue(saved_pente.is_file())
            # 검증 게이트 통과 확인 (예외 발생 없음)
            validate_generated_hwpx(saved_pente, payload_pentecost)

            # 4-b. 사순절 (동적 계산 절기)
            logo_dir_lent = tmp / "logos_lent"
            logo_dir_lent.mkdir()
            (logo_dir_lent / "사순절, 대림절 (1).png").write_bytes(self._create_synthetic_png(293, 351))
            (logo_dir_lent / "사순절, 대림절 (2).png").write_bytes(self._create_synthetic_png(704, 197))

            payload_lent = {
                "metadata": {"date_compact": "20260301", "season": "사순절"},
                "worship_1": {"sermon_title": "가상설교"},
                "announcements_sections": self._canonical_6tier([{"title": "가상모임", "content": "03/01(일) 13:00"}]),
            }
            out_lent = tmp / "out_lent.hwpx"
            eng_lent = HwpxEngine(tpl, logo_dir=logo_dir_lent)
            saved_lent = eng_lent.generate(payload_lent, out_lent)
            self.assertTrue(saved_lent.is_file())
            validate_generated_hwpx(saved_lent, payload_lent)


if __name__ == "__main__":
    unittest.main()
