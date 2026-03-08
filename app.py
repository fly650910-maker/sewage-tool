import streamlit as st
import pandas as pd
import numpy as np
import io
import re

st.set_page_config(page_title="國土署下水道績效轉檔工具", page_icon="🚀", layout="centered")

st.title("🚀 國土署下水道績效 一鍵轉檔工具")
st.markdown("給同仁的話：請依照下方步驟操作，轉檔完成後即可下載最新格式的 CSV 檔案。")

st.header("步驟一：設定專用下水道「建照號碼」")
st.markdown("請在下方填寫屬於專用的建照號碼（多組請用逗號 `,` 分開）：")
permit_input = st.text_area("專用建照清單", value="(093)工建字第01351號, (101)府建字第00541號", height=100)

st.header("步驟二：上傳原始檔案")
uploaded_files = st.file_uploader("請選擇從「建管系統」下載的 CSV 檔案 (可多選)", type=['csv'], accept_multiple_files=True)

if st.button("⚡ 開始自動轉檔", type="primary"):
    if not uploaded_files:
        st.warning("⚠️ 請先上傳檔案喔！")
    else:
        with st.spinner('努力運算中，請稍候...'):
            zy_keywords = [p.strip() for p in re.split(r'[,;\n\t]+', permit_input) if p.strip()]
            all_valid_rows = []
            
            # 讀取並處理所有檔案
            for file in uploaded_files:
                try:
                    df = pd.read_csv(file, on_bad_lines='skip', dtype=str, encoding='utf-8')
                except Exception:
                    continue
                    
                df = df.fillna('')
                df['使用執照發照日期_fmt'] = df.get('使用執照發照日期', '').str.strip()
                df = df[df['使用執照發照日期_fmt'] != '']
                if df.empty: continue
                
                df['房屋戶數_num'] = pd.to_numeric(df['房屋戶數'], errors='coerce').fillna(1).astype(int)
                df = df[df['房屋戶數_num'] < 100000]
                df['核准建造執照_key'] = df.get('核准建造執照', '').fillna('無建照')
                df['核准使用執照_key'] = df.get('核准使用執照', '').fillna('無使照')

                # 展開戶數
                expanded_rows = []
                for name, group in df.groupby(['核准建造執照_key', '核准使用執照_key']):
                    H = max(1, group['房屋戶數_num'].max())
                    N = len(group)
                    expanded_rows.append(group)
                    if N < H:
                        diff = H - N
                        duplicated = pd.concat([group.iloc[[0]].copy()]*diff, ignore_index=True)
                        expanded_rows.append(duplicated)
                if not expanded_rows: continue
                df_expanded = pd.concat(expanded_rows, ignore_index=True)
                
                # 地址修正邏輯
                def fix_addr(row):
                    vill = str(row.get('村里', '')).strip()
                    street = str(row.get('街路段', '')).strip()
                    if any(x in vill for x in ['路', '街', '大道']) or (('段' in vill) and any(x in vill for x in ['路', '街'])):
                        last_idx = max(vill.rfind('村'), vill.rfind('里'), vill.rfind('鄰'))
                        if last_idx != -1:
                            potential_vill = vill[:last_idx+1]
                            potential_road = vill[last_idx+1:]
                        else:
                            potential_vill = ''
                            potential_road = vill
                        if any(x in potential_road for x in ['路', '街', '大道', '段']):
                            row['村里'] = potential_vill
                            if not street: row['街路段'] = potential_road
                            elif potential_road not in street: row['街路段'] = potential_road + street
                    return row
                df_expanded = df_expanded.apply(fix_addr, axis=1)

                all_valid_rows.append(df_expanded)
            
            if all_valid_rows:
                final_df = pd.concat(all_valid_rows, ignore_index=True)
                
                # 判斷專用
                def is_zy(row):
                    permit = str(row.get('核准建造執照', ''))
                    return any(kw in permit for kw in zy_keywords if kw)
                mask_zy = final_df.apply(is_zy, axis=1)
                
                df_zy = final_df[mask_zy].copy()
                df_gen = final_df[~mask_zy].copy()

                def format_target(df_source, cat_name):
                    if df_source.empty: return pd.DataFrame()
                    df_t = pd.DataFrame()
                    df_t['申請類別'] = cat_name
                    df_t['縣/市'] = df_source.get('縣市別', '')
                    df_t['鄉/鎮/市/區'] = df_source.get('鄉鎮市區', '')
                    df_t['村/里'] = df_source.get('村里', '')
                    df_t['街/路名、段號'] = df_source.get('街路段', '')
                    df_t['巷'] = df_source.get('巷', '')
                    df_t['弄'] = df_source.get('弄', '')
                    df_t['門牌號'] = df_source.get('門牌地址', '')
                    df_t['門牌號_之'] = df_source.get('地址_之', '').str.replace('等', '', regex=False).str.strip()
                    df_t['樓層'] = df_source.get('樓層', '')
                    df_t['樓層_之'] = df_source.get('樓層_之', '')
                    df_t['水號'] = ''
                    df_t['核准建造執照'] = df_source.get('核准建造執照', '')
                    df_t['核准使用執照'] = df_source.get('核准使用執照', '')
                    
                    date_cols = ['竣工日期', '設置日期', '建造執照發照日期', '使用執照發照日期_fmt']
                    target_date_cols = ['竣工日期', '設置日期', '建造執照發照日期', '使用執照發照日期']
                    for i, col in enumerate(date_cols):
                        t_col = target_date_cols[i]
                        if col in df_source.columns:
                            df_t[t_col] = df_source[col].fillna('').astype(str).str.strip().str.replace('/', '-', regex=False)
                            df_t[t_col] = df_t[t_col].apply(lambda x: x[:10] if len(x)>=10 and '-' in x else x)
                            df_t[t_col] = df_t[t_col].apply(lambda d: f"{d.split('-')[0]}-{d.split('-')[1].zfill(2)}-{d.split('-')[2].zfill(2)}" if len(d.split('-'))==3 else d)
                        else: df_t[t_col] = ''
                    df_t['戶數'] = '1'
                    df_t['備註'] = df_source.get('備註', '')
                    
                    df_t = df_t.fillna('')
                    address_cols = ['縣/市', '鄉/鎮/市/區', '村/里', '街/路名、段號', '巷', '弄', '門牌號', '門牌號_之', '樓層', '樓層_之']
                    df_t['dup_idx'] = df_t.groupby(address_cols).cumcount() + 1
                    mask = df_t.groupby(address_cols)['dup_idx'].transform('max') > 1
                    df_t.loc[mask, '門牌號_之'] = df_t.loc[mask, '門牌號_之'] + df_t.loc[mask, 'dup_idx'].astype(str)
                    df_t = df_t.drop(columns=['dup_idx']).replace('', np.nan)
                    return df_t

                res_zy = format_target(df_zy, '專用污水下水道')
                res_gen = format_target(df_gen, '建築物污水處理設施')

                st.success("🎉 轉檔成功！請點擊下方按鈕下載檔案：")
                
                col1, col2 = st.columns(2)
                with col1:
                    if not res_zy.empty:
                        csv_zy = res_zy.to_csv(index=False, encoding='utf-8-sig')
                        st.download_button(label="📥 下載：專用下水道", data=csv_zy, file_name="國土署格式_專用下水道.csv", mime="text/csv", type="primary")
                    else:
                        st.info("本次無專用下水道資料")
                
                with col2:
                    if not res_gen.empty:
                        csv_gen = res_gen.to_csv(index=False, encoding='utf-8-sig')
                        st.download_button(label="📥 下載：建築物設備", data=csv_gen, file_name="國土署格式_建築物設備.csv", mime="text/csv", type="primary")
                    else:
                        st.info("本次無建築物設備資料")
            else:
                st.error("處理失敗，請確認檔案格式是否正確。")
