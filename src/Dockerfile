# Python 3.11をベースイメージとして使用
FROM python:3.11-slim

# 作業ディレクトリを設定
WORKDIR /app

# requirements.txtをコピーして依存関係をインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションファイルをコピー
COPY web_echo_fixed.py .
COPY templates/ templates/

# 環境変数を設定（Cloud Runが使用するポート）
ENV PORT=8080

# gunicornでアプリケーションを起動
# --timeout 0: タイムアウトなし（ストーリー生成に時間がかかるため）
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 web_echo_fixed:app