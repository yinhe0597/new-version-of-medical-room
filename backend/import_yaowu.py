import pandas as pd
import sqlite3
import numpy as np
import re
import os

file_path = r'C:\Users\Administrator\Desktop\yaowu.xls'
db_path = r'e:\yws\backend\app.db'

def clean_spec(spec):
    # 将 25mg*30 转换为 25mg*1
    s = str(spec)
    new_s = re.sub(r'\*[\d\.]+', '*1', s)
    return new_s

def get_scattered_unit(spec):
    # 尝试从规格中提取单位，如 "25mg*30片" 提取 "片"
    s = str(spec)
    # 匹配 *数字 后的文字
    match = re.search(r'\*[\d\.]+\s*([a-zA-Z\u4e00-\u9fa5]+)', s)
    if match:
        unit = match.group(1)
        # 如果提取到的是 盒/瓶/袋，可能不是最小单位，尝试进一步提取
        if unit in ['盒', '瓶', '袋', '瓶装']:
            return "片"
        return unit
    
    # 如果没匹配到，尝试匹配末尾的汉字
    match = re.search(r'([\u4e00-\u9fa5]+)$', s)
    if match:
        unit = match.group(1)
        if unit in ['盒', '瓶', '袋', '瓶装']:
            return "片"
        return unit
        
    return "最小单位"

try:
    if not os.path.exists(file_path):
        print(f"错误: 找不到文件 {file_path}")
        exit(1)

    print(f"正在读取文件: {file_path}")
    df = pd.read_excel(file_path, sheet_name=0)
    df.columns = [str(col).strip() for col in df.columns]

    print(f"正在连接数据库: {db_path}")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # 清空现有药品数据
    print("正在清空旧的药品数据...")
    c.execute('DELETE FROM drug')
    c.execute("DELETE FROM sqlite_sequence WHERE name='drug'")

    success_count = 0
    
    # 按序号分组处理
    print("开始处理药品数据...")
    for seq, group in df.groupby('序号'):
        try:
            name = str(group.iloc[0].get('药  名', '')).strip()
            if not name or name == 'nan':
                continue

            spec = str(group.iloc[0].get('规格', '')).strip()
            unit = str(group.iloc[0].get('单位', '')).strip()

            whole_row = group[group['散装价'].isna() | (group['散装价'] == '')]
            if whole_row.empty:
                whole_row = group.iloc[[0]]
            else:
                whole_row = whole_row.iloc[[0]]

            purchase_price = float(whole_row['购进价'].values[0]) if pd.notnull(whole_row['购进价'].values[0]) else 0.0
            price = float(whole_row['盒装价'].values[0]) if pd.notnull(whole_row['盒装价'].values[0]) else 0.0

            scattered_row = group[group['散装价'].notna() & (group['散装价'] != '')]
            has_scattered = not scattered_row.empty
            scattered_price = None
            conversion_rate = None

            if has_scattered:
                scattered_price = float(scattered_row['盒装价'].values[0])
                scattered_total = float(scattered_row['散装价'].values[0])
                if scattered_price > 0:
                    conversion_rate = int(round(scattered_total / scattered_price))
                else:
                    conversion_rate = 1

            stock = 0
            if '库存' in group.columns:
                val = group.iloc[0].get('库存')
                stock = int(val) if pd.notnull(val) else 0

            c.execute('''
                INSERT INTO drug (name, type, specification, unit, price, stock, status, purchase_price, has_scattered, scattered_price, conversion_rate)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                name, 1, spec, unit, price, stock, 1, purchase_price,
                1 if has_scattered else 0, scattered_price, conversion_rate
            ))
            success_count += 1
        except Exception as e:
            print(f"序号 {seq} 处理出错: {e}")

    conn.commit()
    conn.close()
    print(f"成功导入 {success_count} 条药品记录。")
except Exception as e:
    print(f"全局错误: {e}")
