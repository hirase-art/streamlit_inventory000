import streamlit as st
import pandas as pd

# 1. ページ構成
st.set_page_config(page_title="在庫判定シミュレーター", layout="wide")

# 2. Supabase接続 (secrets.tomlを参照)
conn = st.connection("postgresql", type="sql")

# 3. サイドバー：経営・製造パラメータ
st.sidebar.header("🎛 シミュレーション設定")
coeff = st.sidebar.slider("需要予測係数", 0.5, 2.0, 1.0, 0.1, help="直近4週実績に対する倍率")
target_mos = st.sidebar.slider("目標在庫月数", 0.5, 2.0, 1.0, 0.1, help="この月数を切ると『要発注』")

# 4. データ取得（SQLエイリアス問題を解消済み）
@st.cache_data(ttl=300)
def get_verified_data():
    query = """
    WITH weekly_stats AS (
        SELECT 
            "商品ID" as product_id,
            "出荷数" as quantity,
            DENSE_RANK() OVER (PARTITION BY "商品ID" ORDER BY "code" DESC) as rnk
        FROM "shipment_weekly"
    ),
    four_weeks_avg AS (
        SELECT 
            product_id,
            AVG(quantity) as avg_q
        FROM weekly_stats
        WHERE rnk BETWEEN 2 AND 5  /* 今週を除いた直近4週 */
        GROUP BY product_id
    )
    SELECT 
        m."商品ID" as product_id,
        m."商品名" as product_name,
        COALESCE(s."合計在庫", 0) as stock,    
        COALESCE(p."pending_quantity", 0) as pending, -- T_4001の列名に合わせて修正してください
        COALESCE(f.avg_q, 0) as avg_4w
    FROM "product_master" m
    LEFT JOIN four_weeks_avg f ON m."商品ID" = f.product_id
    LEFT JOIN "010_在庫集計" s ON m."商品ID" = s."商品ID"
    LEFT JOIN "T_4001" p ON m."商品ID" = p."商品ID"
    """
    return conn.query(query)

# --- メインロジック ---
st.title("📦 次世代 在庫調達意思決定")

try:
    df_raw = get_verified_data()
    df = df_raw.copy()

    # 計算：X = 4週平均 * 4.4週 * 係数
    df['予測月間出荷(X)'] = (df['avg_4w'] * 4.4 * coeff).astype(int)
    
    # 計算：在庫月数 (MOS)
    df['在庫月数(MOS)'] = (df['stock'] + df['pending']) / df['予測月間出荷(X)'].replace(0, 1)

    # 判定分岐
    def judge(row):
        if row['予測月間出荷(X)'] == 0: return "実績なし"
        mos = row['在庫月数(MOS)']
        if mos < 0.5: return "🚨 間に合わない"
        elif mos < target_mos:
            return "⏳ 入荷待ち" if row['pending'] > 0 else "⚠️ 要発注"
        elif mos > 3.0: return "💰 在庫過多"
        else: return "✅ 適正"

    df['判定'] = df.apply(judge, axis=1)

    # 概要メトリクス
    c1, c2, c3 = st.columns(3)
    c1.metric("🚨 欠品リスク", len(df[df['判定'] == "🚨 間に合わない"]))
    c2.metric("⚠️ 要発注", len(df[df['判定'] == "⚠️ 要発注"]))
    c3.metric("💰 在庫過多", len(df[df['判定'] == "💰 在庫過多"]))

    # フィルター
    status_filter = st.multiselect("表示する判定", df['判定'].unique(), default=df['判定'].unique())
    
    # テーブル表示
    st.dataframe(
        df[df['判定'].isin(status_filter)][['product_id', 'product_name', 'stock', 'pending', '予測月間出荷(X)', '在庫月数(MOS)', '判定']]
        .style.background_gradient(subset=['在庫月数(MOS)'], cmap='RdYlGn', vmin=0, vmax=3),
        use_container_width=True
    )

except Exception as e:
    st.error("データの取得中にエラーが発生しました。")
    st.code(str(e))
    st.info("💡 ヒント: テーブル名や列名がSupabaseと一致しているか、ダブルクォーテーションで囲まれているか確認してください。")
