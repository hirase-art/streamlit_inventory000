%%writefile app.py

import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import japanize_matplotlib  # 日本語文字化け対策

# --------------------------------------------------------------------------
# Streamlit アプリケーションのUI部分
# --------------------------------------------------------------------------
st.title('🚚 週次出荷数の可視化アプリ')

# --------------------------------------------------------------------------
# データ読み込みと加工
# --------------------------------------------------------------------------
# ファイルパスをStreamlitアプリ内に直接記述します。
# このパスは、Colabの実行環境から見たパスと同じです。
DATA_PATH = "/content/drive/Shareddrives/205_ロジスティクス（部門限）/90_aggregation_file/MST/BOX_ID.csv"

# データ読み込み処理を関数化し、キャッシュを使って高速化
@st.cache_data
def load_data(path):
    try:
        df = pd.read_csv(path, encoding='cp932') # Shift-JISで読み込みを試す
        return df
    except Exception as e:
        st.error(f"ファイル読み込みエラー: {e}")
        st.info("ヒント: ファイルの文字コードが'cp932'(Shift-JIS)または'utf-8'以外である可能性があります。")
        return None

df = load_data(DATA_PATH)

# データが正常に読み込めた場合のみ、後続の処理を実行
if df is not None:
    st.header('📊 出荷データのグラフ表示')
    st.write("元データ（先頭10行）")
    st.dataframe(df.head(10))

    # --- ここでグラフ用にデータを加工します ---
    # 例として、'出荷日'列を日付形式に変換し、'week_code'と'出荷数'を計算します。
    # ※ご自身のデータに合わせて列名を修正してください。
    
    # '出荷日'列が存在するか確認
    if '出荷日' in df.columns and '数量' in df.columns:
        try:
            # 日付形式への変換と週コードの作成
            df['出荷日'] = pd.to_datetime(df['出荷日'])
            df['week_code'] = df['出荷日'].dt.strftime('%Y-W%U')
            
            # 週ごとに出荷数を集計
            weekly_summary = df.groupby('week_code')['数量'].sum().reset_index()
            weekly_summary = weekly_summary.sort_values('week_code')

            st.write("週次集計データ")
            st.dataframe(weekly_summary)
            
            # --------------------------------------------------------------------------
            # グラフの描画
            # --------------------------------------------------------------------------
            fig, ax = plt.subplots(figsize=(12, 6))
            
            ax.bar(weekly_summary['week_code'], weekly_summary['数量'])
            
            # グラフの装飾
            ax.set_title('週ごとの合計出荷数', fontsize=16)
            ax.set_xlabel('週コード', fontsize=12)
            ax.set_ylabel('合計出荷数', fontsize=12)
            plt.xticks(rotation=45, ha='right') # X軸ラベルを斜めにして見やすくする
            plt.grid(axis='y', linestyle='--', alpha=0.7)
            plt.tight_layout()

            # Streamlitにグラフを表示
            st.pyplot(fig)

        except Exception as e:
            st.error(f"データ加工またはグラフ描画中にエラーが発生しました: {e}")
            st.warning("ヒント: '出荷日'列や'数量'列のデータ形式が想定と違う可能性があります。")
    else:
        st.warning("警告: グラフを作成するために必要な '出荷日' または '数量' 列が見つかりません。")
        st.info(f"利用可能な列: {df.columns.tolist()}")

else:
    st.error("データの読み込みに失敗したため、処理を中断しました。")

```

### ステップ2: Colabでアプリを起動し公開する

次に、別のColabセルで以下のコードを実行します。
これにより、必要なライブラリのインストール、Google Driveのマウント、そして先ほど作成した`app.py`を`ngrok`を使ってWeb上に公開する処理が行われます。


```python
# 1. 必要なライブラリのインストール
!pip install streamlit pyngrok japanize-matplotlib -q

# 2. Google Driveのマウント
from google.colab import drive
try:
    drive.mount('/content/drive', force_remount=True)
    print("✅ Google Driveのマウントに成功しました。")
except Exception as e:
    print(f"❌ Google Driveのマウント中にエラーが発生しました: {e}")
    # マウント失敗時はここで処理を停止
    exit()

# 3. ngrokのセットアップとStreamlitの起動
from pyngrok import ngrok
from google.colab import userdata
import os
import time

# Colabのシークレットからngrokの認証トークンを取得
# 事前にColabの左側にある鍵マークの「シークレット」に 'NGROK_AUTH_TOKEN' という名前で
# ご自身のトークンを登録しておいてください。
try:
    NGROK_TOKEN = userdata.get('NGROK_AUTH_TOKEN')
    ngrok.set_auth_token(NGROK_TOKEN)
except Exception as e:
    print(f"❌ エラー: ngrokの認証トークンがColabのシークレットに設定されていないようです。")
    print(f"詳細: {e}")
    exit()

# バックグラウンドでStreamlitサーバーを起動
# get_ipython().system_raw() を使うと、より安定してバックグラウンド実行できます。
get_ipython().system_raw('streamlit run app.py --server.headless true --server.port 8501 &')

# サーバーが起動するのを待つ
print("\n...Streamlitサーバーを起動中...")
time.sleep(5)

# ngrokでポート8501を公開
try:
    public_url = ngrok.connect(8501)
    print("✅ 準備完了！下のURLにアクセスしてください。")
    print(public_url)
except Exception as e:
    print(f"❌ エラー: ngrokトンネルの作成に失敗しました。")
    print("ヒント: ランタイムを一度リセットして、すべてのセルを最初から再実行してみてください。")
    print(f"詳細: {e}")
```

### 実行手順のまとめ

1.  **Colabのシークレット設定**: Colabの画面左側にある**鍵アイコン (シークレット)** をクリックし、`NGROK_AUTH_TOKEN` という名前でご自身のngrok認証トークンを保存します。
2.  **`app.py`の書き込み**: 最初のコードブロック（`%%writefile app.py ...`から始まるセル）を実行します。
3.  **アプリの起動**: ２番目のコードブロック（`!pip install ...`から始まるセル）を実行します。
4.  **アクセス**: 出力された `http://....ngrok.io` のようなURLをクリックすると、ブラウザでグラフが表示されたStreamlitアプリが立ち上がります。

### `app.py`のコードのポイント

* **データ加工**: `BOX_ID.csv` に `出荷日` と `数量` という列があることを想定して、週ごとの出荷数を集計するコードを追加しました。**もし列名が違う場合は、コード内の `'出荷日'` と `'数量'` の部分を実際の列名に修正してください。**
* **グラフ描画**: `matplotlib`で棒グラフを作成し、`st.pyplot(fig)`でStreamlit上に表示しています。これがStreamlitでグラフを表示する標準的な方法です。
* **エラー処理**: ファイルが読み込めない場合や、必要な列が存在しない場合にエラーや警告メッセージを表示するようにし、何が問題か分かりやすくしました。
* **キャッシュ**: `@st.cache_data`を使うことで、一度読み込んだデータをメモリに保持し、アプリの動作を高速化してい
