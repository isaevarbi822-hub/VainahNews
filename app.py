import os, sqlite3, threading, time, secrets, hmac
from datetime import datetime, timezone
from urllib.parse import urlparse
from flask import Flask, request, redirect, session, render_template_string, abort, jsonify, url_for
import feedparser
import requests

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY") or secrets.token_hex(32)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.getenv("COOKIE_SECURE", "0") == "1"
DB = os.getenv("DATABASE_PATH", "/tmp/vainahnews.sqlite3")
CATEGORIES = ["Мир", "Россия", "Кавказ", "Технологии", "Спорт", "Экономика", "Другое"]
FEEDS = [
 ("Мир","https://news.google.com/rss/headlines/section/topic/WORLD?hl=ru&gl=RU&ceid=RU:ru"),
 ("Россия","https://news.google.com/rss/search?q=Россия&hl=ru&gl=RU&ceid=RU:ru"),
 ("Кавказ","https://news.google.com/rss/search?q=Кавказ&hl=ru&gl=RU&ceid=RU:ru"),
 ("Технологии","https://news.google.com/rss/headlines/section/topic/TECHNOLOGY?hl=ru&gl=RU&ceid=RU:ru"),
 ("Спорт","https://news.google.com/rss/headlines/section/topic/SPORTS?hl=ru&gl=RU&ceid=RU:ru"),
 ("Экономика","https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=ru&gl=RU&ceid=RU:ru"),
 ("Другое","https://news.google.com/rss?hl=ru&gl=RU&ceid=RU:ru")
]
def db():
    c = sqlite3.connect(DB, timeout=20)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA busy_timeout=20000")
    return c
def init_db():
    with db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS articles(
            id INTEGER PRIMARY KEY, category TEXT, title TEXT, summary TEXT, image_url TEXT,
            source TEXT, url TEXT UNIQUE, published TEXT, visible INTEGER DEFAULT 1)""")
        c.execute("CREATE INDEX IF NOT EXISTS news_visible_date ON articles(visible,published DESC)")
init_db()

def img_url(item):
    candidates = []
    for m in item.get("media_content", []) + item.get("media_thumbnail", []):
        candidates.append(m.get("url", ""))
    for link in item.get("links", []):
        if str(link.get("type","")).startswith("image/"): candidates.append(link.get("href",""))
    for x in candidates:
        u=urlparse(x)
        if u.scheme=="https" and u.hostname and not u.username and not u.password:
            return x[:800]
    return ""

def sync():
    added=0
    for category,url in FEEDS:
        try:
            r=requests.get(url,timeout=12,headers={"User-Agent":"VainahNews/1.0 NewsReader"})
            r.raise_for_status()
            feed=feedparser.parse(r.content)
            with db() as c:
                for item in feed.entries[:35]:
                    link=str(item.get("link",""))[:1200]
                    title=str(item.get("title","")).strip()[:300]
                    if not title or not link.startswith("https://"): continue
                    import re, html
                    summary=re.sub(r"<[^>]+>"," ",str(item.get("summary","")))
                    summary=html.unescape(summary).strip()[:3500]
                    published=datetime.now(timezone.utc).isoformat()
                    cursor=c.execute("INSERT OR IGNORE INTO articles(category,title,summary,image_url,source,url,published) VALUES (?,?,?,?,?,?,?)",
                        (category,title,summary,img_url(item),feed.feed.get("title",category),link,published))
                    added+=cursor.rowcount
        except Exception as ex:
            app.logger.warning("RSS %s failed: %s",category,ex)
    return added

LAYOUT = """<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{title}} — VainahNews</title><style>
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:#0a111f;color:#eff4ff;font:16px system-ui,Arial}
header{padding:23px max(20px,5vw);display:flex;align-items:center;justify-content:space-between;background:#101d32;border-bottom:1px solid #243856}
a{color:#79bcff;text-decoration:none}header a{color:white}.brand{font-weight:900;font-size:26px}.wrap{max-width:1200px;margin:auto;padding:32px 22px}
h1{font-size:clamp(28px,4vw,45px);line-height:1.14}h2{font-size:22px}
input,textarea,select,button{font:inherit;border-radius:12px;padding:13px;color:white;background:#13243b;border:1px solid #375777}
button{background:#237de1;cursor:pointer}.search{display:flex;gap:8px}.search input{flex:1;min-width:0}
.tabs{display:flex;flex-wrap:wrap;gap:9px;margin:24px 0}.tabs a{padding:10px 14px;border:1px solid #304b6b;border-radius:30px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:18px}
.card{background:#132239;border:1px solid #294060;border-radius:18px;overflow:hidden}.card .inner{padding:19px}
.card img{height:165px;width:100%;object-fit:cover}p{line-height:1.75;color:#bac9df}.meta{font-size:13px;color:#8faacc}
.article{max-width:850px}.hero{width:100%;max-height:450px;object-fit:cover;border-radius:20px}
.article .text{white-space:pre-line;font-size:18px;line-height:1.9}.box{padding:24px;background:#132239;border-radius:18px;border:1px solid #294060}
label{display:block;margin:15px 0}label input,label textarea,label select{display:block;width:100%;margin-top:7px}
@media(max-width:550px){header{padding:16px}.search{flex-direction:column}}</style></head><body>
<header><a href="/" class="brand">Vainah<span style="color:#5eafff">News</span></a><nav><a href="/admin">Редакция</a></nav></header>
<main class="wrap">{{body|safe}}</main></body></html>"""

def page(title,body,**values):
    from flask import render_template_string
    content=render_template_string(body,**values)
    return render_template_string(LAYOUT,title=title,body=content)
def rowdicts(rows): return [dict(x) for x in rows]
def news_rows(q="",category="",limit=80):
    where=["visible=1"]; args=[]
    if category in CATEGORIES: where.append("category=?");args.append(category)
    if q: where.append("(title LIKE ? OR summary LIKE ?)");args += ["%"+q+"%"]*2
    with db() as c:
        return rowdicts(c.execute("SELECT * FROM articles WHERE "+" AND ".join(where)+" ORDER BY published DESC,id DESC LIMIT ?",args+[limit]).fetchall())
@app.get("/")
def home():
    q=request.args.get("q","").strip()[:100];cat=request.args.get("category","")
    articles=news_rows(q,cat)
    return page("Главная", """<h1>Новости со всего мира</h1><p>Главные события на русском языке. Публикации обновляются из RSS-источников.</p>
    <form method="get" class="search"><input name="q" value="{{q}}" placeholder="Поиск новостей..."><button>Найти</button></form>
    <div class="tabs"><a href="/">Все</a>{% for c in categories %}<a href="/?category={{c|urlencode}}">{{c}}</a>{% endfor %}</div>
    <div class="grid">{% for a in articles %}<div class="card">{% if a.image_url %}
    <img src="{{a.image_url}}" loading="lazy" referrerpolicy="no-referrer" onerror="this.style.display='none'" alt="">{% endif %}
    <div class="inner"><div class="meta">{{a.category}} · {{a.source}}</div><h2><a href="/article/{{a.id}}">{{a.title}}</a></h2>
    <p>{{a.summary[:380]}}{{'…' if a.summary|length>380 else ''}}</p></div></div>{% else %}<p>Публикаций пока нет. Администратор может запустить импорт RSS.</p>{% endfor %}</div>
    <script>setInterval(()=>{if(!document.hidden&&!location.search)location.reload()},300000)</script>""",
    articles=articles,categories=CATEGORIES,q=q)
@app.get("/article/<int:article_id>")
def article(article_id):
    with db() as c: a=c.execute("SELECT * FROM articles WHERE id=? AND visible=1",(article_id,)).fetchone()
    if not a:abort(404)
    return page(a["title"],"""<div class="article"><a href="/">← Все новости</a><h1>{{a.title}}</h1><p class="meta">{{a.category}} · {{a.source}}</p>
    {% if a.image_url %}<img class="hero" src="{{a.image_url}}" referrerpolicy="no-referrer" onerror="this.style.display='none'" alt="">{% endif %}
    <div class="text">{{a.summary}}</div><p>RSS может содержать только анонс, не полный текст.</p>
    {% if a.url %}<p><a href="{{a.url}}" target="_blank" rel="noopener noreferrer">Читать полную публикацию у источника ↗</a></p>{% endif %}</div>""",a=dict(a))
@app.get("/api/news")
def api_news():
    q=request.args.get("q","").strip()[:100]
    cat=request.args.get("category","")
    arr=news_rows(q,cat,limit=100)
    return jsonify({"articles":arr,"count":len(arr)})
@app.get("/health")
def health(): return jsonify({"ok":True,"service":"VainahNews"})
@app.route("/admin",methods=["GET","POST"])
def admin():
    password=os.getenv("ADMIN_PASSWORD")
    if request.method=="POST" and request.form.get("action")=="login":
        if not password: return "Set ADMIN_PASSWORD in Render Environment Variables",503
        if hmac.compare_digest(request.form.get("password",""),password): session["admin"]=True
        else: return "Неверный пароль",401
        return redirect("/admin")
    if not session.get("admin"):
        return page("Вход",'<div class="box"><h1>Вход в редакцию</h1><form method="post"><input type="hidden" name="action" value="login"><label>Пароль<input type="password" name="password" required></label><button>Войти</button></form></div>')
    if request.method=="POST":
        if request.form.get("token") != session.get("csrf"):abort(403)
        action=request.form.get("action")
        if action=="sync":sync()
        elif action=="publish":
            title=request.form.get("title","").strip()[:300]
            summary=request.form.get("summary","").strip()[:30000]
            category=request.form.get("category","Мир")
            if title and summary and category in CATEGORIES:
                with db() as c: c.execute("INSERT INTO articles(category,title,summary,image_url,source,url,published) VALUES (?,?,?,?,?,?,?)",
                    (category,title,summary,"","VainahNews — редакция",None,datetime.now(timezone.utc).isoformat()))
        return redirect("/admin")
    session.setdefault("csrf",secrets.token_urlsafe(24))
    with db() as c: count=c.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    return page("Редакция",'''<h1>Редакция VainahNews</h1><p>Всего материалов: {{count}}</p>
    <div class="box"><form method="post"><input type="hidden" name="token" value="{{token}}"><input type="hidden" name="action" value="sync"><button>Обновить RSS</button></form></div>
    <div class="box"><h2>Опубликовать собственную статью</h2><form method="post"><input type="hidden" name="token" value="{{token}}">
    <input type="hidden" name="action" value="publish">
    <label>Заголовок<input name="title" required maxlength="300"></label><label>Раздел<select name="category">{% for c in categories %}<option>{{c}}</option>{% endfor %}</select></label>
    <label>Текст<textarea name="summary" rows="18" required maxlength="30000"></textarea></label><button>Опубликовать</button></form></div>''',count=count,token=session["csrf"],categories=CATEGORIES)
if __name__=="__main__":app.run(port=int(os.getenv("PORT","5050")))
