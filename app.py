import streamlit as st
import pandas as pd

st.set_page_config(page_title="診断モード")
st.title("🛠️ 接続診断モード")

# 1. 接続テスト
try:
    conn = st.connection("postgresql", type="sql")
    st.success("✅ データベース接続オブジェクトの作成に成功")
except Exception as e:
    st.error(f"❌ 接続エラー: {e}")
    st.stop()

# 2. 最小限のデータ取得テスト
with st.spinner('在庫データを10件だけ取得中...'):
    try:
        # 全件ではなく、あえて「LIMIT 10」で試す
        df = conn.query('SELECT * FROM "在庫情報" LIMIT 10;')
        st.write("### 在庫データ（先頭10件）")
        st.table(df) # dataframeより軽量なtableを使用
        st.success("✅ データの取得・表示に成功")
    except Exception as e:
        st.error(f"❌ クエリ実行エラー: {e}")

st.info("この画面が安定して表示され続けるなら、原因は『結合処理』か『メモリ不足』です。")
