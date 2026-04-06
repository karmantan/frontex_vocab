from __future__ import annotations
import json
import os
import random
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
DB_PATH=Path("vocab_quiz.db")
ADMIN_TOKEN=os.getenv("ADMIN_TOKEN","change-me")
app=FastAPI(title="Vocabulary Quiz API",version="3.0.0")
app.add_middleware(CORSMiddleware,allow_origins=["*"],allow_credentials=True,allow_methods=["*"],allow_headers=["*"])
INDEX_HTML="""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Vocabulary Quiz</title>
<style>
body{font-family:Arial,sans-serif;max-width:980px;margin:40px auto;padding:0 16px;background:#f8fafc;color:#0f172a}
.card{background:#fff;border:1px solid #e2e8f0;border-radius:16px;padding:20px;margin-bottom:16px}
input,button,select{font:inherit}
input,select{width:100%;padding:12px;border:1px solid #cbd5e1;border-radius:12px;box-sizing:border-box}
button{padding:12px 16px;border:0;border-radius:12px;background:#0f172a;color:#fff;cursor:pointer}
button.secondary{background:#e2e8f0;color:#0f172a}
.row{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px}
.small{font-size:14px;color:#475569}
.good{color:#15803d;font-weight:700}
.bad{color:#b91c1c;font-weight:700}
.hidden{display:none}
a{color:#0f172a}
</style>
</head>
<body>
<h1>Frontex vocab quiz</h1>
<div class="card">
<h2>Deck, category, and mode</h2>
<div class="row">
<select id="deckSelect"></select>
<select id="categorySelect"></select>
<select id="modeSelect">
<option value="selected">Selected category</option>
<option value="mistakes">Mistakes only</option>
<option value="mixed">Mixed review</option>
</select>
</div>
<div style="margin-top:12px"><button class="secondary" onclick="loadDecks()">refresh</button></div>
<p class="small" id="deckInfo"></p>
<p class="small" id="queueSummary">Review queue: 0 items</p>
</div>
<div class="card">
<h2>Quiz</h2>
<div id="quizBox" class="hidden">
<p class="small">German prompt</p>
<h3 id="prompt"></h3>
<p class="small" id="categoryLabel"></p>
<input id="answer" placeholder="type the english answer" onkeydown="if(event.key==='Enter'){submitAnswer()}">
<div style="margin-top:12px;display:flex;gap:8px">
<button onclick="submitAnswer()">submit</button>
<button class="secondary" onclick="nextItem()">skip</button>
</div>
<p id="feedback" style="margin-top:12px"></p>
</div>
<p id="quizEmpty" class="small">no public deck available yet.</p>
</div>
<p class="small">Admin page: <a href="/admin">/admin</a></p>
<script>
const playerId=localStorage.getItem('player_id')||crypto.randomUUID();
localStorage.setItem('player_id',playerId);
let currentDeckId=null;
let currentItem=null;
async function api(path,options={}){
  const res=await fetch(path,{headers:{'Content-Type':'application/json'},...options});
  if(!res.ok){const text=await res.text();throw new Error(text||res.statusText);}
  return res.json();
}
function currentCategory(){
  const value=document.getElementById('categorySelect').value;
  return value||null;
}
function currentMode(){
  return document.getElementById('modeSelect').value;
}
async function loadDecks(){
  const data=await api('/api/decks');
  const deckSelect=document.getElementById('deckSelect');
  deckSelect.innerHTML='';
  for(const deck of data.decks){
    const opt=document.createElement('option');
    opt.value=deck.id;
    opt.textContent=`${deck.name} (${deck.item_count})`;
    deckSelect.appendChild(opt);
  }
  if(data.decks.length){
    currentDeckId=deckSelect.value;
    document.getElementById('deckInfo').textContent=`player id: ${playerId}`;
    document.getElementById('quizBox').classList.remove('hidden');
    document.getElementById('quizEmpty').classList.add('hidden');
    await loadCategories();
    await loadQueueSummary();
    await nextItem();
  }else{
    document.getElementById('deckInfo').textContent='';
    document.getElementById('quizBox').classList.add('hidden');
    document.getElementById('quizEmpty').classList.remove('hidden');
    document.getElementById('queueSummary').textContent='Review queue: 0 items';
  }
}
async function loadCategories(){
  if(!currentDeckId)return;
  const data=await api(`/api/decks/${currentDeckId}/categories`);
  const select=document.getElementById('categorySelect');
  const previous=select.value;
  select.innerHTML='';
  const all=document.createElement('option');
  all.value='';
  all.textContent='All categories';
  select.appendChild(all);
  for(const category of data.categories){
    const opt=document.createElement('option');
    opt.value=category;
    opt.textContent=category;
    select.appendChild(opt);
  }
  if([...select.options].some(x=>x.value===previous)){select.value=previous;}
}
document.getElementById('deckSelect').addEventListener('change',async(e)=>{
  currentDeckId=e.target.value;
  await loadCategories();
  await loadQueueSummary();
  await nextItem();
});
document.getElementById('categorySelect').addEventListener('change',async()=>{
  await loadQueueSummary();
  await nextItem();
});
document.getElementById('modeSelect').addEventListener('change',async()=>{
  await loadQueueSummary();
  await nextItem();
});
async function loadQueueSummary(){
  if(!currentDeckId)return;
  const category=currentCategory();
  const suffix=category?`&category=${encodeURIComponent(category)}`:'';
  const data=await api(`/api/decks/${currentDeckId}/mistake_queue/summary?player_id=${encodeURIComponent(playerId)}${suffix}`);
  const mode=currentMode();
  if(mode==='selected'){
    document.getElementById('queueSummary').textContent=`Review queue: ${data.scoped_queue} items in this category, ${data.total_queue} total`;
  }else if(mode==='mistakes'){
    document.getElementById('queueSummary').textContent=`Mistakes only: ${data.scoped_queue} items ready for review`;
  }else{
    document.getElementById('queueSummary').textContent=`Mixed review: ${data.total_queue} queued mistakes will be mixed into practice`;
  }
}
async function nextItem(){
  if(!currentDeckId)return;
  try{
    const data=await api(`/api/decks/${currentDeckId}/next`,{method:'POST',body:JSON.stringify({player_id:playerId,current_item_id:currentItem?.item_id||null,category:currentCategory(),mode:currentMode()})});
    currentItem=data;
    document.getElementById('prompt').textContent=data.german;
    document.getElementById('answer').value='';
    document.getElementById('feedback').textContent='';
    document.getElementById('categoryLabel').textContent=`category: ${data.category}`;
    document.getElementById('answer').focus();
  }catch(err){
    currentItem=null;
    document.getElementById('prompt').textContent='No items available for this selection.';
    document.getElementById('categoryLabel').textContent='';
    document.getElementById('feedback').textContent='';
  }
}
async function submitAnswer(){
  if(!currentDeckId||!currentItem)return;
  const answer=document.getElementById('answer').value;
  const data=await api(`/api/decks/${currentDeckId}/answer`,{method:'POST',body:JSON.stringify({player_id:playerId,item_id:currentItem.item_id,answer})});
  document.getElementById('feedback').innerHTML=data.correct?`<span class="good">correct</span>`:`<span class="bad">wrong</span> — correct answer: ${data.correct_answer}`;
  await loadQueueSummary();
  setTimeout(nextItem,900);
}
loadDecks();
</script>
</body>
</html>
"""
ADMIN_HTML="""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Vocabulary Quiz Admin</title>
<style>
body{font-family:Arial,sans-serif;max-width:1200px;margin:40px auto;padding:0 16px;background:#f8fafc;color:#0f172a}
.card{background:#fff;border:1px solid #e2e8f0;border-radius:16px;padding:20px;margin-bottom:16px}
textarea,input,button,select{font:inherit}
textarea,input,select{width:100%;padding:12px;border:1px solid #cbd5e1;border-radius:12px;box-sizing:border-box}
button{padding:10px 14px;border:0;border-radius:10px;background:#0f172a;color:#fff;cursor:pointer}
button.secondary{background:#e2e8f0;color:#0f172a}
.small{font-size:14px;color:#475569}
.row{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px}
table{width:100%;border-collapse:collapse}
th,td{padding:10px;border-bottom:1px solid #e2e8f0;text-align:left;vertical-align:top}
.badge{display:inline-block;background:#e2e8f0;border-radius:999px;padding:4px 10px;margin-right:8px;font-size:12px}
a{color:#0f172a}
</style>
</head>
<body>
<h1>Admin: import and manage decks</h1>
<div class="card">
<p class="small">Enter your admin token. It is sent as the <strong>x-admin-token</strong> header.</p>
<input id="token" placeholder="admin token">
</div>
<div class="card">
<h2>Import a deck with categories</h2>
<p class="small">Recommended format: category;German;English. Example:<br><br>Basics;guten Morgen;good morning<br>Travel;der Bahnhof;train station<br>Travel;Entschuldigung;sorry|excuse me</p>
<p class="small">2-column lines are also allowed and will go into the default category <strong>General</strong>: <strong>German;English</strong>.</p>
<input id="deckName" placeholder="deck name" value="My vocabulary">
<textarea id="deckText" rows="14" placeholder="Basics;guten Morgen;good morning&#10;Basics;Wie geht's?;how are you?&#10;Travel;der Bahnhof;train station&#10;Travel;Entschuldigung;sorry|excuse me"></textarea>
<div style="margin-top:12px"><button onclick="importDeck()">import deck</button></div>
<p class="small" id="result"></p>
</div>
<div class="card">
<h2>Edit item weights</h2>
<div class="row">
<select id="adminDeckSelect"></select>
<select id="adminCategorySelect"></select>
<button class="secondary" onclick="loadAdminItems()">load items</button>
</div>
<p class="small">Manual weight guide: 0.3 = rare, 1.0 = normal, 2.0 = more frequent, 4.0 = very frequent.</p>
<div style="overflow:auto">
<table>
<thead>
<tr><th>Category</th><th>German</th><th>English</th><th>Manual weight</th><th>Action</th></tr>
</thead>
<tbody id="itemTableBody">
<tr><td colspan="5" class="small">load a deck to edit weights.</td></tr>
</tbody>
</table>
</div>
</div>
<div class="card">
<h2>Existing decks and categories</h2>
<div id="decks" class="small"></div>
</div>
<p class="small"><a href="/">back to public quiz</a></p>
<script>
const savedToken=localStorage.getItem('admin_token')||'';
document.getElementById('token').value=savedToken;
document.getElementById('token').addEventListener('input',e=>localStorage.setItem('admin_token',e.target.value));
async function api(path,options={}){
  const token=document.getElementById('token').value;
  const headers={'Content-Type':'application/json',...(options.headers||{})};
  if(token){headers['x-admin-token']=token;}
  const res=await fetch(path,{...options,headers});
  if(!res.ok){const text=await res.text();throw new Error(text||res.statusText);}
  return res.json();
}
async function importDeck(){
  try{
    const name=document.getElementById('deckName').value.trim()||'My vocabulary';
    const text=document.getElementById('deckText').value;
    const data=await api('/api/decks/import',{method:'POST',body:JSON.stringify({name,text})});
    document.getElementById('result').textContent=`imported ${data.item_count} items across ${data.category_count} categories into deck ${data.deck_id}`;
    await loadAdminDecks();
    await loadDeckSummaries();
  }catch(err){
    document.getElementById('result').textContent=`import failed: ${err.message}`;
  }
}
async function loadAdminDecks(){
  const data=await fetch('/api/decks').then(r=>r.json());
  const select=document.getElementById('adminDeckSelect');
  select.innerHTML='';
  for(const deck of data.decks){
    const opt=document.createElement('option');
    opt.value=deck.id;
    opt.textContent=`${deck.name} (${deck.item_count})`;
    select.appendChild(opt);
  }
  if(data.decks.length){
    await loadAdminCategories();
    await loadAdminItems();
  }else{
    document.getElementById('itemTableBody').innerHTML='<tr><td colspan="5" class="small">no decks yet.</td></tr>';
  }
}
async function loadAdminCategories(){
  const deckId=document.getElementById('adminDeckSelect').value;
  const data=await fetch(`/api/decks/${deckId}/categories`).then(r=>r.json());
  const select=document.getElementById('adminCategorySelect');
  select.innerHTML='';
  const all=document.createElement('option');
  all.value='';
  all.textContent='All categories';
  select.appendChild(all);
  for(const category of data.categories){
    const opt=document.createElement('option');
    opt.value=category;
    opt.textContent=category;
    select.appendChild(opt);
  }
}
document.getElementById('adminDeckSelect').addEventListener('change',async()=>{
  await loadAdminCategories();
  await loadAdminItems();
});
document.getElementById('adminCategorySelect').addEventListener('change',loadAdminItems);
async function loadAdminItems(){
  const deckId=document.getElementById('adminDeckSelect').value;
  if(!deckId)return;
  const category=document.getElementById('adminCategorySelect').value;
  const suffix=category?`?category=${encodeURIComponent(category)}`:'';
  const data=await fetch(`/api/decks/${deckId}/items${suffix}`).then(r=>r.json());
  const body=document.getElementById('itemTableBody');
  if(!data.items.length){
    body.innerHTML='<tr><td colspan="5" class="small">no items found.</td></tr>';
    return;
  }
  body.innerHTML=data.items.map(item=>`
    <tr>
      <td>${item.category}</td>
      <td>${item.german}</td>
      <td>${item.english}</td>
      <td><input id="weight-${item.id}" type="number" min="0.1" step="0.1" value="${item.manual_weight}"></td>
      <td><button onclick="saveWeight(${item.id})">save</button></td>
    </tr>
  `).join('');
}
async function saveWeight(itemId){
  const value=Number(document.getElementById(`weight-${itemId}`).value);
  try{
    await api(`/api/items/${itemId}/weight`,{method:'PATCH',body:JSON.stringify({manual_weight:value})});
    alert('weight updated');
  }catch(err){
    alert(`update failed: ${err.message}`);
  }
}
async function loadDeckSummaries(){
  const data=await fetch('/api/decks').then(r=>r.json());
  const div=document.getElementById('decks');
  if(!data.decks.length){div.textContent='no decks yet.';return;}
  let html='';
  for(const deck of data.decks){
    const categories=await fetch(`/api/decks/${deck.id}/categories`).then(r=>r.json());
    html+=`<div style="padding:8px 0;border-bottom:1px solid #e2e8f0"><strong>${deck.name}</strong> <span class="badge">items ${deck.item_count}</span> <span class="badge">categories ${categories.categories.length}</span><br>${categories.categories.join(', ')||'General'}</div>`;
  }
  div.innerHTML=html;
}
loadAdminDecks();
loadDeckSummaries();
</script>
</body>
</html>
"""
class ImportDeckRequest(BaseModel):
    name:str=Field(min_length=1,max_length=200)
    text:str=Field(min_length=1)
class NextRequest(BaseModel):
    player_id:str=Field(min_length=1,max_length=200)
    current_item_id:int|None=None
    category:str|None=None
    mode:str=Field(default="selected")
class AnswerRequest(BaseModel):
    player_id:str=Field(min_length=1,max_length=200)
    item_id:int
    answer:str
class WeightUpdateRequest(BaseModel):
    manual_weight:float=Field(ge=0.1,le=20)
class Settings(BaseModel):
    wrong_factor:float=0.6
    streak_decay:float=0.08
    unseen_boost:float=1.25
    accuracy_factor:float=0.8
    min_weight:float=0.15
DEFAULT_SETTINGS=Settings()
def now_iso()->str:
    return datetime.now(timezone.utc).isoformat()
def normalize_text(value:str)->str:
    return " ".join(value.lower().strip().replace("’","'").replace("`","'").translate(str.maketrans("","", ".!?,;:")).split())
def expand_german_variants(value:str)->set[str]:
    forms={normalize_text(value)}
    rules=[("ä",["ae","a"]),("ö",["oe","o"]),("ü",["ue","u"]),("ß",["ss"]),("ae",["ä","a"]),("oe",["ö","o"]),("ue",["ü","u"]),("ss",["ß"])]
    changed=True
    while changed:
        changed=False
        snapshot=list(forms)
        for form in snapshot:
            for src,repls in rules:
                if src in form:
                    for repl in repls:
                        candidate=form.replace(src,repl)
                        if candidate not in forms:
                            forms.add(candidate)
                            changed=True
    return {normalize_text(x) for x in forms}
def split_answers(value:str)->list[str]:
    return [part.strip() for part in value.split("|") if part.strip()]
def answer_matches(user_answer:str,accepted_answer:str)->bool:
    normalized_user=normalize_text(user_answer)
    return normalized_user in expand_german_variants(accepted_answer)
def parse_line(line:str)->tuple[str,str,str]|None:
    line=line.strip()
    if not line:
        return None
    if "\t" in line:
        parts=[part.strip() for part in line.split("\t")]
        if len(parts)>=3 and parts[0] and parts[1] and parts[2]:
            return parts[0],parts[1],"\t".join(parts[2:]).strip()
        if len(parts)>=2 and parts[0] and parts[1]:
            return "General",parts[0],"\t".join(parts[1:]).strip()
        return None
    if ";" in line:
        parts=[part.strip() for part in line.split(";")]
        if len(parts)>=3 and parts[0] and parts[1] and parts[2]:
            return parts[0],parts[1],";".join(parts[2:]).strip()
        if len(parts)>=2 and parts[0] and parts[1]:
            return "General",parts[0],";".join(parts[1:]).strip()
        return None
    if "," in line:
        parts=[part.strip() for part in line.split(",")]
        if len(parts)>=3 and parts[0] and parts[1] and parts[2]:
            return parts[0],parts[1],",".join(parts[2:]).strip()
        if len(parts)>=2 and parts[0] and parts[1]:
            return "General",parts[0],",".join(parts[1:]).strip()
        return None
    return None
@contextmanager
def db():
    conn=sqlite3.connect(DB_PATH)
    conn.row_factory=sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
def column_exists(conn:sqlite3.Connection,table_name:str,column_name:str)->bool:
    rows=conn.execute(f"pragma table_info({table_name})").fetchall()
    return any(row[1]==column_name for row in rows)
def init_db()->None:
    with db() as conn:
        conn.executescript("""
        create table if not exists decks(
            id integer primary key autoincrement,
            name text not null,
            created_at text not null
        );
        create table if not exists items(
            id integer primary key autoincrement,
            deck_id integer not null references decks(id) on delete cascade,
            category text not null default 'General',
            german text not null,
            english text not null,
            accepted_answers text not null,
            manual_weight real not null default 1.0,
            created_at text not null
        );
        create table if not exists player_item_stats(
            player_id text not null,
            item_id integer not null references items(id) on delete cascade,
            seen integer not null default 0,
            correct integer not null default 0,
            wrong integer not null default 0,
            streak integer not null default 0,
            last_wrong_at text null,
            in_mistake_queue integer not null default 0,
            mistake_clear_streak integer not null default 0,
            primary key(player_id,item_id)
        );
        """)
        if not column_exists(conn,"items","category"):
            conn.execute("alter table items add column category text not null default 'General'")
        if not column_exists(conn,"player_item_stats","in_mistake_queue"):
            conn.execute("alter table player_item_stats add column in_mistake_queue integer not null default 0")
        if not column_exists(conn,"player_item_stats","mistake_clear_streak"):
            conn.execute("alter table player_item_stats add column mistake_clear_streak integer not null default 0")
        conn.execute("create unique index if not exists idx_items_unique on items(deck_id,category,german,english)")
@app.on_event("startup")
def on_startup()->None:
    init_db()
def verify_admin_token(x_admin_token:str|None)->None:
    if not x_admin_token or x_admin_token!=ADMIN_TOKEN:
        raise HTTPException(status_code=403,detail="Admin token required")
def get_or_create_stats(conn:sqlite3.Connection,player_id:str,item_id:int)->sqlite3.Row:
    row=conn.execute("select * from player_item_stats where player_id=? and item_id=?",(player_id,item_id)).fetchone()
    if row:
        return row
    conn.execute("insert into player_item_stats(player_id,item_id,seen,correct,wrong,streak,last_wrong_at,in_mistake_queue,mistake_clear_streak) values(?,?,?,?,?,?,?,?,?)",(player_id,item_id,0,0,0,0,None,0,0))
    return conn.execute("select * from player_item_stats where player_id=? and item_id=?",(player_id,item_id)).fetchone()
def compute_weight(stat:sqlite3.Row|dict[str,Any],manual_weight:float,settings:Settings=DEFAULT_SETTINGS)->float:
    seen=stat["seen"] if isinstance(stat,sqlite3.Row) else stat.get("seen",0)
    correct=stat["correct"] if isinstance(stat,sqlite3.Row) else stat.get("correct",0)
    wrong=stat["wrong"] if isinstance(stat,sqlite3.Row) else stat.get("wrong",0)
    streak=stat["streak"] if isinstance(stat,sqlite3.Row) else stat.get("streak",0)
    accuracy=(correct/seen) if seen else 0.0
    wrong_boost=1+(wrong*settings.wrong_factor)
    streak_penalty=max(settings.min_weight,1-(streak*settings.streak_decay))
    unseen_boost=settings.unseen_boost if seen==0 else 1.0
    low_accuracy_boost=1+(max(0.0,1-accuracy)*settings.accuracy_factor)
    return max(settings.min_weight,manual_weight*wrong_boost*streak_penalty*unseen_boost*low_accuracy_boost)
def compute_effective_weight(stat:sqlite3.Row,manual_weight:float,mode:str)->float:
    base=compute_weight(stat,manual_weight)
    if stat["in_mistake_queue"] and mode in {"mistakes","mixed"}:
        return base*1.5
    return base
def fetch_items(conn:sqlite3.Connection,deck_id:int,category:str|None=None)->list[sqlite3.Row]:
    if category:
        return conn.execute("select id,deck_id,category,german,english,manual_weight from items where deck_id=? and category=? order by id asc",(deck_id,category)).fetchall()
    return conn.execute("select id,deck_id,category,german,english,manual_weight from items where deck_id=? order by category asc,id asc",(deck_id,)).fetchall()
def fetch_scope_items(conn:sqlite3.Connection,deck_id:int,player_id:str,category:str|None,mode:str)->list[sqlite3.Row]:
    selected_items=fetch_items(conn,deck_id,category)
    if mode=="selected":
        return selected_items
    if category:
        mistake_rows=conn.execute("""
            select i.id,i.deck_id,i.category,i.german,i.english,i.manual_weight
            from items i
            join player_item_stats s on s.item_id=i.id
            where i.deck_id=? and s.player_id=? and s.in_mistake_queue=1 and i.category=?
            order by i.category asc,i.id asc
        """,(deck_id,player_id,category)).fetchall()
    else:
        mistake_rows=conn.execute("""
            select i.id,i.deck_id,i.category,i.german,i.english,i.manual_weight
            from items i
            join player_item_stats s on s.item_id=i.id
            where i.deck_id=? and s.player_id=? and s.in_mistake_queue=1
            order by i.category asc,i.id asc
        """,(deck_id,player_id)).fetchall()
    if mode=="mistakes":
        return mistake_rows
    combined={row["id"]:row for row in selected_items}
    for row in mistake_rows:
        combined[row["id"]]=row
    return list(combined.values())
def weighted_choice(rows:list[sqlite3.Row],stats_by_item:dict[int,sqlite3.Row],mode:str,exclude_item_id:int|None=None)->sqlite3.Row:
    candidates=[]
    for row in rows:
        if exclude_item_id is not None and len(rows)>1 and row["id"]==exclude_item_id:
            continue
        stat=stats_by_item[row["id"]]
        weight=compute_effective_weight(stat,row["manual_weight"],mode)
        candidates.append((row,weight))
    if not candidates:
        raise HTTPException(status_code=400,detail="No items available")
    total=sum(weight for _,weight in candidates)
    threshold=random.random()*total
    running=0.0
    for row,weight in candidates:
        running+=weight
        if running>=threshold:
            return row
    return candidates[-1][0]
@app.get("/",response_class=HTMLResponse)
def home()->str:
    return INDEX_HTML
@app.get("/admin",response_class=HTMLResponse)
def admin_home()->str:
    return ADMIN_HTML
@app.get("/api/health")
def health()->dict[str,str]:
    return {"status":"ok"}
@app.get("/api/decks")
def list_decks()->dict[str,Any]:
    with db() as conn:
        rows=conn.execute("""
        select d.id,d.name,d.created_at,count(i.id) as item_count
        from decks d
        left join items i on i.deck_id=d.id
        group by d.id,d.name,d.created_at
        order by d.id desc
        """).fetchall()
        return {"decks":[dict(row) for row in rows]}
@app.get("/api/decks/{deck_id}/categories")
def list_categories(deck_id:int)->dict[str,Any]:
    with db() as conn:
        rows=conn.execute("select distinct category from items where deck_id=? order by category asc",(deck_id,)).fetchall()
        return {"categories":[row["category"] for row in rows]}
@app.post("/api/decks/import")
def import_deck(payload:ImportDeckRequest,x_admin_token:str|None=Header(default=None))->dict[str,Any]:
    verify_admin_token(x_admin_token)
    parsed=[]
    for line in payload.text.splitlines():
        item=parse_line(line)
        if item:
            parsed.append(item)
    if not parsed:
        raise HTTPException(status_code=400,detail="No valid lines found")
    with db() as conn:
        cur=conn.execute("insert into decks(name,created_at) values(?,?)",(payload.name,now_iso()))
        deck_id=cur.lastrowid
        categories=set()
        for category,german,english in parsed:
            accepted=json.dumps(split_answers(english),ensure_ascii=False)
            conn.execute("insert into items(deck_id,category,german,english,accepted_answers,manual_weight,created_at) values(?,?,?,?,?,?,?)",(deck_id,category,german,english,accepted,1.0,now_iso()))
            categories.add(category)
        return {"deck_id":deck_id,"item_count":len(parsed),"category_count":len(categories)}
@app.get("/api/decks/{deck_id}/items")
def list_items(deck_id:int,category:str|None=Query(default=None))->dict[str,Any]:
    with db() as conn:
        rows=fetch_items(conn,deck_id,category)
        return {"items":[dict(row) for row in rows]}
@app.patch("/api/items/{item_id}/weight")
def update_weight(item_id:int,payload:WeightUpdateRequest,x_admin_token:str|None=Header(default=None))->dict[str,Any]:
    verify_admin_token(x_admin_token)
    with db() as conn:
        existing=conn.execute("select id from items where id=?",(item_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404,detail="Item not found")
        conn.execute("update items set manual_weight=? where id=?",(payload.manual_weight,item_id))
        return {"item_id":item_id,"manual_weight":payload.manual_weight}
@app.get("/api/decks/{deck_id}/mistake_queue/summary")
def mistake_queue_summary(deck_id:int,player_id:str,category:str|None=Query(default=None))->dict[str,Any]:
    with db() as conn:
        total_row=conn.execute("""
            select count(*) as count
            from items i
            join player_item_stats s on s.item_id=i.id
            where i.deck_id=? and s.player_id=? and s.in_mistake_queue=1
        """,(deck_id,player_id)).fetchone()
        if category:
            scoped_row=conn.execute("""
                select count(*) as count
                from items i
                join player_item_stats s on s.item_id=i.id
                where i.deck_id=? and s.player_id=? and s.in_mistake_queue=1 and i.category=?
            """,(deck_id,player_id,category)).fetchone()
        else:
            scoped_row=total_row
        return {"total_queue":total_row["count"],"scoped_queue":scoped_row["count"]}
@app.post("/api/decks/{deck_id}/next")
def next_item(deck_id:int,payload:NextRequest)->dict[str,Any]:
    mode=payload.mode if payload.mode in {"selected","mistakes","mixed"} else "selected"
    with db() as conn:
        rows=fetch_scope_items(conn,deck_id,payload.player_id,payload.category,mode)
        if not rows:
            raise HTTPException(status_code=404,detail="Deck selection has no items")
        stats_by_item={}
        for row in rows:
            stats_by_item[row["id"]]=get_or_create_stats(conn,payload.player_id,row["id"])
        chosen=weighted_choice(rows,stats_by_item,mode,exclude_item_id=payload.current_item_id)
        return {"item_id":chosen["id"],"category":chosen["category"],"german":chosen["german"]}
@app.post("/api/decks/{deck_id}/answer")
def submit_answer(deck_id:int,payload:AnswerRequest)->dict[str,Any]:
    with db() as conn:
        row=conn.execute("select id,deck_id,category,german,english,accepted_answers from items where id=? and deck_id=?",(payload.item_id,deck_id)).fetchone()
        if not row:
            raise HTTPException(status_code=404,detail="Item not found")
        stat=get_or_create_stats(conn,payload.player_id,payload.item_id)
        accepted=json.loads(row["accepted_answers"])
        is_correct=any(answer_matches(payload.answer,accepted_answer) for accepted_answer in accepted)
        seen=stat["seen"]+1
        correct=stat["correct"]+(1 if is_correct else 0)
        wrong=stat["wrong"]+(0 if is_correct else 1)
        streak=(stat["streak"]+1) if is_correct else 0
        last_wrong_at=stat["last_wrong_at"] if is_correct else now_iso()
        if is_correct:
            in_mistake_queue=stat["in_mistake_queue"]
            mistake_clear_streak=(stat["mistake_clear_streak"]+1) if stat["in_mistake_queue"] else 0
            if in_mistake_queue and mistake_clear_streak>=2:
                in_mistake_queue=0
                mistake_clear_streak=0
        else:
            in_mistake_queue=1
            mistake_clear_streak=0
        conn.execute("update player_item_stats set seen=?,correct=?,wrong=?,streak=?,last_wrong_at=?,in_mistake_queue=?,mistake_clear_streak=? where player_id=? and item_id=?",(seen,correct,wrong,streak,last_wrong_at,in_mistake_queue,mistake_clear_streak,payload.player_id,payload.item_id))
        return {"correct":is_correct,"correct_answer":row["english"],"category":row["category"],"queued_for_review":bool(in_mistake_queue)}