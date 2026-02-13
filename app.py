import streamlit as st
import pandas as pd
import logging
import glob
import matplotlib.pyplot as plt
import japanize_matplotlib
import numpy as np
import matplotlib.gridspec as gridspec

# --- ページ設定 ---
st.set_page_config(layout="wide", page_title="在庫・出荷可視化アプリ")

# --- ログ設定 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='app.log',
    filemode='w'
)

# --------------------------------------------------------------------------
# 1. Supabase 接続設定
# --------------------------------------------------------------------------
try:
    conn = st.connection("postgresql", type="sql")
except Exception as e:
    st.error(f"Supabase接続エラー: {e}")

# --------------------------------------------------------------------------
# 2. データ読み込み関数
# --------------------------------------------------------------------------

@st.cache_data(ttl=3600)
def load_data_from_supabase(table_name):
    """Supabaseからデータを取得し、型変換を行う"""
    try:
        query = f'SELECT * FROM "{table_name}";'
        df = conn.query(query)
        # ID関連の列を文字列に変換 (CSV読み込み時の挙動を再現)
        str_cols = ['商品ID', '倉庫ID', '業務区分ID', 'SET_ID', '品質区分ID']
        for col in str_cols:
            if col in df.columns:
                df[col] = df[col].astype(str).replace('None', np.nan).replace('nan', np.nan)
        return df
    except Exception as e:
        st.error(f"テーブル {table_name} の取得失敗: {e}")
        return pd.DataFrame()

@st.cache_data
def load_single_csv(path, encoding='utf-8'):
    """マスタ類（まだGitHubにあるもの）の読み込み"""
    try:
        return pd.read_csv(path, encoding=encoding, dtype={'商品ID': str, '倉庫ID': str, '業務区分ID': str, 'SET_ID': str})
    except:
        return None

# 補助関数：棒グラフにラベルを追加
def add_labels_to_stacked_bar(ax, data_df):
    try:
        bottom = pd.Series([0.0] * len(data_df), index=data_df.index)
        for col in data_df.columns:
            values = data_df[col].fillna(0)
            y_pos = bottom + values / 2
            for i, val in enumerate(values):
                if val > (data_df.sum(axis=1).max() * 0.05): # 小さすぎる値は非表示
                    ax.text(i, y_pos.iloc[i], f'{int(val)}', ha='center', va='center', fontsize=6, color='white', fontweight='bold')
            bottom += values
    except:
        pass

@st.cache_data
def convert_df(df):
    return df.to_csv(encoding='utf-8-sig').encode('utf-8-sig')

# --------------------------------------------------------------------------
# 3. メイン処理
# --------------------------------------------------------------------------

st.title('📊 在庫・出荷データの可視化アプリ')

# --- データの読み込み ---
# マスタ類はGitHubから読み込み
df1 = load_single_csv("T_9x30.csv", encoding='utf-8')
df_pack_master = load_single_csv("PACK_Classification.csv", encoding='utf-8')
df_set_master = load_single_csv("SET_Class.csv", encoding='utf-8')

# ★ 在庫と週間出荷は Supabase から直接取得 (GitHubのCSVは不要に！)
with st.spinner('Supabaseから最新データを同期中...'):
    df3 = load_data_from_supabase("在庫情報") # 元の CZ04003_*.csv
    df5 = load_data_from_supabase("T_9x07")   # 元の T_9x07.csv

# --------------------------------------------------------------------------
# 4. サイドバー・フィルタ（以前のロジックを完全復旧）
# --------------------------------------------------------------------------
st.sidebar.header(":blue[出荷情報フィルタ]")
unit_selection = st.sidebar.radio("集計単位:", ["Pack", "SET"], horizontal=True)

# マスタデータの切り替え
if unit_selection == "Pack":
    df_master_shipping = df_pack_master.copy() if df_pack_master is not None else pd.DataFrame()
else:
    df_master_shipping = df_set_master.copy().rename(columns={'SET_ID': '商品ID', 'セット構成名称': '商品名'}) if df_set_master is not None else pd.DataFrame()

# 基本データフレームの作成
base_df_monthly = pd.merge(df1, df_master_shipping, on='商品ID', how='left') if df1 is not None else pd.DataFrame()
base_df_weekly = pd.merge(df5, df_master_shipping, on='商品ID', how='left') if not df5.empty else pd.DataFrame()

# 共通フィルタ
aggregation_level = st.sidebar.radio("集計粒度:", ["大分類", "中分類", "小分類", "商品ID"], index=3, horizontal=True)
show_total = st.sidebar.radio("合計表示:", ["なし", "あり"], horizontal=True)

# 絞り込み UI
selected_daibunrui = st.sidebar.multiselect("大分類:", options=sorted(base_df_monthly['大分類'].dropna().unique().tolist()) if '大分類' in base_df_monthly.columns else [])
product_name_search = st.sidebar.text_input("商品名検索:").strip()

# --------------------------------------------------------------------------
# 5. タブ表示（出荷・在庫）
# --------------------------------------------------------------------------
tab_shipping, tab_stock = st.tabs(["📝 出荷情報", "📊 在庫情報"])

# --- 出荷情報のタブ ---
with tab_shipping:
    st.header("🚚 出荷情報")
    if not base_df_monthly.empty:
        # 月間出荷のフィルタリングとピボット
        df_m_filtered = base_df_monthly[base_df_monthly['大分類'].isin(selected_daibunrui)] if selected_daibunrui else base_df_monthly
        if product_name_search:
            df_m_filtered = df_m_filtered[df_m_filtered['商品名'].str.contains(product_name_search, na=False)]

        # ピボットテーブル表示
        pivot_m = df_m_filtered.pivot_table(index=["大分類", "商品ID", "商品名"], columns="month_code", values="合計出荷数", aggfunc="sum").fillna(0)
        st.subheader("月間出荷数（直近12ヶ月）")
        st.dataframe(pivot_m.tail(12))

# --- 在庫情報のタブ ---
with tab_stock:
    st.header("📦 在庫情報")
    if not df3.empty and df_pack_master is not None:
        # 在庫データとマスタの結合
        df3_master = pd.merge(df3, df_pack_master[['商品ID', '大分類', '中分類', '小分類']], on='商品ID', how='left')
        
        # フィルタ適用
        df3_filtered = df3_master[df3_master['大分類'].isin(selected_daibunrui)] if selected_daibunrui else df3_master
        
        col1, col2 = st.columns([2, 1])
        with col1:
            st.subheader("在庫プレビュー")
            st.dataframe(df3_filtered.head(100))
            st.download_button("在庫CSVダウンロード", data=convert_df(df3_filtered), file_name="inventory.csv")
        
        with col2:
            st.subheader("在庫構成比（大分類別）")
            if '大分類' in df3_filtered.columns:
                stock_pie = df3_filtered.groupby('大分類')['在庫数(引当数を含む)'].sum()
                fig, ax = plt.subplots()
                ax.pie(stock_pie, labels=stock_pie.index, autopct='%1.1f%%')
                st.pyplot(fig)

st.success("Supabaseから最新データを取得し、フィルタを適用しました。")
