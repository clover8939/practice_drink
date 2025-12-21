import csv
import re

# 讀取舊 CSV
input_file = 'quiz_items_export_20251220_234224.csv'
output_file = 'new_upload.csv'

# 用來提取屬性名稱的函數
def extract_attribute_name(sentence_template):
    """
    從敘述句提取屬性名稱
    例如："黑咖啡(M)需要[NUM]ml的咖啡液。" -> "咖啡液"
    """
    # 尋找 "[NUM]" 後面的內容
    match = re.search(r'\[NUM\]\s*([^\d\s][^\d]*?)的\s*([^。，，；；:：""''\"\']*)[。，，；；:：""''\"\'ml\s]*', sentence_template)
    if match:
        # 返回 "的" 後面的詞
        return match.group(2).strip()
    
    # 如果上面的正規表達式不符合，嘗試另一個模式
    match = re.search(r'需要\s*\[NUM\]\s*([^的]*?)的\s*([^。，，；；:：""''\"\']*)', sentence_template)
    if match:
        return match.group(2).strip()
    
    # 最後的備選方案
    match = re.search(r'\[NUM\].*?的\s*(\S+)', sentence_template)
    if match:
        return match.group(1).strip()
    
    return "配料"  # 預設值

# 讀取和轉換
new_rows = []

with open(input_file, 'r', encoding='utf-8') as infile:
    reader = csv.DictReader(infile)
    
    for row in reader:
        category = row['Category']
        drink_name = row['Item Name']
        sentence = row['Sentence Template']
        correct_num = row['Correct Number']
        
        # 提取屬性名稱
        attribute_name = extract_attribute_name(sentence)
        
        new_rows.append({
            'category': category,
            'drink_name': drink_name,
            'attribute_name': attribute_name,
            'attribute_value': correct_num,
            'question_template': sentence
        })

# 寫入新 CSV
with open(output_file, 'w', newline='', encoding='utf-8') as outfile:
    fieldnames = ['category', 'drink_name', 'attribute_name', 'attribute_value', 'question_template']
    writer = csv.DictWriter(outfile, fieldnames=fieldnames)
    
    writer.writeheader()
    writer.writerows(new_rows)

print(f"✅ 轉換完成！新檔案已存檔在 {output_file}")
print(f"共轉換 {len(new_rows)} 行資料")
