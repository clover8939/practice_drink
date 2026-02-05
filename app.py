import io
import csv
import sqlite3
import random
import os
import datetime
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, g, make_response

from flask_httpauth import HTTPBasicAuth
from werkzeug.security import generate_password_hash, check_password_hash

# 載入 .env 文件中的環境變數
load_dotenv()

app = Flask(__name__)
DATABASE = 'quiz.db'

# --- 登入配置 ---
auth = HTTPBasicAuth()

# 設定單一管理帳號和密碼（從環境變數讀取，預設為開發用密碼）
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'Lovefatfat')
users = {
    "belle": generate_password_hash(ADMIN_PASSWORD, method="pbkdf2:sha256")
}

@auth.verify_password
def verify_password(username, password):
    """驗證使用者名稱和密碼"""
    if username in users and check_password_hash(users.get(username), password):
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
    """初始化資料庫並創建新的表結構（飲料+屬性模式）。"""
    with app.app_context():
        db = get_db()
        
        try:
            # 1. Drinks 表 - 存放飲料基本資訊
            db.execute("""
                CREATE TABLE IF NOT EXISTS drinks (
                    id INTEGER PRIMARY KEY,
                    category TEXT NOT NULL,
                    name TEXT NOT NULL UNIQUE,
                    is_mastered INTEGER DEFAULT 0
                );
            """)
            
            # 2. Drink Attributes 表 - 存放飲料的各項屬性（咖啡液、牛奶等）
            db.execute("""
                CREATE TABLE IF NOT EXISTS drink_attributes (
                    id INTEGER PRIMARY KEY,
                    drink_id INTEGER NOT NULL,
                    attribute_name TEXT NOT NULL,
                    attribute_value TEXT NOT NULL,
                    unit TEXT,
                    question_template TEXT,
                    times_attempted INTEGER DEFAULT 0,
                    times_correct INTEGER DEFAULT 0,
                    FOREIGN KEY (drink_id) REFERENCES drinks(id) ON DELETE CASCADE,
                    UNIQUE(drink_id, attribute_name)
                );
            """)
            
            # 3. Drink Attribute Options 表 - 存放每個屬性的可選答案
            db.execute("""
                CREATE TABLE IF NOT EXISTS drink_attribute_options (
                    id INTEGER PRIMARY KEY,
                    attribute_id INTEGER NOT NULL,
                    option_value TEXT NOT NULL,
                    is_correct INTEGER DEFAULT 0,
                    FOREIGN KEY (attribute_id) REFERENCES drink_attributes(id) ON DELETE CASCADE
                );
            """)
            
            db.commit()
            print("✅ 資料庫表結構已建立成功！")
            
        except sqlite3.OperationalError as e:
            if 'already exists' not in str(e):
                print(f"⚠️ 資料庫初始化注意: {e}")
            db.commit()

# --- 核心邏輯：飲料和屬性相關函數 ---

def get_unique_categories_and_drinks():
    """從資料庫獲取所有不重複的分類和飲料名稱，供前端篩選使用。"""
    db = get_db()
    try:
        categories = db.execute('SELECT DISTINCT category FROM drinks ORDER BY category').fetchall()
        drinks = db.execute('SELECT DISTINCT name FROM drinks ORDER BY name').fetchall()
    except sqlite3.OperationalError:
        init_db()
        return [], []
    
    return [c['category'] for c in categories], [d['name'] for d in drinks]

def get_drink_attributes(drink_id):
    """獲取指定飲料的所有屬性。"""
    db = get_db()
    return db.execute(
        'SELECT * FROM drink_attributes WHERE drink_id = ? ORDER BY id',
        (drink_id,)
    ).fetchall()

def generate_attribute_options(attribute_id, correct_value, db):
    """
    為指定屬性生成下拉式選單的選項。
    邏輯：
    - 如果答案是10的倍數，每10間格生成選項
    - 考慮順序：10, 5, 0.5
    - 最小為0，最大不超過正確答案的2倍
    """
    # 首先嘗試從資料庫中獲取已定義的選項
    predefined_options = db.execute(
        'SELECT option_value FROM drink_attribute_options WHERE attribute_id = ? ORDER BY is_correct DESC',
        (attribute_id,)
    ).fetchall()
    
    if predefined_options:
        return [opt['option_value'] for opt in predefined_options]
    
    # 如果沒有預定義選項，則生成預設選項
    options_list = []
    
    try:
        correct_num = float(correct_value)
    except ValueError:
        # 非數字答案，返回空列表讓前端顯示預設
        return [str(correct_value)]
    
    max_value = correct_num * 2  # 最大值 = 正確答案的2倍
    
    # 判斷增量：10, 5, 0.5
    if correct_num >= 10 and correct_num % 10 == 0:
        # 答案是10的倍數，每10間格
        step = 10
    elif correct_num >= 5 and correct_num % 5 == 0:
        # 答案是5的倍數，每5間格
        step = 5
    elif correct_num < 5:
        # 答案小於5，按0.5間格
        step = 0.5
    else:
        # 其他情況，按10的倍數計算
        step = 10 if correct_num >= 10 else 5
    
    # 加入隨機性：正確答案前後的選項數量隨機變化
    # 前面: 2-4 個選項，後面: 3-5 個選項
    options_before = random.randint(2, 4)  # 正確答案前面的選項數
    options_after = random.randint(3, 5)   # 正確答案後面的選項數
    
    min_value = max(0, correct_num - step * options_before)
    max_value = correct_num + step * options_after
    
    # 生成所有可能的選項
    current = min_value
    while current <= max_value:
        # 格式化數字 (去除不必要的小數點)
        if current == int(current):
            options_list.append(str(int(current)))
        else:
            options_list.append(str(current))
        current += step
    
    # 確保正確答案在列表中
    correct_str = str(int(correct_num)) if correct_num == int(correct_num) else str(correct_num)
    if correct_str not in options_list:
        options_list.append(correct_str)
    
    # 排序從小到大 (移除隨機打亂)
    options_list = sorted(list(set(options_list)), key=lambda x: float(x))
    
    return options_list

# --- 網頁路由 (Routes) ---

@app.route('/')
def index():
    """首頁 - 顯示各功能選項"""
    return render_template('index.html')

@app.route('/quiz', methods=['GET', 'POST'])
def quiz():
    """飲料選擇和測驗頁面"""
    db = get_db()
    all_categories, all_drinks = get_unique_categories_and_drinks()

    if not all_categories and not all_drinks:
        return render_template('quiz.html', 
                               message="資料庫中沒有飲料，請先新增飲料後再開始測驗。",
                               all_categories=[], 
                               all_drinks=[],
                               quiz_mode='all')

    if request.method == 'POST':
        selected_category = request.form.get('category_filter', 'all')
        selected_drink = request.form.get('drink_filter', 'all')
        quiz_mode = request.form.get('quiz_mode', 'all')  # 新增: 測驗模式
        
        where_clauses = []
        params = []
        
        if selected_category and selected_category != 'all':
            where_clauses.append("category = ?")
            params.append(selected_category)
        
        if selected_drink and selected_drink != 'all':
            where_clauses.append("name = ?")
            params.append(selected_drink)
        
        sql_where = " WHERE " + " AND ".join(where_clauses) if where_clauses else ""
        
        # 價錢測驗模式：隨機選取 5 道價錢題目
        if quiz_mode == 'price':
            # 從所有符合條件的飲料中,隨機選取 5 個價錢屬性
            price_query = f'''
                SELECT da.*, d.name as drink_name, d.category, d.id as drink_id
                FROM drink_attributes da
                JOIN drinks d ON da.drink_id = d.id
                {sql_where}
                {"AND" if sql_where else "WHERE"} da.attribute_name = '價錢'
                ORDER BY RANDOM()
                LIMIT 5
            '''
            price_attributes = db.execute(price_query, params).fetchall()
            
            if not price_attributes:
                return render_template('quiz.html', 
                                       message="沒有找到符合條件的價錢題目。", 
                                       all_categories=all_categories, 
                                       all_drinks=all_drinks,
                                       selected_category=selected_category,
                                       selected_drink=selected_drink,
                                       quiz_mode=quiz_mode)
            
            # 為每個價錢屬性生成選項
            drink_questions = []
            for attr in price_attributes:
                options = generate_attribute_options(attr['id'], attr['attribute_value'], db)
                
                # 處理問題模板,確保題目中包含飲料名稱
                question_text = attr['question_template'].replace('[NUM]', '____')
                
                # 替換各種可能的通用詞彙為具體飲料名稱
                replacements = [
                    ('這杯飲料', f"「{attr['drink_name']}」"),
                    ('這個食物', f"「{attr['drink_name']}」"),
                    ('此飲品', f"「{attr['drink_name']}」"),
                    ('該飲料', f"「{attr['drink_name']}」"),
                ]
                
                for old, new in replacements:
                    question_text = question_text.replace(old, new)
                
                # 如果題目中沒有包含飲料名稱,在前面加上
                if attr['drink_name'] not in question_text:
                    question_text = f"「{attr['drink_name']}」{question_text}"
                
                drink_questions.append({
                    'id': attr['id'],
                    'name': attr['attribute_name'],
                    'drink_name': attr['drink_name'],  # 添加飲料名稱
                    'category': attr['category'],
                    'question': question_text,
                    'unit': '',  # 價錢測驗不顯示單位,因為已經在問題模板中
                    'correct_answer': attr['attribute_value'],
                    'options': options,
                    'is_price': True  # 標記為價錢題目
                })
            
            # 使用虛擬的 drink 物件
            virtual_drink = {
                'id': 0,
                'name': '價錢測驗',
                'category': '混合題目'
            }
            
            return render_template('quiz_question.html', 
                                   drink=virtual_drink,
                                   questions=drink_questions,
                                   category_filter=selected_category,
                                   drink_filter=selected_drink,
                                   quiz_mode=quiz_mode,
                                   is_price_quiz=True)
        
        # 配料測驗或全部測驗模式：選取一個飲料
        # 隨機選取一個飲料
        query = f'SELECT * FROM drinks {sql_where} ORDER BY RANDOM() LIMIT 1'
        drink = db.execute(query, params).fetchone()
        
        if not drink:
            return render_template('quiz.html', 
                                   message="在所選的範圍內找不到飲料。", 
                                   all_categories=all_categories, 
                                   all_drinks=all_drinks,
                                   selected_category=selected_category,
                                   selected_drink=selected_drink,
                                   quiz_mode=quiz_mode)

        # 獲取該飲料的所有屬性
        attributes = get_drink_attributes(drink['id'])
        
        # 根據測驗模式過濾屬性
        if quiz_mode == 'price':
            # 價錢測驗模式：只顯示屬性名稱為「價錢」的題目
            attributes = [attr for attr in attributes if attr['attribute_name'] == '價錢']
        elif quiz_mode == 'ingredient':
            # 配料測驗模式：排除價錢，只顯示配料
            attributes = [attr for attr in attributes if attr['attribute_name'] != '價錢']
        # quiz_mode == 'all' 時不過濾，顯示所有屬性
        
        if not attributes:
            mode_text = "價錢" if quiz_mode == 'price' else "配料" if quiz_mode == 'ingredient' else ""
            return render_template('quiz.html', 
                                   message=f"該飲料沒有配置{mode_text}題目。", 
                                   all_categories=all_categories, 
                                   all_drinks=all_drinks,
                                   selected_category=selected_category,
                                   selected_drink=selected_drink,
                                   quiz_mode=quiz_mode)

        # 為每個屬性生成選項
        drink_questions = []
        for attr in attributes:
            options = generate_attribute_options(attr['id'], attr['attribute_value'], db)
            
            # 處理問題模板,加入飲料名稱讓題目更清楚
            question_text = attr['question_template'].replace('[NUM]', '____')
            
            # 為配料測驗也在題目前加上飲料名稱
            if quiz_mode != 'price' and drink:
                # 如果題目中沒有包含飲料名稱,在前面加上
                if drink['name'] not in question_text:
                    question_text = f"「{drink['name']}」{question_text}"
            
            drink_questions.append({
                'id': attr['id'],
                'name': attr['attribute_name'],
                'drink_name': drink['name'] if drink else None,  # 添加飲料名稱
                'question': question_text,
                'unit': attr['unit'],
                'correct_answer': attr['attribute_value'],
                'options': options
            })
        
        return render_template('quiz_question.html', 
                               drink=drink,
                               questions=drink_questions,
                               category_filter=selected_category,
                               drink_filter=selected_drink,
                               quiz_mode=quiz_mode)

    return render_template('quiz.html', 
                           all_categories=all_categories, 
                           all_drinks=all_drinks, 
                           selected_category='all', 
                           selected_drink='all',
                           quiz_mode='all')

@app.route('/check_answer', methods=['POST'])
def check_answer():
    """檢查答案並更新統計資訊"""
    db = get_db()
    
    # 獲取所有的答題資料
    form_data = request.form.to_dict()
    drink_id = form_data.get('drink_id')
    
    # 統計答題結果
    all_correct = True
    results = []
    
    # 遍歷所有表單數據，找出所有的答案
    for key in form_data.keys():
        if key.startswith('choice_'):
            # 提取屬性ID
            attribute_id = key.replace('choice_', '')
            user_choice = form_data.get(f'choice_{attribute_id}')
            correct_answer = form_data.get(f'correct_answer_{attribute_id}')
            
            # 驗證必填欄位
            if not user_choice or user_choice == '':
                continue  # 跳過未作答的題目
            
            # 取回 attribute 額外資訊（名稱/模板/單位/飲料名稱）
            attr_row = None
            drink_name = None
            if attribute_id:
                attr_row = db.execute(
                    '''SELECT da.attribute_name, da.question_template, da.unit, d.name as drink_name
                       FROM drink_attributes da
                       JOIN drinks d ON da.drink_id = d.id
                       WHERE da.id = ?''',
                    (attribute_id,)
                ).fetchone()

            if attr_row:
                attribute_name = attr_row['attribute_name']
                question_template = attr_row['question_template']
                unit = attr_row['unit']
                drink_name = attr_row['drink_name']
            else:
                attribute_name = None
                question_template = None
                unit = None
                drink_name = None
                
            question_text = None
            if question_template:
                question_text = question_template.replace('[NUM]', '____')

            is_correct = (user_choice == correct_answer)
            all_correct = all_correct and is_correct

            # 更新屬性的統計資訊
            if attribute_id:
                db.execute(
                    'UPDATE drink_attributes SET times_attempted = times_attempted + 1 WHERE id = ?',
                    (attribute_id,)
                )

                if is_correct:
                    db.execute(
                        'UPDATE drink_attributes SET times_correct = times_correct + 1 WHERE id = ?',
                        (attribute_id,)
                    )

            results.append({
                'correct': is_correct,
                'attribute_id': attribute_id,
                'attribute_name': attribute_name,
                'drink_name': drink_name,  # 新增飲料名稱
                'question_text': question_text,
                'unit': unit,
                'user_choice': user_choice,
                'correct_answer': correct_answer
            })
    
    # 驗證是否有作答記錄
    if not results:
        return render_template('result.html', 
                             all_correct=False,
                             results=[],
                             request_form=form_data,
                             message="⚠️ 未檢測到任何作答，請確保至少回答一題。")
    
    # 更新飲料的掌握狀態：只要有一題錯就標記為未掌握
    if drink_id:
        mastery_status = 1 if all_correct else 0
        db.execute('UPDATE drinks SET is_mastered = ? WHERE id = ?', (mastery_status, drink_id))
    
    db.commit()
    
    return render_template('result.html', 
                           all_correct=all_correct,
                           results=results,
                           request_form=form_data)

@app.route('/create_item', methods=['GET', 'POST'])
@auth.login_required
def create_item():
    """建立新飲料及其屬性"""
    if request.method == 'POST':
        category = request.form.get('category')
        drink_name = request.form.get('drink_name')
        
        db = get_db()
        
        # 檢查飲料是否已存在
        existing = db.execute('SELECT id FROM drinks WHERE name = ?', (drink_name,)).fetchone()
        if existing:
            return render_template('create_item.html', message="❌ 此飲料名稱已存在")
        
        try:
            # 插入飲料基本資訊
            cursor = db.execute(
                'INSERT INTO drinks (category, name) VALUES (?, ?)',
                (category, drink_name)
            )
            drink_id = cursor.lastrowid
            
            # 處理屬性
            attribute_count = int(request.form.get('attribute_count', 1))
            for i in range(attribute_count):
                attr_name = request.form.get(f'attribute_name_{i}')
                attr_value = request.form.get(f'attribute_value_{i}')
                attr_unit = request.form.get(f'attribute_unit_{i}')
                attr_template = request.form.get(f'attribute_template_{i}')
                
                if attr_name and attr_value:
                    db.execute(
                        '''INSERT INTO drink_attributes 
                           (drink_id, attribute_name, attribute_value, unit, question_template) 
                           VALUES (?, ?, ?, ?, ?)''',
                        (drink_id, attr_name, attr_value, attr_unit, attr_template)
                    )
            
            db.commit()
            return render_template('create_item.html', message="✅ 飲料及屬性建立成功！")
        
        except Exception as e:
            db.rollback()
            return render_template('create_item.html', message=f"❌ 建立失敗: {e}")

    return render_template('create_item.html')

@app.route('/manage')
@auth.login_required
def manage_items():
    """管理飲料和屬性"""
    db = get_db()
    drinks = db.execute('SELECT * FROM drinks ORDER BY category, name').fetchall()
    all_categories, all_drink_names = get_unique_categories_and_drinks()
    
    # 為每個飲料獲取屬性
    drinks_with_attrs = []
    for drink in drinks:
        attrs = get_drink_attributes(drink['id'])
        drinks_with_attrs.append({
            'drink': drink,
            'attributes': attrs
        })
    
    return render_template('manage_items.html', 
                           drinks_with_attrs=drinks_with_attrs, 
                           all_categories=all_categories,
                           all_drinks=all_drink_names)

@app.route('/edit_item/<int:drink_id>', methods=['GET', 'POST'])
@auth.login_required
def edit_item(drink_id):
    """編輯飲料和屬性"""
    db = get_db()
    drink = db.execute('SELECT * FROM drinks WHERE id = ?', (drink_id,)).fetchone()
    
    if not drink:
        return redirect(url_for('manage_items'))
    
    if request.method == 'POST':
        category = request.form.get('category')
        name = request.form.get('name')
        
        try:
            db.execute('UPDATE drinks SET category = ?, name = ? WHERE id = ?',
                      (category, name, drink_id))
            
            # 獲取現有的所有屬性ID
            existing_attrs = db.execute('SELECT id FROM drink_attributes WHERE drink_id = ?', (drink_id,)).fetchall()
            existing_attr_ids = {str(attr['id']) for attr in existing_attrs}
            
            # 收集表單中提交的屬性ID
            submitted_attr_ids = set()
            attribute_count = int(request.form.get('attribute_count', 0))
            
            # 更新或新增屬性
            for i in range(attribute_count):
                attr_id = request.form.get(f'attribute_id_{i}')
                attr_name = request.form.get(f'attribute_name_{i}')
                attr_value = request.form.get(f'attribute_value_{i}')
                attr_unit = request.form.get(f'attribute_unit_{i}')
                attr_template = request.form.get(f'attribute_template_{i}')
                
                if attr_name and attr_value:
                    if attr_id:  # 更新現有屬性
                        submitted_attr_ids.add(attr_id)
                        db.execute(
                            '''UPDATE drink_attributes 
                               SET attribute_name = ?, attribute_value = ?, unit = ?, question_template = ?
                               WHERE id = ? AND drink_id = ?''',
                            (attr_name, attr_value, attr_unit, attr_template, attr_id, drink_id)
                        )
                    else:  # 新增屬性
                        db.execute(
                            '''INSERT INTO drink_attributes 
                               (drink_id, attribute_name, attribute_value, unit, question_template) 
                               VALUES (?, ?, ?, ?, ?)''',
                            (drink_id, attr_name, attr_value, attr_unit, attr_template)
                        )
            
            # 刪除未在表單中出現的屬性（使用者已移除的）
            attrs_to_delete = existing_attr_ids - submitted_attr_ids
            for attr_id in attrs_to_delete:
                db.execute('DELETE FROM drink_attributes WHERE id = ? AND drink_id = ?', (attr_id, drink_id))
            
            db.commit()
            return redirect(url_for('manage_items'))
        
        except Exception as e:
            db.rollback()
            attributes = get_drink_attributes(drink_id)
            return render_template('edit_item.html', 
                                 drink=drink, 
                                 attributes=attributes,
                                 message=f"❌ 更新失敗: {e}")
    
    attributes = get_drink_attributes(drink_id)
    return render_template('edit_item.html', drink=drink, attributes=attributes)

@app.route('/delete_item/<int:drink_id>', methods=['POST'])
@auth.login_required
def delete_item(drink_id):
    """刪除飲料"""
    db = get_db()
    db.execute('DELETE FROM drinks WHERE id = ?', (drink_id,))
    db.commit()
    return redirect(url_for('manage_items'))

@app.route('/import', methods=['GET', 'POST'])
@auth.login_required
def import_items():
    """匯入飲料 CSV"""
    if request.method == 'POST':
        if 'file' not in request.files:
            return render_template('import_items.html', message="請選擇一個檔案進行上傳。")
        
        file = request.files['file']
        
        if file.filename == '':
            return render_template('import_items.html', message="請選擇一個有效的檔案。")
        
        if not file.filename.endswith('.csv'):
            return render_template('import_items.html', message="檔案格式不正確，請上傳 CSV 檔案 (.csv)。")

        stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
        csv_reader = csv.reader(stream)
        
        imported_count = 0
        skipped_count = 0
        processed_rows = 0
        created_drinks_count = 0
        db = get_db()
        
        try:
            for row in csv_reader:
                # 略過空行
                if not row or all((c.strip() == '' for c in row)):
                    continue

                # 去掉首尾空白
                row = [col.strip() for col in row]

                # 自動跳過標題列（支援 5 欄或 6 欄）
                header_cells = [c.lower() for c in row]
                if header_cells[:2] == ['category', 'drink name'] or header_cells[:2] == ['category', 'drink_name']:
                    continue

                # 支援兩種格式：
                # 5欄：category, drink_name, attribute_name, attribute_value, question_template
                # 6欄：category, drink_name, attribute_name, attribute_value, unit, question_template
                if len(row) == 5:
                    category, drink_name, attr_name, attr_value, template = row
                    unit = ''
                elif len(row) == 6:
                    category, drink_name, attr_name, attr_value, unit, template = row
                else:
                    skipped_count += 1
                    continue

                processed_rows += 1

                if not (category and drink_name and attr_name and attr_value and template):
                    skipped_count += 1
                    continue

                # 檢查或建立飲料
                drink = db.execute('SELECT id FROM drinks WHERE name = ?', (drink_name,)).fetchone()
                if not drink:
                    cursor = db.execute(
                        'INSERT INTO drinks (category, name) VALUES (?, ?)',
                        (category, drink_name)
                    )
                    drink_id = cursor.lastrowid
                    created_drinks_count += 1
                else:
                    drink_id = drink['id']

                # 加入或忽略屬性（同飲品+屬性名不重複）
                db.execute(
                    '''INSERT OR IGNORE INTO drink_attributes 
                       (drink_id, attribute_name, attribute_value, unit, question_template) 
                       VALUES (?, ?, ?, ?, ?)''',
                    (drink_id, attr_name, attr_value, unit, template)
                )
                imported_count += 1
            
            db.commit()
            success_message = (
                f"✅ 匯入成功！共處理 {processed_rows} 列資料，"
                f"新增 {created_drinks_count} 杯飲料，新增/忽略 {imported_count} 條屬性資料。"
            )
            if skipped_count > 0:
                success_message += f" (略過 {skipped_count} 條不符合格式的行)"
            
            return render_template('import_items.html', message=success_message, is_success=True)
        
        except Exception as e:
            return render_template('import_items.html', message=f"匯入時發生錯誤: {e}")

    return render_template('import_items.html')

@app.route('/export', methods=['GET'])
@auth.login_required
def export_items():
    """匯出所有飲料資料為 CSV"""
    db = get_db()
    
    try:
        drinks = db.execute('SELECT * FROM drinks ORDER BY category, name').fetchall()
        
        if not drinks:
            return "資料庫中沒有飲料可以匯出。", 404
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # 寫入標題列
        writer.writerow(['Category', 'Drink Name', 'Attribute Name', 'Attribute Value', 'Unit', 'Question Template'])
        
        # 寫入資料
        for drink in drinks:
            attrs = get_drink_attributes(drink['id'])
            for attr in attrs:
                writer.writerow([
                    drink['category'],
                    drink['name'],
                    attr['attribute_name'],
                    attr['attribute_value'],
                    attr['unit'],
                    attr['question_template']
                ])
        
        csv_content = output.getvalue()
        response = make_response(csv_content)
        
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"drinks_export_{timestamp}.csv"
        
        response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
        response.headers['Content-Type'] = 'text/csv; charset=utf-8-sig'
        
        return response
    
    except Exception as e:
        return f"匯出失敗: {e}", 500

@app.route('/reset_mastery', methods=['POST'])
@auth.login_required
def reset_mastery():
    """重置所有飲料的掌握狀態和答題記錄"""
    db = get_db()
    try:
        # 重置所有屬性的答題統計
        attr_cursor = db.execute('UPDATE drink_attributes SET times_attempted = 0, times_correct = 0')
        attr_reset_count = attr_cursor.rowcount
        
        # 重置所有飲料的掌握狀態
        drink_cursor = db.execute('UPDATE drinks SET is_mastered = 0')
        drink_reset_count = drink_cursor.rowcount
        
        db.commit()
        
        return render_template('reset_result.html', 
                             drink_reset_count=drink_reset_count,
                             attr_reset_count=attr_reset_count)
    except Exception as e:
        db.rollback()
        return render_template('reset_result.html', 
                             drink_reset_count=0, 
                             attr_reset_count=0,
                             message=f"⚠️ 重置失敗: {e}")

# --- 執行應用程式 ---

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
