import streamlit as st
import pandas as pd
import numpy as np

# --- ページ設定 ---
st.set_page_config(layout="wide", page_title="在庫・出荷分析システム V2")

# --------------------------------------------------------------------------
# 1. データベース接続
# --------------------------------------------------------------------------
conn = st.connection("postgresql", type="sql")

@st.cache_data(ttl=600)
def load_master(table_name):
    """マスタデータは件数が少ないのでそのまま読み込む"""
    return conn.query(f'SELECT * FROM "{table_name}";')

@st.cache_data(ttl=300)
def get_aggregated_shipments(period_type="monthly"):
    """
    ★重要：SQL側で集計を済ませてから持ってくる
    Python側で 6万行をこねくり回すのをやめ、集計済みの数百行だけを取得します。
    """
    if period_type == "monthly":
        # 月次集計SQL
        query = """
        SELECT 
            "倉庫ID", "業務区分ID", "商品ID", 
            to_char("出荷確定日", 'YYMM') as code, 
            SUM("出荷数") as "合計出荷数"
        FROM shipment_all
        GROUP BY 1, 2, 3, 4
        """
    else:
        # 週次集計SQL (月曜始まり)
        query = """
        SELECT 
            "倉庫ID", "業務区分ID", "商品ID", 
            to_char(date_trunc('week', "出荷確定日"), 'YYMMDD') || 'w' as code, 
            SUM("出荷数") as "合計出荷数"
        FROM shipment_all
        GROUP BY 1, 2, 3, 4
        """
    return conn.query(query)

# データロード
with st.spinner('データを同期中...'):
    df_m_ship = get_aggregated_shipments("monthly")
    df_w_ship = get_aggregated_shipments("weekly")
    df_inv = load_master("在庫情報")
    df_pack = load_master("Pack_Classification")
    df_set = load_master("SET_Class")

# --------------------------------------------------------------------------
# 2. サイドバー (共通フィルタ)
# --------------------------------------------------------------------------
st.sidebar.header("🔍 共通検索")
search_id = st.sidebar.text_input("商品ID検索 (カンマ区切り可):", placeholder="2039, 2040")
search_name = st.sidebar.text_input("商品名検索 (あいまい):")

st.sidebar.markdown("---")
unit = st.sidebar.radio("集計単位:", ["Pack", "SET"], horizontal=True)
df_master = df_pack if unit == "Pack" else df_set.rename(columns={'SET_ID': '商品ID', 'セット構成名称': '商品名'})

# 分類フィルタの作成
dai_opts = sorted(df_master['大分類'].dropna().unique()) if not df_master.empty else []
sel_dai = st.sidebar.multiselect("大分類:", options=dai_opts)

# --------------------------------------------------------------------------
# 3. フィルタ＆ピボット関数
# --------------------------------------------------------------------------
def display_shipment_table(df_ship, master, title):
    if df_ship.empty: return
    
    # 1. マスタ結合 (ここも集計済みデータ相手なので一瞬で終わる)
    res = pd.merge(df_ship, master[['商品ID', '商品名', '大分類', '中分類', '小分類']], on='商品ID', how='left')
    
    # 2. フィルタ適用
    if search_id:
        ids = [i.strip().zfill(8) if i.strip().isdigit() else i.strip() for i in search_id.split(',')]
        res = res[res['商品ID'].isin(ids)]
    if search_name:
        res = res[res['商品名'].str.contains(search_name, na=False)]
    if sel_dai:
        res = res[res['大分類'].isin(sel_dai)]
        
    # 3. ピボット表示
    if not res.empty:
        piv = res.pivot_table(
            index=["大分類", "商品ID", "商品名"], 
            columns='code', 
            values='合計出荷数', 
            aggfunc='sum'
        ).fillna(0)
        st.subheader(title)
        st.dataframe(piv, use_container_width=True)
    else:
        st.info(f"{title}の該当データがありません。")

# --------------------------------------------------------------------------
# 4. メイン表示
# --------------------------------------------------------------------------
tab1, tab2 = st.tabs(["📝 出荷分析", "📊 在庫分析"])

with tab1:
    display_shipment_table(df_m_ship, df_master, "🗓️ 月間出荷推移")
    st.markdown("---")
    display_shipment_table(df_w_ship, df_master, "🗓️ 週間出荷推移")

with tab2:
    st.subheader("📦 在庫状況")
    # 在庫も同様にフィルタ
    inv_res = pd.merge(df_inv, df_pack[['商品ID', '大分類']], on='商品ID', how='left')
    if sel_dai: inv_res = inv_res[inv_res['大分類'].isin(sel_dai)]
    st.dataframe(inv_res, use_container_width=True)
