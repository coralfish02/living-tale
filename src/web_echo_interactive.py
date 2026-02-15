"""
web_echo_interactive.py
Project Echo - AI自律対話型ドラマ生成システム

ユーザーが各フェーズ（起承転結）で方向性を指示できる
"""

from flask import Flask, render_template, request, jsonify
import vertexai
from vertexai.preview.generative_models import GenerativeModel
from vertexai.preview.vision_models import ImageGenerationModel
import json
import time
import threading
import base64

# ========================================
# 設定
# ========================================
# プロジェクトIDを環境変数または現在のgcloud設定から取得
import os
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT") or "project-da9ea0f1-155c-4d54-b47"
LOCATION = "us-central1"

app = Flask(__name__)

# CORS対応（開発環境用）
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

try:
    vertexai.init(project=PROJECT_ID, location=LOCATION)
    print(f"[INFO] Vertex AI 初期化完了: project={PROJECT_ID}, location={LOCATION}")
except Exception as e:
    print(f"[WARN] Vertex AI 初期化エラー: {e}")
    print("[WARN] Google Cloud認証が必要かもしれません: gcloud auth application-default login")

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
    起承転結の全フェーズを含む16コマ漫画を1枚の画像として生成する
    結フェーズ完了後に呼び出される
    """
    session = sessions.get(session_id)
    if not session:
        return

    print(f"[INFO] 16コマ漫画生成開始: {session_id}")
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

    # ★ 全フェーズの物語を取得
    all_conversation = session.get('conversation', [])
    characters = session.get('characters', [])
    char_desc = "、".join([f"{c['name']}（{c['age']}歳、{c['public_persona']}）" for c in characters])

    # 全フェーズの物語を1つの文章にまとめる
    full_story = {}
    for phase_key, phase_label in phases:
        phase_msgs = [m for m in all_conversation if m.get('phase') == phase_key]
        if phase_msgs:
            full_story[phase_key] = phase_msgs[0]['narrative']
        else:
            full_story[phase_key] = ""

    story_summary = "\n\n".join([f"【{phases[i][1]}】{full_story[phases[i][0]]}" for i in range(len(phases)) if full_story[phases[i][0]]])

    print(f"[INFO] 全体のストーリーコンテキスト取得完了（{len(story_summary)}文字）")

    # Step1: Geminiで16コマ漫画用の英語プロンプト生成
    print(f"[INFO] 16コマ漫画プロンプト生成中...")
    try:
        prompt_text = call_with_retry(generator, f"""
以下の物語全体を、16コマ漫画（4x4グリッド）のImagenプロンプトに変換してください。

【物語全体】
{story_summary}

【登場人物】
{char_desc}

【16コマ漫画レイアウト】
- 4x4グリッドレイアウト（縦4行×横4列）
- 1行目（上から1列目）：起フェーズ（4コマ）
- 2行目（上から2列目）：承フェーズ（4コマ）
- 3行目（上から3列目）：転フェーズ（4コマ）
- 4行目（上から4列目）：結フェーズ（4コマ）

【画像スタイル】
- アニメ風カラーイラスト
- 2人のキャラクターの容姿・服装を16コマ全体で統一
- マンガパネルスタイル
- 各コマに日本語の吹き出し

【出力条件】
- 60語以内の英語で出力
- プロンプト文のみ出力（説明不要）
- 16コマ漫画レイアウトであることを明記
""")
        time.sleep(8)  # Gemini レート制限対策
    except Exception as e:
        print(f"[ERROR] プロンプト生成失敗: {e}")
        session['comic_images'] = []
        session['comic_status'] = 'error'
        return

    # Step2: Imagenで16コマ漫画を1枚の画像として生成
    print(f"[INFO] 16コマ漫画生成中... プロンプト: {prompt_text[:60]}...")
    try:
        # ★ 16コマ漫画レイアウトを明示的に指定
        full_prompt = f"16-panel manga layout, 4x4 grid, anime style, colorful illustration, consistent character design, {prompt_text}, 2 characters, Japanese text in speech bubbles, manga panel style, same art style throughout all panels"

        images = imagen.generate_images(
            prompt=full_prompt,
            number_of_images=1,
            aspect_ratio="1:1",
            safety_filter_level="block_some",
            person_generation="allow_adult",
        )

        # 画像をファイルに保存
        filename = f"{session_id}_16panel.png"
        filepath = os.path.join(IMAGE_DIR, filename)
        images[0].save(location=filepath, include_generation_parameters=False)

        image_url = f"/static/images/{filename}"
        comic_images = [{
            "phase": "全体（16コマ）",
            "image_url": image_url,
            "prompt": prompt_text
        }]
        print(f"[OK] 16コマ漫画生成完了: {image_url}")

    except Exception as e:
        error_msg = str(e)
        print(f"[ERROR] 16コマ漫画生成失敗: {error_msg}")

        # 429エラーの場合は特別な処理
        if "429" in error_msg or "Quota exceeded" in error_msg:
            print(f"[WARN] API制限に達しました。60秒待機後にリトライします...")
            time.sleep(60)

            # リトライを1回だけ実行
            try:
                print(f"[INFO] 16コマ漫画生成をリトライ中...")
                images = imagen.generate_images(
                    prompt=full_prompt,
                    number_of_images=1,
                    aspect_ratio="1:1",
                    safety_filter_level="block_some",
                    person_generation="allow_adult",
                )

                filename = f"{session_id}_16panel.png"
                filepath = os.path.join(IMAGE_DIR, filename)
                images[0].save(location=filepath, include_generation_parameters=False)

                image_url = f"/static/images/{filename}"
                comic_images = [{
                    "phase": "全体（16コマ）",
                    "image_url": image_url,
                    "prompt": prompt_text
                }]
                print(f"[OK] 16コマ漫画生成完了（リトライ成功）: {image_url}")
            except Exception as retry_error:
                print(f"[ERROR] リトライも失敗: {retry_error}")
                comic_images = [{"phase": "全体（16コマ）", "image_url": None, "error": str(retry_error)}]
        else:
            comic_images = [{"phase": "全体（16コマ）", "image_url": None, "error": error_msg}]

    session['comic_images'] = comic_images
    session['comic_status'] = 'complete'
    print(f"[INFO] 16コマ漫画生成完了: {session_id}")

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

        # 3. 物語の題名生成
        session['progress'] = '物語の題名を生成中...'
        story_title = call_with_retry(generator, f"""
以下のテーマとキャラクターから、物語の題名を生成してください。

テーマ: {session['theme']}
登場人物: {char_info}

【題名の条件】
- 10文字以内
- 物語の雰囲気を表現
- 題名のみ出力（説明不要）
""")
        session['story_title'] = story_title.strip()
        time.sleep(8)  # ★安全のための待機

        # 4. 語り手モデル作成（第三者視点）
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
- どちらか一方の視点ではなく、客観的な第三者視点で描写すること
- セリフと行動・心理描写を織り交ぜること
- 読みやすく、自然な文章で描写すること
- 文頭は「その日、」「カフェの中で、」など情景から始めること

出力形式（JSON）:
{{
  "narrative": "第三者視点の地の文（両キャラクターが登場する自然な文章）",
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
            "story_title": session['story_title'],
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

    # フェーズ名のマッピング
    phase_titles = {
        'ki': '起（状況設定・出会い）',
        'sho': '承（展開・関係の深まり）',
        'ten': '転（転換・意外な展開）',
        'ketsu': '結（結末・変化）'
    }

    for turn in range(config['turns']):
        progress_msg = f"{config['label']} ({turn+1}/{config['turns']}ターン目)"
        print(f"[INFO] {progress_msg}")

        # プロンプト作成（第三者視点）
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
            # 1. 語り手モデルで第三者視点の場面生成
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
以下の物語を250文字～300文字で要約してください。

テーマ: {session['theme']}

物語:
{all_text}

【要約の条件】
- 250文字～300文字で記述
- 起承転結の流れを含めること
- 読みやすく簡潔な文章で記述すること
- 物語の核心と結末を明確に
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
    try:
        if not request.is_json:
            return jsonify({"error": "JSON形式のリクエストが必要です"}), 400
        
        data = request.json
        if not data:
            return jsonify({"error": "リクエストデータが空です"}), 400
        
        theme = data.get('theme', '')
        if not theme:
            return jsonify({"error": "テーマが必要"}), 400
        
        print(f"[INFO] 新しいセッション開始: テーマ='{theme}'")
        
        session_id = str(int(time.time() * 1000))
        sessions[session_id] = {'theme': theme, 'current_phase': 'start', 'status': 'initializing'}
        
        def init_session():
            try:
                print(f"[DEBUG] セッション {session_id} 開始")
                result = generate_phase(session_id, 'start')
                sessions[session_id].update(result)
                sessions[session_id]['current_phase'] = 'ki'
                sessions[session_id]['status'] = 'ready'
                print(f"[INFO] セッション {session_id} 初期化完了")
            except Exception as e:
                import traceback
                print(f"[ERROR] 初期化失敗: {e}")
                print(f"[ERROR] トレースバック:\n{traceback.format_exc()}")
                sessions[session_id]['status'] = 'error'
                sessions[session_id]['error'] = str(e)
        
        thread = threading.Thread(target=init_session, daemon=True)
        thread.start()
        
        print(f"[INFO] セッション作成完了: session_id={session_id}")
        print(f"[DEBUG] 返却データ: {{'session_id': '{session_id}', 'status': 'initializing'}}")
        
        return jsonify({
            "session_id": session_id, 
            "status": "initializing"
        })
    except Exception as e:
        import traceback
        print(f"[ERROR] /start エンドポイントエラー: {e}")
        print(f"[ERROR] トレースバック:\n{traceback.format_exc()}")
        return jsonify({"error": f"サーバーエラー: {str(e)}"}), 500

@app.route('/status/<session_id>')
def status(session_id):
    try:
        print(f"[DEBUG] ステータス取得リクエスト: session_id={session_id}")
        print(f"[DEBUG] 現在のセッション数: {len(sessions)}")
        print(f"[DEBUG] セッションID一覧: {list(sessions.keys())[:5]}")
        
        session = sessions.get(session_id)
        if not session:
            print(f"[WARN] セッションが見つかりません: {session_id}")
            return jsonify({
                "error": "セッションが見つかりません",
                "status": "not_found",
                "session_id": session_id
            }), 404
        
        status_data = {
            "status": session.get('status', 'initializing'),
            "current_phase": session.get('current_phase'),
            "characters": session.get('characters'),
            "initial_situation": session.get('initial_situation'),
            "conversation": session.get('conversation', []),
            "progress": session.get('progress', ''),
            "next_phase": session.get('next_phase') or session.get('current_phase'),
            "story": session.get('story')
        }
        
        # 会話が更新された場合は、next_phaseも更新
        if session.get('conversation') and len(session.get('conversation', [])) > 0:
            # 最後の会話のフェーズを確認
            last_conv = session.get('conversation', [])[-1]
            if last_conv.get('phase'):
                current_phase = last_conv.get('phase')
                phase_order = ['ki', 'sho', 'ten', 'ketsu']
                try:
                    current_index = phase_order.index(current_phase)
                    if current_index < len(phase_order) - 1:
                        status_data['next_phase'] = phase_order[current_index + 1]
                    else:
                        status_data['next_phase'] = 'complete'
                except ValueError:
                    pass
        
        if session.get('error'):
            status_data['error'] = session.get('error')
        
        print(f"[DEBUG] ステータス返却: status={status_data.get('status')}")
        return jsonify(status_data)
    except Exception as e:
        import traceback
        print(f"[ERROR] /status エンドポイントエラー: {e}")
        print(f"[ERROR] トレースバック:\n{traceback.format_exc()}")
        return jsonify({"error": f"サーバーエラー: {str(e)}"}), 500

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

@app.route('/comic/retry/<session_id>', methods=['POST'])
def comic_retry(session_id):
    """4コマ漫画の再生成"""
    session = sessions.get(session_id)
    if not session:
        return jsonify({"error": "セッションが見つかりません"}), 404

    data = request.json
    phase = data.get('phase')
    index = data.get('index')

    # TODO: 特定のパネルの再生成機能を実装
    # 現時点では成功を返す
    return jsonify({
        "status": "retry_initiated",
        "message": "再生成を開始しました（実装予定）"
    })

@app.route('/suggestions/<session_id>')
def suggestions(session_id):
    """次のフェーズへの方向性提案を返す（AIで生成）"""
    session = sessions.get(session_id)
    if not session:
        return jsonify({"error": "セッションが見つかりません"}), 404

    # すでに提案がある場合はキャッシュを返す
    phase = session.get('current_phase', 'ki')
    cache_key = f'suggestions_{phase}'
    if session.get(cache_key):
        return jsonify({"suggestions": session[cache_key]})

    # Geminiで提案を生成
    def generate_suggestions():
        try:
            generator = GenerativeModel("gemini-2.0-flash-001")
            conversation = session.get('conversation', [])
            recent = conversation[-2:] if conversation else []
            story_so_far = "\n".join([m['narrative'] for m in recent]) if recent else "（まだ物語が始まっていません）"

            phase_names = {'ki': '起', 'sho': '承', 'ten': '転', 'ketsu': '結'}
            phase_label = phase_names.get(phase, phase)

            text = call_with_retry(generator, f"""
テーマ: {session['theme']}
現在のフェーズ: {phase_label}

【これまでの物語】
{story_so_far}

次の「{phase_label}」フェーズに加えると面白くなる展開を3つ提案してください。
各提案は15文字以内の短い一文にしてください。

JSON形式で出力:
{{"suggestions": ["提案1", "提案2", "提案3"]}}
""")
            data = json.loads(extract_json(text))
            session[cache_key] = data.get('suggestions', [])
        except Exception as e:
            print(f"[ERROR] 提案生成失敗: {e}")
            session[cache_key] = []

    # バックグラウンドで生成
    thread = threading.Thread(target=generate_suggestions, daemon=True)
    thread.start()

    return jsonify({"suggestions": session.get(cache_key, [])})

if __name__ == '__main__':
    # デバッグモード無効化（自動リロードを防ぐ）
    app.run(debug=False, host='0.0.0.0', port=5000)