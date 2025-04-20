import pdfplumber
import pandas as pd
import re
from collections import Counter
import openai
import time
import json
import os

# Setting
pdf_path = "../input/your_pdf.pdf"  
excel_path = "../ESG评价体系0322.xlsx"
output_path = "词频统计_含近义词.csv"
openai.api_key = "YOUR_API_KEY"  
model = "gpt-4"

# ========== 1. Loading Qualitative Keywords ==========
def load_keywords_with_synonyms(excel_path):
    xls = pd.ExcelFile(excel_path)
    records = []
    sheet_column_map = {
        'Environment': 'NLP方法',
        'Social': '研究方法',
        'Governance': '研究方法'
    }
    for sheet, col in sheet_column_map.items():
        df = xls.parse(sheet)
        if 'Possible Keywords' in df.columns and col in df.columns:
            for _, row in df.iterrows():
                if pd.notna(row['Possible Keywords']) and str(row[col]).strip() in ['定性', '定性/定量']:
                    for kw in re.split(r',\s*', str(row['Possible Keywords'])):
                        records.append({"keyword": kw.strip(), "type": row[col], "domain": sheet})
    return pd.DataFrame(records)

# ========== 2. Extract full text ==========
def extract_pdf_text(pdf_path):
    all_text = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                all_text.append(text)
    return "\n".join(all_text)

# ========== 3. Generate near-synonym extensions ==========
def get_synonyms_batch(keywords):
    prompt = f"""
Please provide 3 to 5 common synonyms or semantically similar expressions for each of the following ESG-related keywords. 
Return the result in JSON format with this structure:
[
  {{"keyword": "original", "synonyms": ["syn1", "syn2", ...] }},
  ...
]

Keywords:
{chr(10).join(f"- {kw}" for kw in keywords)}
"""
    try:
        response = openai.ChatCompletion.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=1500
        )
        content = response.choices[0].message["content"]
        print("GPT 返回内容：", content)  # ✅ 添加这一行查看返回结果
        return content
    except Exception as e:
        print("❌ GPT 错误：", e)
        return "[]"

# ========== 4. mainstream process ==========
def run():
    print("📘 读取关键词...")
    df_keywords = load_keywords_with_synonyms(excel_path)
    keywords = df_keywords['keyword'].unique().tolist()

    print("💬 生成近义词...")
    synonyms_json = get_synonyms_batch(keywords)

    synonym_map = {}
    try:
        parsed = json.loads(synonyms_json)
        for item in parsed:
            synonym_map[item['keyword']] = [item['keyword']] + item.get('synonyms', [])
    except Exception as e:
        print("⚠️ 同义词解析失败，使用原始关键词", e)
        for k in keywords:
            synonym_map[k] = [k]

    print("📄 读取 PDF 文本...")
    text = extract_pdf_text(pdf_path).lower()

    print("📊 统计词频...")
    freq_data = []
    for keyword in keywords:
        total_count = 0
        matches = []
        for syn in synonym_map.get(keyword, [keyword]):
            pattern = re.escape(syn.lower())
            count = len(re.findall(pattern, text))
            if count > 0:
                matches.append((syn, count))
                total_count += count
        freq_data.append({
            "keyword": keyword,
            "total_frequency": total_count,
            "matched_synonyms": "; ".join(f"{s} ({c})" for s, c in matches)
        })

    df_out = pd.DataFrame(freq_data)

    match = re.search(r"(\d{4})", pdf_path)
    if match:
        pdf_year = match.group(1)
        print("📄 当前文件名：", pdf_path, "→ 提取年份为：", pdf_year)
    else:
        pdf_year = ""
        print("⚠️ 文件名中未找到年份")

    basename = os.path.splitext(os.path.basename(pdf_path))[0]
    output_filename = f"{basename}_定性_结果.csv"

    df_out.to_csv(output_filename, index=False)
    print(f"\n✅ 提取完成，结果已保存至 {output_filename}")

# ========== 执行 ==========
if __name__ == '__main__':
    run()
