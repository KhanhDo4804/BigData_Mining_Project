$OutPath = Join-Path (Get-Location) "Bao_cao_demo_Crypto_Analytics.docx"
$Namespace = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

$Sections = @(
    @{
        Title = "Demo 1. Dashboard tổng quan"
        Image = "demo_01_dashboard_tong_quan.png"
        Bullets = @(
            "Hiển thị Top ví PageRank cao nhất dưới dạng bảng cuộn.",
            "Hiển thị Top ví nhiều tiền nhất theo tổng Balance bằng biểu đồ cột ngang log-scale.",
            "Hiển thị Top token được giữ nhiều nhất theo số ví, tổng Balance hoặc tổng giao dịch."
        )
    },
    @{
        Title = "Demo 2. Tìm kiếm ví và gợi ý token"
        Image = "demo_02_tim_kiem_vi_goi_y_token.png"
        Bullets = @(
            "Nhập User ID để xem portfolio của ví.",
            "Hiển thị token đang nắm giữ và số dư hiện tại.",
            "Hiển thị Top token đáng mua nhất và Top ví uy tín có hành vi giống."
        )
    },
    @{
        Title = "Demo 3. Chi tiết ví"
        Image = "demo_03_chi_tiet_vi.png"
        Bullets = @(
            "Hiển thị PageRank, số loại token, tổng giao dịch và thời điểm active gần nhất.",
            "Bảng token trong ví có thể cuộn và lọc theo token.",
            "Biểu đồ phân bổ số dư theo token trong ví."
        )
    },
    @{
        Title = "Demo 4. Tìm kiếm token"
        Image = "demo_04_tim_kiem_token.png"
        Bullets = @(
            "Tìm kiếm token bằng Token ID, token address, symbol hoặc name.",
            "Hiển thị thông tin token gồm Token ID, Symbol, tên, decimals, total supply và contract.",
            "Nếu có nhiều kết quả, hệ thống tự lấy kết quả đầu tiên."
        )
    },
    @{
        Title = "Demo 5. Biểu đồ giá token theo address"
        Image = "demo_05_bieu_do_gia_token_address.png"
        Bullets = @(
            "Lấy token address từ bảng BIGDATA_DB.STAGING.TOKEN_IN_PROJECT.",
            "Truy vấn dữ liệu OHLCV theo pool DEX của token.",
            "Hiển thị biểu đồ nến giá token theo khung thời gian."
        )
    },
    @{
        Title = "Demo 6. Xu hướng thị trường Real-time"
        Image = "demo_06_xu_huong_thi_truong_realtime.png"
        Bullets = @(
            "Hiển thị token hot nhất theo khối lượng trong cửa sổ realtime.",
            "Hiển thị token có số lệnh giao dịch cao nhất.",
            "Biểu đồ Top 10 token theo khối lượng và bảng xếp hạng chi tiết."
        )
    },
    @{
        Title = "Demo 7. Phát hiện bất thường Real-time"
        Image = "demo_07_phat_hien_bat_thuong_realtime.png"
        Bullets = @(
            "Hiển thị tổng số cảnh báo, tổng ETH bất thường và giao dịch lớn nhất.",
            "Biểu đồ Top ví rủi ro theo ETH và luồng ETH bất thường.",
            "Bảng danh sách giao dịch bất thường realtime."
        )
    }
)

function Escape-XmlText([string]$Text) {
    return [System.Security.SecurityElement]::Escape($Text)
}

function New-Paragraph([string]$Text, [string]$Style = "", [string]$Align = "") {
    $ppr = ""
    if ($Style -or $Align) {
        $parts = ""
        if ($Style) { $parts += "<w:pStyle w:val=""$Style""/>" }
        if ($Align) { $parts += "<w:jc w:val=""$Align""/>" }
        $ppr = "<w:pPr>$parts</w:pPr>"
    }
    $safe = Escape-XmlText $Text
    return "<w:p>$ppr<w:r><w:t xml:space=""preserve"">$safe</w:t></w:r></w:p>"
}

function New-Bullet([string]$Text) {
    $safe = Escape-XmlText $Text
    return "<w:p><w:pPr><w:numPr><w:ilvl w:val=""0""/><w:numId w:val=""1""/></w:numPr></w:pPr><w:r><w:t xml:space=""preserve"">$safe</w:t></w:r></w:p>"
}

function New-PageBreak() {
    return "<w:p><w:r><w:br w:type=""page""/></w:r></w:p>"
}

function New-ImagePlaceholder([string]$FileName) {
    $safe = Escape-XmlText $FileName
    return "<w:p><w:pPr><w:spacing w:before=""160"" w:after=""80""/></w:pPr><w:r><w:rPr><w:b/><w:color w:val=""1F4E79""/></w:rPr><w:t>Ảnh demo cần chèn: $safe</w:t></w:r></w:p>" +
        "<w:p><w:pPr><w:pBdr><w:top w:val=""single"" w:sz=""8"" w:space=""1"" w:color=""A6A6A6""/><w:left w:val=""single"" w:sz=""8"" w:space=""4"" w:color=""A6A6A6""/><w:bottom w:val=""single"" w:sz=""8"" w:space=""1"" w:color=""A6A6A6""/><w:right w:val=""single"" w:sz=""8"" w:space=""4"" w:color=""A6A6A6""/></w:pBdr><w:spacing w:before=""120"" w:after=""120""/></w:pPr><w:r><w:t xml:space=""preserve"">[Chèn ảnh chụp màn hình giao diện web tại đây]</w:t></w:r></w:p>"
}

$BodyParts = New-Object System.Collections.Generic.List[string]
$BodyParts.Add((New-Paragraph "BÁO CÁO DEMO HỆ THỐNG CRYPTO ANALYTICS" "Title" "center"))
$BodyParts.Add((New-Paragraph "Chỉ bao gồm phần demo giao diện và chức năng." "" "center"))
$BodyParts.Add((New-Paragraph ""))
$BodyParts.Add((New-Paragraph "Danh sách ảnh demo cần chụp" "Heading1"))
foreach ($Section in $Sections) {
    $BodyParts.Add((New-Bullet $Section.Image))
}
$BodyParts.Add((New-PageBreak))

for ($i = 0; $i -lt $Sections.Count; $i++) {
    $Section = $Sections[$i]
    $BodyParts.Add((New-Paragraph $Section.Title "Heading1"))
    foreach ($Item in $Section.Bullets) {
        $BodyParts.Add((New-Bullet $Item))
    }
    $BodyParts.Add((New-ImagePlaceholder $Section.Image))
    if ($i -lt $Sections.Count - 1) {
        $BodyParts.Add((New-PageBreak))
    }
}

$SectionProps = "<w:sectPr><w:pgSz w:w=""11906"" w:h=""16838""/><w:pgMar w:top=""1134"" w:right=""1134"" w:bottom=""1134"" w:left=""1134"" w:header=""708"" w:footer=""708"" w:gutter=""0""/></w:sectPr>"
$DocumentXml = "<?xml version=""1.0"" encoding=""UTF-8"" standalone=""yes""?><w:document xmlns:w=""$Namespace""><w:body>$($BodyParts -join '')$SectionProps</w:body></w:document>"

$StylesXml = @"
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="$Namespace">
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
</w:styles>
"@

$NumberingXml = @"
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:numbering xmlns:w="$Namespace">
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
</w:numbering>
"@

$ContentTypes = @"
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>
</Types>
"@

$RootRels = @"
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>
"@

$DocRels = @"
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>
</Relationships>
"@

if (Test-Path -LiteralPath $OutPath) {
    Remove-Item -LiteralPath $OutPath -Force
}

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$Encoding = New-Object System.Text.UTF8Encoding($false)

function Add-ZipEntry($Zip, [string]$EntryName, [string]$Content) {
    $Entry = $Zip.CreateEntry($EntryName)
    $Stream = $Entry.Open()
    $Writer = New-Object System.IO.StreamWriter($Stream, $Encoding)
    $Writer.Write($Content)
    $Writer.Dispose()
    $Stream.Dispose()
}

$Zip = [System.IO.Compression.ZipFile]::Open($OutPath, [System.IO.Compression.ZipArchiveMode]::Create)
try {
    Add-ZipEntry $Zip "[Content_Types].xml" $ContentTypes
    Add-ZipEntry $Zip "_rels/.rels" $RootRels
    Add-ZipEntry $Zip "word/_rels/document.xml.rels" $DocRels
    Add-ZipEntry $Zip "word/document.xml" $DocumentXml
    Add-ZipEntry $Zip "word/styles.xml" $StylesXml
    Add-ZipEntry $Zip "word/numbering.xml" $NumberingXml
}
finally {
    $Zip.Dispose()
}

Write-Output $OutPath
