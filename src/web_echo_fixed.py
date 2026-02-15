"""
web_echo_fixed.py
Project Echo - Webブラウザ版（完全修正版）

【修正内容】
1. レート制限エラーへの対応強化
   - 待機時間: 60秒 → 120秒 → 180秒 → 240秒 → 300秒
   - リトライ回数: 5回
   - ターン間待機: 6秒

2. 予定調和の排除
   - 事前にプロットを作らない
   - キャラクター同士が自然に会話
   - 会話終了後に起承転結を分類
"""

from flask import Flask, render_template, request, jsonify, Response
import vertexai
from vertexai.preview.generative_models import GenerativeModel
import json
import time
import threading

# ========================================
# 設定
# ========================================
PROJECT_ID = "gen-lang-client-0239094918"
LOCATION = "us-central1"

app = Flask(__name__)
vertexai.init(project=PROJECT_ID, location=LOCATION)

progress_data = {
    "status": "waiting",
    "step": "",
    "message": "",
    "result": None
}

# ========================================
# ユーティリティ
# ========================================
def call_with_retry(model, prompt, max_retries=5, initial_wait=60):
    """
    レート制限に強いAPI呼び出し
    60秒 → 120秒 → 180秒 → 240秒 → 300秒
    """
    for attempt in range(max_retries):
        try:
            response = model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            if "429" in str(e) or "Resource exhausted" in str(e):
                wait_time = initial_wait * (attempt + 1)
                update_progress("generating", f"レート制限。{wait_time}秒待機... ({attempt+1}/{max_retries})")
                time.sleep(wait_time)
            else:
                if attempt == max_retries - 1:
                    raise
                time.sleep(10)
    raise Exception("API呼び出し失敗")

def extract_json(text):
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()
    return text

def update_progress(status, message, step=""):
    global progress_data
    progress_data["status"] = status
    progress_data["message"] = message
    progress_data["step"] = step
    print(f"[{step}] {message}")

# ========================================
# メインロジック
# ========================================
def generate_story(theme):
    """
    自然なストーリー生成
    """
    try:
        # ========== Step 1: キャラクター生成 ==========
        update_progress("generating", "キャラクター生成中...", "1/4")
        
        generator = GenerativeModel("gemini-2.0-flash-exp")
        
        text = call_with_retry(generator, f"""
{theme}で2人のキャラクターを生成。

JSON形式:
[
  {{"name": "3文字", "age": 17, "public_persona": "表(1文)", "secret_goal": "裏(1文)", "speech_style": "話し方"}}
]
""")
        characters = json.loads(extract_json(text))
        update_progress("generating", f"{len(characters)}人完了", "1/4")
        time.sleep(5)
        
        # ========== Step 2: 初期状況 ==========
        update_progress("generating", "初期状況生成中...", "2/4")
        
        char_info = "\n".join([f"{c['name']}: {c['secret_goal']}" for c in characters])
        
        initial_situation = call_with_retry(generator, f"""
{theme}のテーマで以下のキャラクターが出会う初期状況を1文で。

{char_info}
""")
        update_progress("generating", "初期状況完了", "2/4")
        time.sleep(5)
        
        # ========== Step 3: エージェント作成 ==========
        update_progress("generating", "エージェント作成中...", "3/4")
        
        agents = []
        for char in characters:
            instruction = f"""
あなたは{char['name']}。
性格: {char['public_persona']}
目的: {char['secret_goal']}
話し方: {char['speech_style']}

目的達成のために行動。他人は目的を知らない。

【重要】必ず以下のJSON形式で出力してください。他の文章は一切含めないでください。
{{"dialogue": "発言内容を1文で", "inner_thought": "内心の考えを1文で"}}

例:
{{"dialogue": "予算のことなんだけど...", "inner_thought": "どう切り出そうか"}}
"""
            agents.append({
                "name": char['name'],
                "model": GenerativeModel("gemini-2.0-flash-exp"),
                "instruction": instruction
            })
            time.sleep(3)
        
        update_progress("generating", "エージェント完了", "3/4")
        time.sleep(5)
        
        # ========== Step 4: 会話生成（10ターン） ==========
        update_progress("generating", "会話生成開始...", "4/4")
        
        conversation = []
        
        for turn in range(10):
            speaker = agents[turn % len(agents)]
            
            if turn == 0:
                prompt = f"{initial_situation}\n\n{speaker['name']}として最初に話しかけてください。\n\n必ずJSON形式のみで出力してください。"
            else:
                recent = conversation[-4:]
                prompt = f"{initial_situation}\n\n【これまでの会話】\n"
                for msg in recent:
                    prompt += f"{msg['speaker']}: {msg['dialogue']}\n"
                prompt += f"\n{speaker['name']}として返答してください。\n\n必ずJSON形式のみで出力してください。"
            
            try:
                update_progress("generating", f"会話中 ({turn+1}/10)...", "4/4")
                
                # instructionをプロンプトに含める
                full_prompt = f"{speaker['instruction']}\n\n{prompt}"
                text = call_with_retry(speaker['model'], full_prompt)
                data = json.loads(extract_json(text))
                
                conversation.append({
                    "speaker": speaker['name'],
                    "dialogue": data['dialogue'],
                    "inner_thought": data['inner_thought']
                })
                
                time.sleep(6)  # ターン間待機
                
            except Exception as e:
                print(f"ターン{turn+1}エラー: {e}")
                time.sleep(10)
                continue
        
        # ========== 起承転結に分類 ==========
        update_progress("generating", "起承転結に分類中...", "分類")
        
        size = len(conversation) // 4
        acts = [
            {"title": "起（状況設定）", "conversations": conversation[0:size]},
            {"title": "承（展開）", "conversations": conversation[size:size*2]},
            {"title": "転（転換）", "conversations": conversation[size*2:size*3]},
            {"title": "結（結末）", "conversations": conversation[size*3:]}
        ]
        
        time.sleep(5)
        
        # ========== 要約生成 ==========
        update_progress("generating", "要約生成中...", "要約")
        
        all_text = "\n".join([f"{m['speaker']}: {m['dialogue']}" for m in conversation])
        
        summary = call_with_retry(generator, f"""
以下を150字で要約:

テーマ: {theme}
{char_info}

会話:
{all_text}
""")
        
        # ========== 完了 ==========
        result = {
            "theme": theme,
            "characters": characters,
            "story": {"acts": acts},
            "summary": summary
        }
        
        progress_data["result"] = result
        update_progress("completed", "完了！", "完了")
        return result
        
    except Exception as e:
        update_progress("error", str(e), "エラー")
        import traceback
        traceback.print_exc()
        return None

# ========================================
# Webルート
# ========================================
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/generate', methods=['POST'])
def generate():
    global progress_data
    theme = request.json.get('theme', '')
    
    if not theme:
        return jsonify({"error": "テーマが必要"}), 400
    
    progress_data = {
        "status": "generating",
        "step": "",
        "message": "開始...",
        "result": None
    }
    
    thread = threading.Thread(target=generate_story, args=(theme,))
    thread.start()
    
    return jsonify({"status": "started"})

@app.route('/progress')
def progress():
    def generate():
        last = ""
        while True:
            current = f"{progress_data['step']}: {progress_data['message']}"
            if current != last:
                yield f"data: {json.dumps(progress_data, ensure_ascii=False)}\n\n"
                last = current
            if progress_data['status'] in ['completed', 'error']:
                break
            time.sleep(1)
    return Response(generate(), mimetype='text/event-stream')

@app.route('/result')
def result():
    if progress_data['status'] == 'completed' and progress_data['result']:
        return jsonify(progress_data['result'])
    return jsonify({"error": "結果なし"}), 404

# ========================================
# 実行
# ========================================
if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("Project Echo - 完全修正版")
    print("=" * 60)
    print("\n修正内容:")
    print("  ✓ レート制限対策強化（最大300秒待機）")
    print("  ✓ 予定調和排除（会話後に起承転結分類）")
    print("\nアクセス: http://localhost:5000")
    print("終了: Ctrl+C")
    print("=" * 60 + "\n")
    
    app.run(debug=True, host='0.0.0.0', port=5000)
