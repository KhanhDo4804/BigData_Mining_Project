from pathlib import Path
import zipfile
from xml.sax.saxutils import escape


OUT = Path("Bao_cao_demo_Crypto_Analytics.docx")
NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

SECTIONS = [
    (
        "Demo 1. Dashboard tổng quan",
        "demo_01_dashboard_tong_quan.png",
        [
            "Hiển thị Top ví PageRank cao nhất dưới dạng bảng cuộn.",
            "Hiển thị Top ví nhiều tiền nhất theo tổng Balance bằng biểu đồ cột ngang log-scale.",
            "Hiển thị Top token được giữ nhiều nhất theo số ví, tổng Balance hoặc tổng giao dịch.",
        ],
    ),
    (
        "Demo 2. Tìm kiếm ví và gợi ý token",
        "demo_02_tim_kiem_vi_goi_y_token.png",
        [
            "Nhập User ID để xem portfolio của ví.",
            "Hiển thị token đang nắm giữ và số dư hiện tại.",
            "Hiển thị Top token đáng mua nhất và Top ví uy tín có hành vi giống.",
        ],
    ),
    (
        "Demo 3. Chi tiết ví",
        "demo_03_chi_tiet_vi.png",
        [
            "Hiển thị PageRank, số loại token, tổng giao dịch và thời điểm active gần nhất.",
            "Bảng token trong ví có thể cuộn và lọc theo token.",
            "Biểu đồ phân bổ số dư theo token trong ví.",
        ],
    ),
    (
        "Demo 4. Tìm kiếm token",
        "demo_04_tim_kiem_token.png",
        [
            "Tìm kiếm token bằng Token ID, token address, symbol hoặc name.",
            "Hiển thị thông tin token gồm Token ID, Symbol, tên, decimals, total supply và contract.",
            "Nếu có nhiều kết quả, hệ thống tự lấy kết quả đầu tiên.",
        ],
    ),
    (
        "Demo 5. Biểu đồ giá token theo address",
        "demo_05_bieu_do_gia_token_address.png",
        [
            "Lấy token address từ bảng BIGDATA_DB.STAGING.TOKEN_IN_PROJECT.",
            "Truy vấn dữ liệu OHLCV theo pool DEX của token.",
            "Hiển thị biểu đồ nến giá token theo khung thời gian.",
        ],
    ),
    (
        "Demo 6. Xu hướng thị trường Real-time",
        "demo_06_xu_huong_thi_truong_realtime.png",
        [
            "Hiển thị token hot nhất theo khối lượng trong cửa sổ realtime.",
            "Hiển thị token có số lệnh giao dịch cao nhất.",
            "Biểu đồ Top 10 token theo khối lượng và bảng xếp hạng chi tiết.",
        ],
    ),
    (
        "Demo 7. Phát hiện bất thường Real-time",
        "demo_07_phat_hien_bat_thuong_realtime.png",
        [
            "Hiển thị tổng số cảnh báo, tổng ETH bất thường và giao dịch lớn nhất.",
            "Biểu đồ Top ví rủi ro theo ETH và luồng ETH bất thường.",
            "Bảng danh sách giao dịch bất thường realtime.",
        ],
    ),
]


def paragraph(text="", style=None, align=None):
    ppr = ""
    if style or align:
        parts = []
        if style:
            parts.append(f'<w:pStyle w:val="{style}"/>')
        if align:
            parts.append(f'<w:jc w:val="{align}"/>')
        ppr = "<w:pPr>" + "".join(parts) + "</w:pPr>"
    return f'<w:p>{ppr}<w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>'


def bullet(text):
    return (
        '<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/>'
        '<w:numId w:val="1"/></w:numPr></w:pPr>'
        f'<w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>'
    )


def page_break():
    return '<w:p><w:r><w:br w:type="page"/></w:r></w:p>'


def image_placeholder(filename):
    return (
        '<w:p><w:pPr><w:spacing w:before="160" w:after="80"/></w:pPr>'
        '<w:r><w:rPr><w:b/><w:color w:val="1F4E79"/></w:rPr>'
        f"<w:t>Ảnh demo cần chèn: {escape(filename)}</w:t>"
        "</w:r></w:p>"
        '<w:p><w:pPr><w:pBdr>'
        '<w:top w:val="single" w:sz="8" w:space="1" w:color="A6A6A6"/>'
        '<w:left w:val="single" w:sz="8" w:space="4" w:color="A6A6A6"/>'
        '<w:bottom w:val="single" w:sz="8" w:space="1" w:color="A6A6A6"/>'
        '<w:right w:val="single" w:sz="8" w:space="4" w:color="A6A6A6"/>'
        '</w:pBdr><w:spacing w:before="120" w:after="120"/></w:pPr>'
        '<w:r><w:t xml:space="preserve">[Chèn ảnh chụp màn hình giao diện web tại đây]</w:t></w:r>'
        "</w:p>"
    )


def build_document_xml():
    body = [
        paragraph("BÁO CÁO DEMO HỆ THỐNG CRYPTO ANALYTICS", "Title", "center"),
        paragraph("Chỉ bao gồm phần demo giao diện và chức năng.", None, "center"),
        paragraph(""),
        paragraph("Danh sách ảnh demo cần chụp", "Heading1"),
    ]
    for _, image, _ in SECTIONS:
        body.append(bullet(image))
    body.append(page_break())

    for index, (title, image, bullets) in enumerate(SECTIONS):
        body.append(paragraph(title, "Heading1"))
        for item in bullets:
            body.append(bullet(item))
        body.append(image_placeholder(image))
        if index != len(SECTIONS) - 1:
            body.append(page_break())

    section_props = (
        "<w:sectPr>"
        '<w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134" '
        'w:header="708" w:footer="708" w:gutter="0"/>'
        "</w:sectPr>"
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{NS}"><w:body>'
        + "".join(body)
        + section_props
        + "</w:body></w:document>"
    )


def main():
    styles_xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="{NS}">
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal">
    <w:name w:val="Normal"/>
    <w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial"/><w:sz w:val="24"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Title">
    <w:name w:val="Title"/>
    <w:basedOn w:val="Normal"/>
    <w:pPr><w:spacing w:after="240"/></w:pPr>
    <w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial"/><w:b/><w:sz w:val="36"/><w:color w:val="1F4E79"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading1">
    <w:name w:val="heading 1"/>
    <w:basedOn w:val="Normal"/>
    <w:pPr><w:spacing w:before="240" w:after="160"/></w:pPr>
    <w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial"/><w:b/><w:sz w:val="30"/><w:color w:val="1F4E79"/></w:rPr>
  </w:style>
</w:styles>'''

    numbering_xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:numbering xmlns:w="{NS}">
  <w:abstractNum w:abstractNumId="0">
    <w:multiLevelType w:val="hybridMultilevel"/>
    <w:lvl w:ilvl="0">
      <w:start w:val="1"/>
      <w:numFmt w:val="bullet"/>
      <w:lvlText w:val="•"/>
      <w:lvlJc w:val="left"/>
      <w:pPr><w:ind w:left="720" w:hanging="360"/></w:pPr>
    </w:lvl>
  </w:abstractNum>
  <w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>
</w:numbering>'''

    content_types = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>
</Types>'''

    root_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>'''

    doc_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>
</Relationships>'''

    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as docx:
        docx.writestr("[Content_Types].xml", content_types)
        docx.writestr("_rels/.rels", root_rels)
        docx.writestr("word/_rels/document.xml.rels", doc_rels)
        docx.writestr("word/document.xml", build_document_xml())
        docx.writestr("word/styles.xml", styles_xml)
        docx.writestr("word/numbering.xml", numbering_xml)

    print(OUT.resolve())


if __name__ == "__main__":
    main()
