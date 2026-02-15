"""
web_echo_interactive.py
Project Echo - インタラクティブ版 (安全策・順次実行版)

ユーザーが各フェーズ（起承転結）で方向性を指示できる
"""

from flask import Flask, render_template, request, jsonify
import vertexai
from vertexai.preview.generative_models import GenerativeModel
from vertexai.preview.vision_models import ImageGenerationModel
import json
import time
import threading
import os
import base64

# ========================================
# 設定
# ========================================
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT") or "YOUR_PROJECT_ID"
LOCATION = "us-central1"

app = Flask(__name__)
vertexai.init(project=PROJECT_ID, location=LOCATION)

# 画像保存ディレクトリ
IMAGE_DIR = os.path.join(os.path.dirname(__file__), 'static', 'images')
os.makedirs(IMAGE_DIR, exist_ok=True)

# セッションデータ
sessions = {}

# ========================================
# ユーティリティ
# ========================================
def call_with_retry(model, prompt, max_retries=5, initial_wait=60):
    """レート制限対策付きAPI呼び出し（タイムアウト付き）"""
    import concurrent.futures
    
    for attempt in range(max_retries):
        try:
            print(f"[DEBUG] API呼び出し開始 (試行 {attempt+1}/{max_retries})")
            
            # 60秒タイムアウト付きで実行
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(model.generate_content, prompt)
                try:
                    response = future.result(timeout=60)
                    print(f"[DEBUG] API呼び出し成功")
                    return response.text.strip()
                except concurrent.futures.TimeoutError:
                    print(f"[ERROR] タイムアウト（60秒）- 試行 {attempt+1}/{max_retries}")
                    if attempt == max_retries - 1:
                        raise Exception("APIタイムアウト：60秒以内に応答がありませんでした")
                    time.sleep(10)
                    continue

        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg or "Resource exhausted" in error_msg:
                wait_time = initial_wait * (attempt + 1)
                print(f"[WARN] レート制限検知。{wait_time}秒待機... (試行 {attempt+1}/{max_retries})")
                time.sleep(wait_time)
            elif "タイムアウト" in error_msg:
                raise
            else:
                if attempt == max_retries - 1:
                    raise
                print(f"[WARN] エラー: {error_msg} - 10秒後に再試行")
                time.sleep(10)
    raise Exception("API呼び出し失敗")

def extract_json(text):
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()
    return text

# ========================================
# 4コマ漫画生成
# ========================================
def generate_comic(session_id):
    """
    起承転結の各フェーズから1枚ずつ、計4枚の画像を生成する
    結フェーズ完了後に呼び出される
    """
    session = sessions.get(session_id)
    if not session:
        return

    print(f"[INFO] 4コマ漫画生成開始: {session_id}")
    session['comic_status'] = 'generating'
    session['comic_images'] = []

    generator = GenerativeModel("gemini-2.0-flash-001")
    imagen = ImageGenerationModel.from_pretrained("imagen-3.0-generate-002")

    phases = [
        ('ki',    '起'),
        ('sho',   '承'),
        ('ten',   '転'),
        ('ketsu', '結'),
    ]

    comic_images = []

    for phase_key, phase_label in phases:
        # そのフェーズの会話を取得
        phase_msgs = [m for m in session.get('conversation', []) if m.get('phase') == phase_key]
        if not phase_msgs:
            print(f"[WARN] {phase_label}フェーズの会話が見つかりません")
            comic_images.append({
                "phase": phase_label,
                "image_url": None,
                "error": "会話なし"
            })
            continue

        narrative = phase_msgs[0]['narrative']
        characters = session.get('characters', [])
        char_desc = "、".join([f"{c['name']}({c['public_persona']})" for c in characters])

        # Step1: Geminiで英語プロンプト生成
        print(f"[INFO] {phase_label}フェーズのプロンプト生成中...")
        try:
            prompt_text = call_with_retry(generator, f"""
以下の日本語の場面描写を、Imagen画像生成用の英語プロンプトに変換してください。

場面:
{narrative}

登場人物: {char_desc}

条件:
- アニメ風カラーイラストのスタイル
- 2人のキャラクターが登場する
- 感情や雰囲気を視覚的に表現する
- 30語以内の英語で出力
- プロンプト文のみ出力（説明不要）
""")
            time.sleep(8)  # Gemini レート制限対策
        except Exception as e:
            print(f"[ERROR] {phase_label}プロンプト生成失敗: {e}")
            comic_images.append({"phase": phase_label, "image_url": None, "error": str(e)})
            continue

        # Step2: Imagenで画像生成
        print(f"[INFO] {phase_label}フェーズの画像生成中... プロンプト: {prompt_text[:60]}...")
        try:
            full_prompt = f"anime style, colorful illustration, {prompt_text}, 2 characters, detailed background, manga panel"

            images = imagen.generate_images(
                prompt=full_prompt,
                number_of_images=1,
                aspect_ratio="1:1",
                safety_filter_level="block_some",
                person_generation="allow_adult",
            )

            # 画像をファイルに保存
            filename = f"{session_id}_{phase_key}.png"
            filepath = os.path.join(IMAGE_DIR, filename)
            images[0].save(location=filepath, include_generation_parameters=False)

            image_url = f"/static/images/{filename}"
            comic_images.append({
                "phase": phase_label,
                "image_url": image_url,
                "prompt": prompt_text
            })
            print(f"[OK] {phase_label}フェーズの画像生成完了: {image_url}")
            # Imagenはレート制限なし → sleepなし

        except Exception as e:
            print(f"[ERROR] {phase_label}画像生成失敗: {e}")
            comic_images.append({"phase": phase_label, "image_url": None, "error": str(e)})
            continue

    session['comic_images'] = comic_images
    session['comic_status'] = 'complete'
    print(f"[INFO] 4コマ漫画生成完了: {session_id}")

# ========================================
# フェーズ別生成
# ========================================
def generate_phase(session_id, phase, user_direction=""):
    session = sessions.get(session_id)
    if not session:
        return {"error": "セッションが見つかりません"}
    
    # モデル設定 
    generator = GenerativeModel("gemini-2.0-flash-001")
    
    # ========== start: 初期設定 ==========
    if phase == 'start':
        print(f"[DEBUG] セッション {session_id}: キャラクター生成開始")
        session['progress'] = 'キャラクター生成中...'
        
        # 1. キャラクター生成
        text = call_with_retry(generator, f"""
{session['theme']}で2人のキャラクターを生成。

JSON形式:
[
  {{"name": "3文字", "age": 17, "public_persona": "表(1文)", "secret_goal": "裏(1文)", "speech_style": "話し方"}}
]
""")
        time.sleep(8)  # ★安全のための待機 (10 RPM対策)

        print(f"[DEBUG] セッション {session_id}: キャラクター生成完了")
        characters = json.loads(extract_json(text))
        session['characters'] = characters
        session['progress'] = '初期状況を生成中...'
        
        # 2. 初期状況生成
        char_info = "\n".join([f"{c['name']}: {c['secret_goal']}" for c in characters])
        initial_situation = call_with_retry(generator, f"""
{session['theme']}で以下のキャラクターが出会う初期状況を1文で。

{char_info}
""")
        session['initial_situation'] = initial_situation
        time.sleep(8)  # ★安全のための待機
        
        # 3. 語り手モデル作成 (APIコールなし)
        # 一人称視点ではなく、両キャラクターが登場する第三者視点に変更
        char_names = [c['name'] for c in characters]
        char_profiles = "\n".join([
            f"{c['name']}（{c['age']}歳）: 性格={c['public_persona']} / 目的={c['secret_goal']} / 話し方={c['speech_style']}"
            for c in characters
        ])
        
        narrator_instruction = f"""
あなたは小説の語り手です。
登場人物2人が会話・行動する場面を、第三者視点の小説風地の文で描写してください。

登場人物:
{char_profiles}

【重要ルール】
- 必ず{char_names[0]}と{char_names[1]}の両方を登場させること
- どちらか一方の名前だけで文頭を始めない
- セリフと行動・心理描写を織り交ぜること
- 文頭は「その日、」「カフェの中で、」など情景から始めること

出力形式（JSON）:
{{
  "narrative": "第三者視点の地の文（両キャラクターが登場する）",
  "inner_thought": "この場面全体の雰囲気や核心を1文で"
}}
必ずJSON形式のみで出力してください。
"""
        
        session['narrator'] = {
            "model": GenerativeModel("gemini-2.0-flash-001"),
            "instruction": narrator_instruction,
            "char_names": char_names,
            "char_profiles": char_profiles
        }
        # 後方互換のため agents も残す（内心生成で使用）
        agents = []
        for char in characters:
            agents.append({
                "name": char['name'],
                "model": GenerativeModel("gemini-2.0-flash-001"),
                "instruction": ""
            })
        session['agents'] = agents
        session['conversation'] = []
        
        return {
            "status": "ready",
            "characters": characters,
            "initial_situation": initial_situation,
            "next_phase": "ki"
        }
    
    # ========== ki, sho, ten, ketsu: 会話生成 ==========
    phase_config = {
        'ki': {'turns': 1, 'next': 'sho', 'title': '起（状況設定）', 'label': '【起】状況設定を生成中'},
        'sho': {'turns': 1, 'next': 'ten', 'title': '承（展開）', 'label': '【承】物語の展開を生成中'},
        'ten': {'turns': 1, 'next': 'ketsu', 'title': '転（転換）', 'label': '【転】転換点を生成中'},
        'ketsu': {'turns': 1, 'next': 'complete', 'title': '結（結末）', 'label': '【結】結末を生成中'}
    }
    
    config = phase_config.get(phase)
    if not config:
        return {"error": "無効なフェーズ"}
    
    agents = session['agents']
    narrator = session['narrator']
    conversation = session['conversation']
    initial_situation = session['initial_situation']
    direction_text = f"\n\n【ユーザーの希望】\n{user_direction}" if user_direction else ""
    phase_conversations = []
    
    for turn in range(config['turns']):
        progress_msg = f"{config['label']} ({turn+1}/{config['turns']}ターン目)"
        print(f"[INFO] {progress_msg}")
        
        # プロンプト作成（第三者視点）
        phase_titles = {
            'ki': '起（状況設定・出会い）',
            'sho': '承（展開・関係の深まり）',
            'ten': '転（転換・意外な展開）',
            'ketsu': '結（結末・変化）'
        }
        phase_title = phase_titles.get(phase, phase)
        
        if len(conversation) == 0:
            prompt = f"""
初期状況: {initial_situation}
{direction_text}

これは物語の「{phase_title}」の場面です。
{narrator['char_names'][0]}と{narrator['char_names'][1]}が登場する場面を描写してください。

必ずJSON形式のみで出力してください。
"""
        else:
            recent = conversation[-4:]
            story_so_far = "\n\n".join([m['narrative'] for m in recent])
            prompt = f"""
初期状況: {initial_situation}

【これまでの物語】
{story_so_far}
{direction_text}

これは物語の「{phase_title}」の場面です。
上記の流れを受けて、{narrator['char_names'][0]}と{narrator['char_names'][1]}が登場する続きの場面を描写してください。

必ずJSON形式のみで出力してください。
"""
        
        try:
            # 語り手モデルで第三者視点の場面生成
            full_prompt = f"{narrator['instruction']}\n\n{prompt}"
            text = call_with_retry(narrator['model'], full_prompt)
            data = json.loads(extract_json(text))
            
            msg = {
                "speaker": f"{narrator['char_names'][0]}・{narrator['char_names'][1]}",
                "narrative": data.get('narrative', ''),
                "inner_thought": data.get('inner_thought', ''),
                "phase": phase
            }
            
            time.sleep(8)  # ★安全のための待機 (ここが重要)
            
            # 2. 全キャラクターの内心を順次生成（並列処理から変更）
            all_inner_thoughts = []
            
            for agent in agents:
                print(f"[DEBUG] {agent['name']}の内心を生成中...")
                inner_prompt = f"""
以下の場面における{agent['name']}の内心を1文で表現してください。

場面: {msg['narrative']}

あなたは{agent['name']}です。
性格: {[c for c in session['characters'] if c['name'] == agent['name']][0]['public_persona']}
目的: {[c for c in session['characters'] if c['name'] == agent['name']][0]['secret_goal']}

JSON形式で出力:
{{"inner_thought": "内心の考え（1文）"}}
"""
                try:
                    inner_text = call_with_retry(agent['model'], inner_prompt)
                    inner_data = json.loads(extract_json(inner_text))
                    all_inner_thoughts.append({
                        "character": agent['name'],
                        "thought": inner_data.get('inner_thought', '')
                    })
                    
                    time.sleep(8)  # ★各APIコールの後に必ず待機
                    
                except Exception as e:
                    print(f"内心生成エラー ({agent['name']}): {e}")
                    all_inner_thoughts.append({
                        "character": agent['name'],
                        "thought": "..."
                    })
            
            msg['all_inner_thoughts'] = all_inner_thoughts
            conversation.append(msg)
            phase_conversations.append(msg)
            
        except Exception as e:
            print(f"エラー: {e}")
            time.sleep(10)
            continue
    
    session['conversation'] = conversation
    
    # ========== complete: 要約生成 ==========
    if config['next'] == 'complete':
        all_text = "\n\n".join([m['narrative'] for m in conversation])
        summary = call_with_retry(generator, f"""
以下の物語を150字で要約:

テーマ: {session['theme']}

会話:
{all_text}
""")
        session['summary'] = summary
        
        story = {
            'ki': [m for m in conversation if m.get('phase') == 'ki'],
            'sho': [m for m in conversation if m.get('phase') == 'sho'],
            'ten': [m for m in conversation if m.get('phase') == 'ten'],
            'ketsu': [m for m in conversation if m.get('phase') == 'ketsu']
        }

        # ★ 4コマ漫画生成を非同期で開始（物語表示をブロックしない）
        session['comic_status'] = 'generating'
        session['comic_images'] = []
        comic_thread = threading.Thread(
            target=generate_comic,
            args=(session_id,),
            daemon=True
        )
        comic_thread.start()
        print(f"[INFO] 4コマ漫画生成スレッド起動")
        
        return {
            "status": "complete",
            "phase": config['title'],
            "conversations": phase_conversations,
            "next_phase": None,
            "story": story,
            "summary": summary,
            "characters": session['characters']
        }
    
    return {
        "status": "continue",
        "phase": config['title'],
        "conversations": phase_conversations,
        "next_phase": config['next']
    }

# ========================================
# Webルート (変更なし)
# ========================================
@app.route('/')
def index():
    return render_template('index_interactive.html')

@app.route('/start', methods=['POST'])
def start():
    data = request.json
    theme = data.get('theme', '')
    if not theme:
        return jsonify({"error": "テーマが必要"}), 400
    
    session_id = str(int(time.time() * 1000))
    sessions[session_id] = {'theme': theme, 'current_phase': 'start', 'status': 'initializing'}
    
    def init_session():
        try:
            print(f"[DEBUG] セッション {session_id} 開始")
            result = generate_phase(session_id, 'start')
            sessions[session_id].update(result)
            sessions[session_id]['current_phase'] = 'ki'
            sessions[session_id]['status'] = 'ready'
        except Exception as e:
            print(f"[ERROR] 初期化失敗: {e}")
            sessions[session_id]['status'] = 'error'
            sessions[session_id]['error'] = str(e)
    
    thread = threading.Thread(target=init_session, daemon=True)
    thread.start()
    return jsonify({"session_id": session_id, "status": "initializing"})

@app.route('/status/<session_id>')
def status(session_id):
    session = sessions.get(session_id)
    if not session:
        return jsonify({"error": "セッションが見つかりません"}), 404
    return jsonify({
        "status": session.get('status', 'initializing'),
        "current_phase": session.get('current_phase'),
        "characters": session.get('characters'),
        "initial_situation": session.get('initial_situation'),
        "conversation": session.get('conversation', []),
        "progress": session.get('progress', ''),
        "next_phase": session.get('next_phase'),
        "story": session.get('story')
    })

@app.route('/continue', methods=['POST'])
def continue_story():
    data = request.json
    session_id = data.get('session_id')
    user_direction = data.get('direction', '')
    session = sessions.get(session_id)
    if not session:
        return jsonify({"error": "セッションなし"}), 404
    
    current_phase = session.get('current_phase')
    session['status'] = 'generating'
    session['progress'] = f'{current_phase}フェーズを生成中...'
    
    def generate():
        try:
            result = generate_phase(session_id, current_phase, user_direction)
            if result.get('next_phase'):
                session['current_phase'] = result['next_phase']
            if result.get('status') == 'complete':
                session['status'] = 'complete'
                session['story'] = result.get('story')
                session['summary'] = result.get('summary')
            else:
                session['status'] = 'continue'
        except Exception as e:
            print(f"[ERROR] 生成失敗: {e}")
            session['status'] = 'error'
            session['error'] = str(e)
            
    thread = threading.Thread(target=generate, daemon=True)
    thread.start()
    return jsonify({"status": "generating"})

@app.route('/result/<session_id>')
def result(session_id):
    session = sessions.get(session_id)
    if not session or session.get('status') != 'complete':
        return jsonify({"error": "完了していません"}), 400
    return jsonify({
        "theme": session['theme'],
        "characters": session['characters'],
        "story": session['story'],
        "summary": session['summary']
    })

@app.route('/comic/<session_id>')
def comic(session_id):
    """4コマ漫画の生成状況と画像URLを返す"""
    session = sessions.get(session_id)
    if not session:
        return jsonify({"error": "セッションが見つかりません"}), 404
    return jsonify({
        "comic_status": session.get('comic_status', 'not_started'),
        "comic_images": session.get('comic_images', [])
    })

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)