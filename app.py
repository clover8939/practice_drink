import io
import csv
import sqlite3
import random
from flask import Flask, render_template, request, redirect, url_for, g

from flask_httpauth import HTTPBasicAuth
from werkzeug.security import generate_password_hash, check_password_hash # 用於安全地處理密碼

app = Flask(__name__)
DATABASE = 'quiz.db'

# --- 登入配置 ---
auth = HTTPBasicAuth()

# 設定單一管理帳號和密碼 (請務必修改密碼！)
users = {
    "belle": generate_password_hash("Lovefatfat", method= "pbkdf2:sha256") # <<<<<<< 請務必修改此密碼
}

@auth.verify_password
def verify_password(username, password):
    """驗證使用者名稱和密碼"""
    if username in users and \
            check_password_hash(users.get(username), password):
        return username
    return None

# --- 資料庫初始化與連接 ---

def get_db():
    """獲取資料庫連線，並設置 row_factory 讓查詢結果以字典形式返回。"""
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    """應用程式上下文結束時關閉資料庫連線。"""
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    """初始化資料庫並創建 quiz_items 表。"""
    with app.app_context():
        db = get_db()
        # 創建或修改題庫表 (新增 is_mastered 欄位)
        try:
            # 嘗試執行 ALTER TABLE 來添加新欄位，避免刪除現有資料
            db.execute('ALTER TABLE quiz_items ADD COLUMN is_mastered INTEGER DEFAULT 0')
            db.commit()
        except sqlite3.OperationalError as e:
            # 如果欄位已存在，會拋出錯誤，我們忽略這個錯誤
            if 'duplicate column name' not in str(e):
                 # 如果是其他錯誤，則拋出
                # 首次運行時，如果表不存在，init_db會失敗，但我們需要先確保表存在
                pass

            # 確保 table 創建邏輯仍然存在 (用於全新啟動)
            db.execute("""
                CREATE TABLE IF NOT EXISTS quiz_items (
                    id INTEGER PRIMARY KEY,
                    category TEXT NOT NULL,         
                    item_name TEXT NOT NULL,        
                    sentence_template TEXT NOT NULL,
                    correct_number TEXT NOT NULL,
                    unit TEXT,
                    is_mastered INTEGER DEFAULT 0  -- 新增欄位
                );
            """)
            db.commit()

# --- 核心邏輯：生成題目與選項 ---

def get_unique_categories_and_items():
    """從資料庫獲取所有不重複的分類和品項，供前端篩選使用。"""
    db = get_db()
    # 確保資料庫存在，如果不存在，呼叫 init_db
    try:
        categories = db.execute('SELECT DISTINCT category FROM quiz_items ORDER BY category').fetchall()
        items = db.execute('SELECT DISTINCT item_name FROM quiz_items ORDER BY item_name').fetchall()
    except sqlite3.OperationalError:
        init_db()
        return [], []
    
    return [c['category'] for c in categories], [i['item_name'] for i in items]

# app.py (替換 generate_options 函數)

# app.py (替換 generate_options 函數)

def generate_options(correct_answer, db):
    """
    優化版選項生成：確保選項包含正確答案，從資料庫尋找接近答案的真實值，
    並在補足選項時，優先使用接近的 10 的倍數作為干擾項。
    """
    
    # 確保所有選項都是字串格式，並且以正確答案開頭
    options_set = {str(correct_answer)}
    
    try:
        correct_num = float(correct_answer)
        is_numeric = True
    except ValueError:
        correct_num = None
        is_numeric = False

    # 1. 從資料庫獲取所有數字型答案
    all_numbers_from_db = []
    if is_numeric:
        db_results = db.execute('SELECT correct_number FROM quiz_items').fetchall()
        
        for row in db_results:
            db_answer_str = row['correct_number']
            if db_answer_str != correct_answer: # 排除正確答案本身
                try:
                    db_num = float(db_answer_str)
                    
                    # 計算差值 (距離)
                    difference = abs(db_num - correct_num)
                    
                    all_numbers_from_db.append((db_answer_str, db_num, difference))
                except ValueError:
                    pass

        # 2. 排序並選擇最接近的答案 (最多3個)
        all_numbers_from_db.sort(key=lambda x: x[2]) # 根據距離排序
        closest_options = all_numbers_from_db[:4]
        
        for option_str, option_num, _ in closest_options:
            options_set.add(option_str)
            
            # 3. 增加「相近的 10 的倍數整數」作為干擾項
            if abs(option_num - correct_num) > 0.1: # 確保這個干擾項與正確答案不同
                
                # 找到最接近 option_num 且能被 10 整除的數
                closest_multiple_of_10 = round(option_num / 10) * 10
                
                # 確保結果是整數，並且與正確答案數值上不同
                if abs(closest_multiple_of_10 - correct_num) > 0.1:
                    options_set.add(str(int(closest_multiple_of_10)))
                
    # 4. 補足邏輯：使用 10 的倍數來填滿不足的選項
    while len(options_set) < 4:
        if is_numeric:
            # 產生一個與正確答案接近的 10 的倍數
            
            # 找到正確答案最接近的 10 的倍數
            correct_num_multiple_of_10 = round(correct_num / 10) * 10
            
            # 產生一個相對於這個 10 的倍數的偏移量 (例如：-20, 10, 20)
            # 確保偏移量是 10 的倍數
            offset_options = [-20, -10, 10, 20, 30]
            random_offset = random.choice(offset_options)
            
            filler_num = correct_num_multiple_of_10 + random_offset
            
            # 確保數字大於或等於 0，且必須是 10 的倍數
            filler_num = max(0, filler_num)
            
            filler_option_str = str(int(filler_num))
            
            # 檢查：1. 與正確答案數值上不同； 2. 集合中不存在
            if abs(float(filler_option_str) - correct_num) > 0.1 and filler_option_str not in options_set:
                options_set.add(filler_option_str)
            else:
                 # 如果生成的數字重複或與答案相同，則重試
                 # 這裡可以簡單地加入一個大的隨機 10 的倍數來避免卡住
                 random_large_multiple = random.choice([50, 100, 150, 200])
                 options_set.add(str(random_large_multiple))
                 
        else:
             # 如果正確答案非數字 (e.g. "微量")，則補足預設選項
             options_set.add(random.choice(["10", "20", "30", "微量", "少量"]))
             
        # 安全機制：確保集合大小不再變化，防止無限循環
        if len(options_set) == 4:
            break

    # 5. 將集合轉換為列表，並打亂順序，選取前4個
    options = list(options_set)
    random.shuffle(options)
    return options[:4]

# --- 網頁路由 (Routes) ---

# --- 新增：登入首頁路由 ---
@app.route('/')
def index():
    """
    登入後的主頁，會被 auth.login_required 保護。
    非登入狀態會跳轉到瀏覽器登入框。
    """
    # 這裡使用 auth.login_required 來保護主頁
    # 但如果我們想讓所有人都能看見首頁，但只有特定功能需要登入，則保留 index()，並添加 login_required 到需要保護的路由。
    return render_template('index.html')

# app.py (修改 /quiz 路由)

@app.route('/quiz', methods=['GET', 'POST'])
def quiz():
    db = get_db()
    all_categories, all_items = get_unique_categories_and_items()

    if not all_categories and not all_items:
        return render_template('quiz_empty.html')

    if request.method == 'POST':
        # 處理篩選邏輯
        selected_category = request.form.get('category_filter')
        selected_item = request.form.get('item_filter')
        quiz_mode = request.form.get('quiz_mode', 'all') 
        quiz_method = request.form.get('quiz_method', 'card') # <--- 新增：獲取測驗方法
        
        where_clauses = []
        params = []
        
        # 1. 處理錯題複習模式
        if quiz_mode == 'missed':
            where_clauses.append("is_mastered = 0")
        
        # 2. 處理分類和品項篩選
        if selected_category and selected_category != 'all':
            where_clauses.append("category = ?")
            params.append(selected_category)
            
        if selected_item and selected_item != 'all':
            where_clauses.append("item_name = ?")
            params.append(selected_item)
            
        sql_where = " WHERE " + " AND ".join(where_clauses) if where_clauses else ""
        
        # 3. 隨機選取一題
        query = f'SELECT * FROM quiz_items {sql_where} ORDER BY RANDOM() LIMIT 1'
        item = db.execute(query, params).fetchone()
        
        if not item:
            message = "在所選的範圍內找不到題目。"
            if quiz_mode == 'missed':
                message = "🙌 恭喜！目前在所選範圍內沒有需要複習的錯題了。"
            
            return render_template('quiz.html', 
                                   message=message, 
                                   all_categories=all_categories, 
                                   all_items=all_items,
                                   selected_category=selected_category,
                                   selected_item=selected_item,
                                   selected_mode=quiz_mode,
                                   selected_method=quiz_method) # <--- 新增：傳遞 method

        correct_answer = item['correct_number']
        options = generate_options(correct_answer, db)
        question_text = item['sentence_template'].replace('[NUM]', '____')
        
        # 顯示題目頁面 (傳遞 item_id 和 method)
        return render_template('quiz_question.html', 
                               item=item,
                               question=question_text,
                               unit=item['unit'],
                               options=options,
                               correct_answer=correct_answer,
                               category_filter=selected_category,
                               item_filter=selected_item,
                               quiz_mode=quiz_mode,
                               quiz_method=quiz_method) # <--- 新增：傳遞 method

    # GET 請求時，顯示篩選介面
    return render_template('quiz.html', 
                           all_categories=all_categories, 
                           all_items=all_items, 
                           selected_category='all', 
                           selected_item='all',
                           selected_mode='all',
                           selected_method='card') # <--- 新增：預設方法為 card

# (別忘了修改 /check_answer 路由，確保它也能將 quiz_method 傳遞給 result.html，
# 以便 result.html 中的「再來一題」按鈕能保持方法設定。)
# 實際檢查 /check_answer 路由，它已經通過 request.form 將所有參數傳遞給 result.html，所以 /check_answer 不需額外修改。

@app.route('/check_answer', methods=['POST'])
def check_answer():
    user_choice = request.form.get('choice')
    correct_answer = request.form.get('correct_answer')
    item_id = request.form.get('item_id') # 從隱藏欄位獲取題目 ID
    
    is_correct = (user_choice == correct_answer)
    
    # 如果答對了，更新資料庫的 is_mastered 為 1
    if is_correct and item_id:
        db = get_db()
        db.execute('UPDATE quiz_items SET is_mastered = 1 WHERE id = ?', (item_id,))
        db.commit()
    
    # 將所有 POST 數據傳遞給結果頁面，包含篩選條件
    return render_template('result.html', 
                           is_correct=is_correct, 
                           user_choice=user_choice, 
                           correct_answer=correct_answer,
                           request_form=request.form)

@app.route('/create_item', methods=['GET', 'POST'])
@auth.login_required
def create_item():
    if request.method == 'POST':
        # 接收使用者輸入
        category = request.form['category'] 
        item_name = request.form['item_name']
        sentence = request.form['sentence_template']
        number = request.form['correct_number']
        unit = request.form['unit']

        db = get_db()
        db.execute('INSERT INTO quiz_items (category, item_name, sentence_template, correct_number, unit) VALUES (?, ?, ?, ?, ?)',
                   (category, item_name, sentence, number, unit))
        db.commit()
        
        return redirect(url_for('create_item'))

    return render_template('create_item.html')

# app.py (新增或替換以下路由)

@app.route('/manage')
@auth.login_required
def manage_items():
    """
    顯示所有題目，並提供篩選功能以供編輯。
    """
    db = get_db()
    
    # 獲取所有題目列表
    items = db.execute('SELECT * FROM quiz_items ORDER BY category, item_name').fetchall()
    
    # 獲取所有分類和品項，用於前端篩選
    all_categories, all_items = get_unique_categories_and_items()
    
    return render_template('manage_items.html', 
                           items=items, 
                           all_categories=all_categories,
                           all_items=all_items)

@app.route('/edit_item/<int:item_id>', methods=['GET', 'POST'])
@auth.login_required
def edit_item(item_id):
    """
    根據 ID 顯示特定題目，並處理修改邏輯。
    """
    db = get_db()
    
    if request.method == 'POST':
        # 處理修改資料
        category = request.form['category'] 
        item_name = request.form['item_name']
        sentence = request.form['sentence_template']
        number = request.form['correct_number']
        unit = request.form['unit']
        
        db.execute("""
            UPDATE quiz_items 
            SET category=?, item_name=?, sentence_template=?, correct_number=?, unit=?
            WHERE id=?
        """, (category, item_name, sentence, number, unit, item_id))
        db.commit()
        
        # 修改成功後，重導向回管理頁面
        return redirect(url_for('manage_items'))

    # GET 請求時，顯示編輯表單
    item = db.execute('SELECT * FROM quiz_items WHERE id = ?', (item_id,)).fetchone()
    
    if item is None:
        # 如果找不到題目，返回錯誤或重導向
        return redirect(url_for('manage_items'))
        
    return render_template('edit_item.html', item=item)

@app.route('/delete_item/<int:item_id>', methods=['POST'])
@auth.login_required
def delete_item(item_id):
    """
    根據 ID 刪除特定題目。
    """
    db = get_db()
    db.execute('DELETE FROM quiz_items WHERE id = ?', (item_id,))
    db.commit()
    
    return redirect(url_for('manage_items'))

# app.py (新增路由)


@app.route('/import', methods=['GET', 'POST'])
@auth.login_required
def import_items():
    """
    處理 CSV 檔案上傳和匯入題庫。
    CSV 格式預期： category,item_name,sentence_template,correct_number,unit
    """
    if request.method == 'POST':
        # 檢查是否有檔案被上傳
        if 'file' not in request.files:
            return render_template('import_items.html', message="請選擇一個檔案進行上傳。")
        
        file = request.files['file']
        
        # 檢查檔案是否為空
        if file.filename == '':
            return render_template('import_items.html', message="請選擇一個有效的檔案。")
            
        # 檢查檔案類型 (簡單檢查副檔名)
        if not file.filename.endswith('.csv'):
            return render_template('import_items.html', message="檔案格式不正確，請上傳 CSV 檔案 (.csv)。")

        # 讀取檔案內容並解析 CSV
        stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
        csv_reader = csv.reader(stream)
        
        # 跳過標題行 (如果有的話)
        # next(csv_reader) 
        
        imported_count = 0
        skipped_count = 0
        db = get_db()
        
        try:
            for row in csv_reader:
                # 預期欄位順序： category, item_name, sentence_template, correct_number, unit
                if len(row) == 5:
                    category, item_name, sentence, number, unit = [col.strip() for col in row]
                    
                    # 簡單檢查關鍵欄位不為空
                    if category and item_name and sentence and number:
                        db.execute("""
                            INSERT INTO quiz_items 
                            (category, item_name, sentence_template, correct_number, unit) 
                            VALUES (?, ?, ?, ?, ?)
                        """, (category, item_name, sentence, number, unit))
                        imported_count += 1
                    else:
                        skipped_count += 1
                else:
                    skipped_count += 1
                    
            db.commit()
            
            success_message = f"✅ 匯入成功！共新增 {imported_count} 條題目。"
            if skipped_count > 0:
                 success_message += f" (略過 {skipped_count} 條不符合格式的行)"

            return render_template('import_items.html', message=success_message, is_success=True)

        except Exception as e:
            # 如果解析或寫入資料庫出錯
            return render_template('import_items.html', message=f"匯入時發生錯誤: {e}")

    # GET 請求時，顯示上傳表單
    return render_template('import_items.html')

@app.route('/reset_mastery', methods=['POST'])
@auth.login_required
def reset_mastery():
    """將所有已掌握的題目 (is_mastered = 1) 重置為 0。"""
    db = get_db()
    try:
        cursor = db.execute('UPDATE quiz_items SET is_mastered = 0 WHERE is_mastered = 1')
        db.commit()
        reset_count = cursor.rowcount
        
        return render_template('reset_result.html', reset_count=reset_count)
    except sqlite3.OperationalError:
        # 如果 is_mastered 欄位不存在 (舊資料庫未更新)
        return render_template('reset_result.html', reset_count=0, message="⚠️ 資料庫結構尚未更新，無法執行重置。請重啟應用程式或檢查資料庫。")

# --- 執行應用程式 ---

if __name__ == '__main__':
    init_db()
    app.run(debug=True)