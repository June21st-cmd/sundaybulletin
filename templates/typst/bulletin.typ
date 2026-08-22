// 주보 Typst 조판 템플릿 (Sunday Bulletin Typst Template)
#set page(
  paper: "a4",
  flipped: true,            // A4 가로 인쇄 (2단 접지용)
  columns: 2,               // 2단 분할
  margin: (x: 12mm, y: 15mm)
)
#set text(font: ("KoPubWorldBatang", "Noto Serif CJK KR", "Batang", "serif"), size: 10pt, lang: "ko")

// [1] 글자 장평(가로 확대) 함수: scaleX와 동일
#let 장평(비율: 120%, 내용) = box(scale(x: 비율, 내용))

// [2] 배분 정렬 함수: 지정된 너비 안에 글자를 균등 분할
#let 배분(너비: 55pt, 텍스트) = {
  let 글자들 = 텍스트.clusters()
  box(width: 너비, {
    for (i, char) in 글자들.enumerate() {
      if i > 0 { h(1fr) }
      char
    }
  })
}

// 주보 헤더
#align(center)[
  #text(size: 16pt, weight: "bold")[#장평(비율: 110%)[주일 예배]] \
  #v(2mm)
  #text(size: 10pt, fill: rgb("#555555"))[2026년 8월 16일 | 성령강림후 제12주]
]

#v(4mm)

// 예배 순서 테이블
#table(
  columns: (70pt, 1fr, 80pt),
  stroke: (x, y) => if y == 0 { (bottom: 1.5pt, stroke: rgb("#2a52be")) } else { (bottom: 0.5pt, stroke: luma(200)) },
  
  [#배분(너비: 55pt)[예배부름]], [인도자], [다함께],
  [#배분(너비: 55pt)[찬송]], [*#장평(비율: 115%)[새찬송가 28장]*], [다함께],
  [#배분(너비: 55pt)[성경봉독]], [누가복음 10:25-37], [인도자],
  [#배분(너비: 55pt)[말씀선포]], [*#장평(비율: 125%)[선한 이웃은 누구인가]*], [담임목사],
  [#배분(너비: 55pt)[봉헌]], [찬송가 50장 1절], [다함께],
  [#배분(너비: 55pt)[축도]], [], [담임목사],
)
