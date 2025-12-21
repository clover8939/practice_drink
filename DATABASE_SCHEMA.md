"""
新資料庫架構設計說明

舊結構 (quiz_items):
- id, category, item_name, sentence_template, correct_number, unit, is_mastered

新結構:
1. drinks 表：存放飲料基本資訊
   - id (PRIMARY KEY)
   - category (分類: 黑咖啡、奶茶等)
   - name (飲料名稱: 黑咖啡加牛奶(M))
   - mastery_score (掌握度: 0-100)

2. drink_attributes 表：存放飲料的各個屬性
   - id (PRIMARY KEY)
   - drink_id (外鍵)
   - attribute_name (屬性名稱: 咖啡液、牛奶等)
   - attribute_value (正確值: 160)
   - unit (單位: 毫升、克等)
   - question_template (問題模板: "[NUM]毫升的咖啡液")
   - times_attempted (嘗試次數)
   - times_correct (正確次數)

3. drink_attribute_options 表：存放每個屬性的可選答案
   - id (PRIMARY KEY)
   - attribute_id (外鍵)
   - option_value (選項值)
   - is_correct (是否正確)

例子:
drinks 表:
id | category | name | mastery_score
1  | 黑咖啡   | 黑咖啡加牛奶(M) | 75

drink_attributes 表:
id | drink_id | attribute_name | attribute_value | unit  | question_template
1  | 1        | 咖啡液        | 160            | 毫升  | [NUM]毫升的咖啡液
2  | 1        | 牛奶          | 50             | 毫升  | [NUM]毫升的牛奶

drink_attribute_options 表:
id | attribute_id | option_value | is_correct
1  | 1           | 160          | 1
2  | 1           | 180          | 0
3  | 1           | 200          | 0
"""
