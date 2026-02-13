import streamlit as st
import pandas as pd
import logging
import glob
import matplotlib.pyplot as plt
import japanize_matplotlib
import numpy as np
import matplotlib.gridspec as gridspec

# デバッグ用：設定が読み込めているか画面に出す
# 成功すれば、ここにDB情報が表示されます
if st.secrets:
    st.write("✅ 設定の読み込みに成功しました")
else:
    st.write("❌ 設定（secrets）が空です")

# --- ログ設定 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='app.log',
    filemode='w'
)

# --------------------------------------------------------------------------
# 1. Supabase 接続確立
# --------------------------------------------------------------------------
try:
    # secrets.toml の [connections.postgresql] を探しに行きます
    conn = st.connection("postgresql", type="sql")
except Exception as e:
    st.error(f"接続設定エラー: {e}")

# --------------------------------------------------------------------------
# 2. データ読み込み関数
# --------------------------------------------------------------------------

@st.cache_data(ttl=3600)
def load_data_from_supabase(table_name):
    """Supabaseからデータを取得し、ID列を文字列に変換する"""
    try:
        query = f'SELECT * FROM "{table_name}";'
        df = conn.query(query)
        
        # ID関連の列を文字列に変換（CSV読み込み時の挙動を再現）
        str_cols = ['商品ID', '倉庫ID', '業務区分ID', 'SET_ID']
        for col in str_cols:
            if col in df.columns:
                df[col] = df[col].astype(str).replace('None', np.nan).replace('nan', np.nan)
        return df
    except Exception as e:
        st.error(f"テーブル {table_name} の取得失敗: {e}")
        return pd.DataFrame()

@st.cache_data
def load_single_csv(path, encoding='utf-8'):
    """既存のCSV読み込み（マスタデータ用）"""
    try:
        return pd.read_csv(path, encoding=encoding, dtype={'商品ID': str, '倉庫ID': str, '業務区分ID': str, 'SET_ID': str})
    except:
        return None

# 補助関数：棒グラフにラベルを追加
def add_labels_to_stacked_bar(ax, data_df):
    # (既存のロジックをそのまま維持)
    bottom = pd.Series([0.0] * len(data_df), index=data_df.index)
    for col in data_df.columns:
        values = data_df[col]
        y_pos = bottom + values / 2
        for i, val in enumerate(values):
            if val > 0:
                ax.text(i, y_pos.iloc[i], f'{int(val)}', ha='center', va='center', fontsize=5, color='white')
        bottom += values

@st.cache_data
def convert_df(df):
    return df.to_csv(encoding='utf-8-sig').encode('utf-8-sig')

# --------------------------------------------------------------------------
# 3. メイン処理
# --------------------------------------------------------------------------
def main():
    st.set_page_config(layout="wide")
    st.title('📊 在庫・出荷データの可視化アプリ')

    # --- データの読み込み ---
    # マスタ類はまだCSVのまま（順次Supabaseへ移行可能）
    df1 = load_single_csv("T_9x30.csv", encoding='utf-8')
    df_pack_master = load_single_csv("PACK_Classification.csv", encoding='utf-8')
    df_set_master = load_single_csv("SET_Class.csv", encoding='utf-8')
    
    # ★ ここが重要！GitHubのCSVではなく、Supabaseから読み込む
    with st.spinner('Supabaseから在庫データを取得中...'):
        df3 = load_data_from_supabase("在庫情報")
        df5 = load_data_from_supabase("T_9x07")

    # データが空の場合のチェック
    if df3.empty:
        st.error("在庫データが取得できませんでした。Supabaseのテーブル名を確認してください。")
        return

    # --- 以降のフィルタリング、グラフ描画ロジック ---
    # (以前の app.py のロジックをここに続ける)
    st.success("データの取得に成功しました。")
    st.subheader("在庫情報のプレビュー")
    st.dataframe(df3.head())

if __name__ == "__main__":
    main()
