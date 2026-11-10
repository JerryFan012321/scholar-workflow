"""Independent offline settings inputs and expected outcomes.

Synthetic context/requires start at revision 2. All writes remain inside this
runner. Check dirty/saving/failure states, explicit discard, conflict comparison,
same-origin session draft isolation and page history. No provider is contacted.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[2] / "src/scholar_workflow/research/recommendations/static"
NODE = shutil.which("node")
RUNNER = r"""
const fs=require('node:fs'),vm=require('node:vm');
const input=JSON.parse(fs.readFileSync(0,'utf8')),storage=new Map(),requests=[],confirmations=[];
const record={context:{content:'Saved context',revision:2,updated_by:{name:'Synthetic agent'}},ranking:{status:'current'}};
let requirement={requirement_id:'req-existing',source_id:'alphaxiv',title:'Saved title',content:'Saved requirement',enabled:true,revision:2};
let failOnce=false,holdSave=false,releaseSave=null;
let holdRequirementList=false,releaseRequirementList=null,holdRequirementPost=false,releaseRequirementPost=null,requirementWrites=0;
const find=(node,predicate)=>{if(predicate(node))return node;for(const child of node.children){const value=find(child,predicate);if(value)return value;}};
class Element{
 constructor(tag){this.tagName=tag;this.className='';this.children=[];this._text='';this.value='';this.disabled=false;this.hidden=false;this.checked=false;this.dataset={};this.listeners={};this.attributes={};this.parent=null;this.classList={toggle:(name,on)=>{const values=new Set(this.className.split(' ').filter(Boolean));on?values.add(name):values.delete(name);this.className=[...values].join(' ');}};}
 get textContent(){return this._text+this.children.map(child=>child.textContent).join('');}
 set textContent(value){this._text=String(value);this.children=[];}
 get options(){return this.children;}
 append(...nodes){for(const child of nodes){if(child.parent)child.parent.children=child.parent.children.filter(item=>item!==child);child.parent=this;this.children.push(child);}}
 replaceChildren(...nodes){for(const child of this.children)child.parent=null;this._text='';this.children=[];this.append(...nodes);}
 setAttribute(name,value){this.attributes[name]=String(value);}removeAttribute(name){delete this.attributes[name];}
 addEventListener(name,fn){(this.listeners[name]||=[]).push(fn);}
 querySelector(selector){return find(this,node=>selector.startsWith('.')&&node.className.split(' ').includes(selector.slice(1)));}
 async fire(name){if(this.disabled)throw Error('disabled control');await Promise.all((this.listeners[name]||[]).map(fn=>fn({target:this,preventDefault(){}})));}
 focus(){if(this.onFocus)this.onFocus();}
}
const settle=async()=>{for(let n=0;n<8;n++)await new Promise(setImmediate);};
function start(scope=input.scope||'test:pool-a',priorState=null){
 const ids=new Map(),events={},pages=new Map();let focus='',reloads=0;
 const get=id=>{if(!ids.has(id)){const element=new Element('div');element.id=id;element.onFocus=()=>focus=id;ids.set(id,element);}return ids.get(id);};
 for(const name of ['settings','recommendations','sources','ingestion','context']){const button=new Element('button');button.dataset.page=name;pages.set(name,button);}
 for(const id of ['settings-view','sources-view','ingestion-view','context-view','ingestion-overlay','ranking-context-latest','ranking-context-cancel'])get(id).hidden=true;
 const element=(tag,className,text)=>{const node=new Element(tag);node.className=className||'';if(text!==undefined)node.textContent=text;return node;};
 const window={scrollY:0,confirm:text=>{confirmations.push(text);return input.confirm!==false;},
  crypto:{randomUUID:()=> 'synthetic-id'},addEventListener:(name,fn)=>(events[name]||=[]).push(fn),
  scrollTo:options=>{window.scrollY=typeof options==='object'?options.top:options;},
  history:{state:priorState||{},pushState(value){this.state=value;},replaceState(value){this.state=value;}},
  sessionStorage:{getItem:key=>storage.get(key)||null,setItem:(key,value)=>storage.set(key,value),removeItem:key=>storage.delete(key)}};
 const api=async(path,payload)=>{
  requests.push({path,...(payload===undefined?{}:{body:JSON.parse(JSON.stringify(payload))})});
  if(path==='/api/ranking/context'){
   if(payload){
    if(holdSave)await new Promise(resolve=>releaseSave=resolve);
    if(input.action==='context_conflict'&&!failOnce){failOnce=true;record.context={...record.context,content:'Remote changed context',revision:3};throw Object.assign(Error('Conflict'),{code:5});}
    if(input.action==='context_failure'&&!failOnce){failOnce=true;throw Object.assign(Error('Unavailable'),{code:3});}
    record.context={...record.context,content:payload.content,revision:payload.expected_revision+1};
   }
   return JSON.parse(JSON.stringify(record));
  }
  if(path==='/api/sources')return{items:[]};
  if(path==='/api/ingestion/history')return{items:[]};
  if(path.startsWith('/api/requirements?')){
   if(holdRequirementList){holdRequirementList=false;await new Promise(resolve=>releaseRequirementList=resolve);}
   return{items:requirement.source_id===new URL('https://fixture.test'+path).searchParams.get('source_id')?[requirement]:[]};
  }
  if(path==='/api/requirements'&&payload){
   requirementWrites++;
   if(holdRequirementPost){holdRequirementPost=false;await new Promise(resolve=>releaseRequirementPost=resolve);}
   requirement={...payload,revision:payload.expected_revision+1};return requirement;
  }
  if(path.startsWith('/api/requirements/'))return JSON.parse(JSON.stringify(requirement));
  throw Error('Unexpected request '+path);
 };
 const bridge={api,element,externalLink:()=>null,getProfile:()=>scope?.split(':')[0]||'test',getDraftScope:()=>scope,
  ready:Promise.resolve(),closeDetail(){},reload:async()=>reloads++};
 window.ScholarRecommendations=bridge;
 const realm={window,document:{getElementById:get,createElement:tag=>new Element(tag),querySelectorAll:()=>[...pages.values()],addEventListener(){}},
  sessionStorage:window.sessionStorage,Date,JSON,Array,Map,Set,Number,Math,URL,TextEncoder,Uint8Array};
 vm.createContext(realm);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),realm);vm.runInContext(fs.readFileSync(process.argv[2],'utf8'),realm);
 const fields=root=>id=>find(root,node=>node.dataset.field===id);
 return{get,window,pages,events,fields,bridge,
  context:()=>({content:get('ranking-context-content').value,notice:get('ranking-context-notice').textContent,
   save:get('ranking-context-save').disabled,save_label:get('ranking-context-save').textContent,cancel:get('ranking-context-cancel').hidden,
   latest_hidden:get('ranking-context-latest').hidden,latest:get('ranking-context-latest-content').textContent,
   meta:get('ranking-context-meta').textContent}),focus:()=>focus,reloads:()=>reloads,
  mount(source='alphaxiv'){const root=new Element('div');window.ScholarRecommendationRequirements.mount(root,{source_id:source,name:source});return{root,field:fields(root)};}};
}
async function openContext(app){await app.pages.get('context').fire('click');await settle();}
async function editContext(app,value='My unsaved context'){app.get('ranking-context-content').value=value;await app.get('ranking-context-content').fire('input');}
(async()=>{
 let app=start();await settle();let extra={};
 if(input.action.startsWith('context_')){
  await openContext(app);extra.initial=app.context();
  if(input.action!=='context_clean_reload')await editContext(app);
  if(input.action==='context_dirty')extra.dirty=app.context();
  if(['context_save','context_failure','context_conflict'].includes(input.action)){
   holdSave=input.action==='context_save';const pending=app.get('ranking-context-save').fire('click');await settle();
   if(holdSave){extra.busy=app.context();releaseSave();}
   await pending;await settle();extra.after_save=app.context();
  }
  if(input.action==='context_conflict'){
   await app.get('ranking-context-adopt').fire('click');await settle();extra.adopted=app.context();
   await app.get('ranking-context-save').fire('click');await settle();
  }
  if(['context_reload_dirty','context_clean_reload'].includes(input.action)){
   record.context={...record.context,content:'Latest remote value',revision:3};await app.get('ranking-context-reload').fire('click');await settle();
  }
  if(input.action==='context_cancel'){await app.get('ranking-context-cancel').fire('click');await settle();}
  if(['context_refresh','context_failure','context_other_scope'].includes(input.action)){
   extra.before_refresh=app.context();app=start(input.action==='context_other_scope'?(input.other_scope||'personal:pool-a'):(input.scope||'test:pool-a'));await settle();await openContext(app);
  }
 }
 if(input.action.startsWith('requirement_')){
  let mounted=app.mount();await settle();let field=mounted.field;
  if(input.action!=='requirement_new_refresh'){
   const edit=find(mounted.root,node=>node.className.split(' ').includes('requirement-edit'));await edit.fire('click');await settle();
  }
  field('requirement-title').value='My draft title';await field('requirement-title').fire('input');
  field('requirement-content').value='My draft requirement';await field('requirement-content').fire('input');
  if(input.action==='requirement_save'){await field('requirement-form').fire('submit');await settle();}
  if(input.action==='requirement_clean_reload'){
   await field('requirement-form').fire('submit');await settle();await field('requirement-reload').fire('click');await settle();
  }
  if(input.action==='requirement_cancel'){await field('requirement-cancel').fire('click');await settle();}
  if(input.action==='requirement_save_lock'){
   holdRequirementList=true;
   const first=field('requirement-form').fire('submit');await settle();
   extra.list_busy={content:field('requirement-content').disabled,save:field('requirement-save').disabled};
   await field('requirement-form').fire('submit');await settle();extra.writes_before_release=requirementWrites;
   releaseRequirementList();await first;await settle();
   field('requirement-content').value='Second deliberate edit';await field('requirement-content').fire('input');
   holdRequirementPost=true;
   const second=field('requirement-form').fire('submit');await settle();
   extra.second_busy={content:field('requirement-content').disabled,save:field('requirement-save').disabled};
   releaseRequirementPost();await second;await settle();
  }
  if(['requirement_refresh','requirement_new_refresh','requirement_other_scope','requirement_other_source'].includes(input.action)){
   app=start(input.action==='requirement_other_scope'?'test:pool-b':(input.scope||'test:pool-a'));await settle();
   mounted=app.mount(input.action==='requirement_other_source'?'x-self':'alphaxiv');await settle();field=mounted.field;
  }
  extra.requirement={title:field('requirement-title').value,content:field('requirement-content').value,
   save_disabled:field('requirement-save').disabled,notice:field('requirement-notice').textContent,
   cancel_hidden:field('requirement-cancel')?.hidden};
 }
 if(input.action==='navigation'){
  app.window.scrollY=345;await app.pages.get('settings').fire('click');await settle();
  app.window.scrollY=67;await app.pages.get('ingestion').fire('click');await settle();
  const dispatch=async state=>{app.window.history.state=state;for(const fn of app.events.popstate||[])fn({state});await settle();};
  await dispatch({scholarRecommendationPage:'sources'});extra.sources={scroll:app.window.scrollY,focus:app.focus(),hidden:app.get('sources-view').hidden};
  await dispatch({scholarRecommendationPage:'recommendations'});extra.recommendations={scroll:app.window.scrollY,focus:app.focus(),hidden:app.get('recommendations-view').hidden};
  extra.history=app.window.history.state;extra.gear=app.pages.get('settings').attributes;
 }
 process.stdout.write(JSON.stringify({context:app.context(),storage:[...storage],requests,confirmations,...extra}));
})().catch(error=>{process.stderr.write(error.stack);process.exitCode=1;});
"""


def render(action, **inputs):
    if not NODE:
        pytest.skip("Node is required for synthetic settings journeys.")
    result = subprocess.run([NODE, "-e", RUNNER, str(STATIC / "workspace.js"), str(STATIC / "requirements.js")],
                            input=json.dumps({"action": action, **inputs}), text=True, capture_output=True, check=True)
    return json.loads(result.stdout)


def test_context_changes_have_dirty_and_unmodified_states():
    result = render("context_dirty")
    assert result["initial"]["save"] and result["initial"]["cancel"]
    assert not result["dirty"]["save"] and not result["dirty"]["cancel"]
    assert "未保存" in result["dirty"]["notice"]


def test_context_save_has_busy_state_then_clears_the_session_draft():
    result = render("context_save")
    assert result["busy"]["save"] and "保存中" in result["busy"]["save_label"]
    assert result["context"]["save"] and "已保存" in result["context"]["notice"]
    assert result["storage"] == []


@pytest.mark.parametrize("action", ["context_refresh", "context_failure"])
def test_context_refresh_or_failed_save_restores_the_unsaved_text(action):
    result = render(action)
    assert result["context"]["content"] == "My unsaved context"
    assert "草稿" in result["context"]["notice"]
    if action == "context_failure":
        assert "未保存" in result["after_save"]["notice"]


@pytest.mark.parametrize("other_scope", ["personal:pool-a", "test:pool-b"])
def test_context_drafts_do_not_cross_profile_or_pool(other_scope):
    result = render("context_other_scope", other_scope=other_scope)
    assert result["context"]["content"] == "Saved context"


def test_reading_latest_context_preserves_a_dirty_editor_without_confirmation():
    result = render("context_reload_dirty")
    assert result["context"]["content"] == "My unsaved context"
    assert result["context"]["latest"] == "Latest remote value" and not result["context"]["latest_hidden"]
    assert not result["confirmations"]


def test_clean_context_reload_needs_no_discard_confirmation():
    result = render("context_clean_reload")
    assert result["context"]["content"] == "Latest remote value" and not result["confirmations"]


@pytest.mark.parametrize("confirm", [False, True])
def test_cancel_is_explicit_and_only_discards_after_confirmation(confirm):
    result = render("context_cancel", confirm=confirm)
    assert len(result["confirmations"]) == 1
    assert result["context"]["content"] == ("Saved context" if confirm else "My unsaved context")


def test_context_conflict_keeps_old_revision_until_explicit_adoption():
    result = render("context_conflict")
    assert result["after_save"]["content"] == "My unsaved context"
    assert "草稿已保留" in result["after_save"]["notice"]
    assert result["after_save"]["latest"] == "Remote changed context"
    writes = [row["body"] for row in result["requests"] if "body" in row]
    assert [row["expected_revision"] for row in writes] == [2, 3]
    assert not result["confirmations"]


@pytest.mark.parametrize("action", ["requirement_refresh", "requirement_new_refresh"])
def test_source_requirement_drafts_recover_after_refresh(action):
    result = render(action)
    assert result["requirement"]["title"] == "My draft title"
    assert result["requirement"]["content"] == "My draft requirement"
    assert "草稿" in result["requirement"]["notice"]


@pytest.mark.parametrize("action", ["requirement_other_scope", "requirement_other_source"])
def test_source_requirement_drafts_are_isolated_by_pool_and_source(action):
    result = render(action)
    assert result["requirement"]["content"] == ""


def test_saved_source_requirement_clears_draft_and_clean_reload_does_not_confirm():
    result = render("requirement_clean_reload")
    assert result["storage"] == [] and result["confirmations"] == []
    assert result["requirement"]["save_disabled"]


@pytest.mark.parametrize("confirm", [False, True])
def test_source_requirement_cancel_preserves_or_discards_only_after_confirmation(confirm):
    result = render("requirement_cancel", confirm=confirm)
    assert len(result["confirmations"]) == 1
    assert result["requirement"]["content"] == ("Saved requirement" if confirm else "My draft requirement")
    assert bool(result["storage"]) is not confirm


def test_requirement_save_lock_covers_delayed_list_refresh_and_the_next_save():
    result = render("requirement_save_lock")
    assert result["list_busy"] == {"content": True, "save": True}
    assert result["writes_before_release"] == 1
    assert result["second_busy"] == {"content": True, "save": True}
    writes = [row["body"] for row in result["requests"] if "body" in row]
    assert [row["expected_revision"] for row in writes] == [2, 3]
    assert result["requirement"]["content"] == "Second deliberate edit"
    assert result["requirement"]["save_disabled"]


def test_browser_history_keeps_recommendation_scroll_and_focus_without_disclosure_semantics():
    result = render("navigation")
    assert result["sources"] == {"scroll": 67, "focus": "sources-title", "hidden": False}
    assert result["recommendations"] == {"scroll": 345, "focus": "page-title", "hidden": False}
    assert "aria-expanded" not in result["gear"]
