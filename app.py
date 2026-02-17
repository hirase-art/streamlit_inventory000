import streamlit as st
import pandas as pd
import numpy as np

st.set_page_config(layout="wide", page_title="在庫・出荷分析 (診断中)")
st.title("🛠️ 機能復旧・診断モード")

# 1. 接続確認
conn = st.connection("postgresql", type="sql")

@st.cache_data(ttl=600)
def load_data(table_name, limit=None):
    query = f'SELECT * FROM "{table_name}"'
    if limit: query += f' LIMIT {limit}'
    df = conn.query(query)
    return df

# 2. 段階的にロードして件数を確認
st.write("### 📡 1. データ同期状況")
try:
    with st.spinner('データを取得中...'):
        df_inv = load_data("在庫情報")
        df_pack = load_data("Pack_Classification")
        df_ship_m = load_data("T_9x30", limit=5000) # 重い可能性があるので一旦制限
        
    st.success(f"取得完了: 在庫 {len(df_inv)}件 / マスタ {len(df_pack)}件 / 出荷 {len(df_ship_m)}件")
except Exception as e:
    st.error(f"ロード失敗: {e}")
    st.stop()

# 3. 結合テスト (ここが Oh no の最有力候補)
st.write("### 🔗 2. データ結合テスト")
try:
    # 必要な列だけに絞って結合（メモリ節約）
    m_sub = df_pack[['商品ID', '大分類', '中分類', '小分類', '商品名']].drop_duplicates('商品ID')
    res = pd.merge(df_inv, m_sub, on='商品ID', how='left')
    st.success(f"結合成功: 結果 {len(res)}件")
except Exception as e:
    st.error(f"結合失敗: {e}")
    st.stop()

# 4. 表示テスト
st.write("### 📊 3. 簡易表示")
if not res.empty:
    st.dataframe(res.head(100), use_container_width=True)
    
st.info("ここまでのステップがすべて正常なら、次は『グラフ』や『ピボット』を戻します。")
